# Task 1 — Skills Platform UI Design

> Date: 2026-05-03 · Status: Spec for review · Owner: Kevin Wei

## Goal

讓評審能用瀏覽器在**他自己挑的 GitHub repo** 上實打 Task 1 的 4 個 CI/CD skill，
並視覺化看到題目要評分的四個面向：

1. **Skill 邊界** — 4 張獨立 card，描述 + 適用 vs. 不適用情境
2. **認證** — Bearer key 由評審自帶（localStorage），未填會 prompt
3. **Idempotency** — Idempotency-Key 自動產生，但有手動覆寫欄位讓評審親手測「重打回相同 run_id」
4. **錯誤處理 / silent failure 防範** — handler 失敗會回 `{ok: false, error: ...}`，UI 用紅色區塊呈現

題目原文「在 Zeabur 部署一個 demo（Web UI 或 API）」的「Web UI」分支，本 spec 對應到此。

## Out of Scope

- React / SPA build pipeline（vanilla JS、無 build step）
- 帳號、SSO、多用戶
- Zeabur 部署（blocker 解開後再上；先 ship 本機可跑、可錄影）
- `browser-task` / `sec-extract-10k` / `hello`（不在 Task 1 deliverable，UI 只列 4 個 CI/CD skill）
- WebSocket（SSE 已經夠用）

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Browser (evaluator)                                              │
│   ui/index.html  ──▶  fetch / EventSource  ──▶  Gateway          │
│   ui/app.js                                                      │
│   ui/styles.css                                                  │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI Gateway (existing)                                       │
│   GET  /skills              list registered skills (existing)    │
│   POST /skills/{n}/invoke   202 + run_id (existing)              │
│   GET  /runs/{id}           run record (existing)                │
│   GET  /runs/{id}/stream    SSE (existing)                       │
│   GET  /runs?limit=20       NEW — list recent runs               │
│   GET  /ui/* + GET /        NEW — StaticFiles + redirect         │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ CI Worker (existing pool)                                        │
│   1. dequeue run                                                 │
│   2. NEW git_fetch(repo, ref) → /tmp/sandbox/<run_id>            │
│   3. dispatch to existing handler with repo_path                 │
│   4. cleanup sandbox                                             │
└──────────────────────────────────────────────────────────────────┘
```

技術選擇：**Vanilla HTML + ES module JS + plain CSS**，無 framework / build。
理由：題目評的是後端 + 平台設計，UI 只是讓 demo 看得見；React/Next 等於 build chain
噪音，反而稀釋訊號。一頁 < 500 行 JS。

## Backend Gaps to Fill

掃 code 後發現三個必補的 gap：

### Gap 1 — Handler 不會 git clone（**critical**）

`src/workers/ci/handlers.py:104` 預期 `payload["repo_path"]` 是 local path：
```python
repo_path = Path(payload.get("repo_path") or os.getcwd()).resolve()
```
若評審塞 GitHub URL 進來，會跑到 `os.getcwd()`，等於在我們自己的 repo 上跑 ruff/pytest。
**這是端到端 demo 不可能 work 的硬阻塞。**

**修法**：在 worker dispatch 層（不是 handler）加 `git_fetch` pre-step：

```python
# src/workers/ci/git_fetch.py (新檔)
async def fetch_repo(repo: str, ref: str, dest: Path) -> Path:
    """Shallow-clone repo@ref into dest. Validate URL prefix == https://github.com/.
    Return cloned path."""
    if not repo.startswith("https://github.com/"):
        raise ValueError(f"only https://github.com/ URLs allowed: {repo}")
    await _run_subprocess(
        ["git", "clone", "--depth=1", "--branch", ref, repo, str(dest)],
        timeout_s=120.0,
    )
    return dest
```

`src/workers/ci/__main__.py` 在 dequeue 後、call handler 前包一層：

```python
sandbox = Path("/tmp/skill_sandbox") / str(run_id)
try:
    await fetch_repo(payload["repo"], payload.get("ref", "main"), sandbox)
    payload["repo_path"] = str(sandbox)
    result = await handler(payload)
finally:
    shutil.rmtree(sandbox, ignore_errors=True)
```

**安全邊界**：
- 只允許 `https://github.com/` prefix（拒絕 file://、ssh://、其他 host）
- `--depth=1` 不抓全 history
- Sandbox 在 `/tmp/skill_sandbox/<run_id>`，run 完即砍
- Clone timeout 120s
- Handler 內既有 timeout（pytest 300s 等）保留不動

### Gap 2 — 無 `GET /runs` list endpoint

UI 右下要顯示 run history。目前只有 `GET /runs/{id}`（單筆）。
新增：

```python
GET /runs?limit=20&skill=lint-and-test
→ [
    { run_id, skill_name, status, created_at, duration_ms, ok },
    ...
  ]
```
- limit 預設 20、上限 100
- skill 過濾為 optional
- 排序：`created_at DESC`
- 不回 `result_json` 全文（太肥），UI 點開單筆才打 `/runs/{id}`

### Gap 3 — UI 要過濾掉非 Task 1 skill

`/skills` 會回 7 個（manifest_scanner 把 `skills/*/SKILL.md` 全 sync 進 DB）。
**UI 過濾邏輯放前端**：`worker_target == 'ci' && name != 'hello'`。
不動 backend。

## UI Components

### Layout（單頁三欄）

```
┌──────────────────────────────────────────────────────────────────┐
│  Skills Platform                            API key: [..........]│
├──────────────────────────────┬───────────────────────────────────┤
│ Skill list (4 cards)         │  Active run                       │
│                              │   status: running ●               │
│  ┌──────────────────────┐    │   skill:  lint-and-test           │
│  │ lint-and-test        │    │   repo:   psf/black @ main        │
│  │ Run lint+test on…    │    │                                   │
│  └──────────────────────┘    │   ─ live status stream ─          │
│  ┌──────────────────────┐    │   queued → running → ?            │
│  │ build-and-release    │    │                                   │
│  └──────────────────────┘    │   ─ result (when done) ─          │
│  ┌──────────────────────┐    │   { ok: true, lint: {...} }       │
│  │ dependency-audit     │    │                                   │
│  └──────────────────────┘    │                                   │
│  ┌──────────────────────┐    │                                   │
│  │ security-scan        │    │                                   │
│  └──────────────────────┘    │                                   │
├──────────────────────────────┴───────────────────────────────────┤
│ Form (appears under selected card)                               │
│  Repo URL:  [_____________________]                              │
│  Ref:       [main]                                               │
│  Idempotency-Key: [auto-uuid]  [Generate new]                    │
│  ─ skill-specific options ─                                      │
│  [Run]                                                           │
├──────────────────────────────────────────────────────────────────┤
│ Run history (last 20)                                            │
│  ✓ lint-and-test  psf/black     2m ago    18.4s                  │
│  ✗ security-scan  psf/requests  5m ago    12.1s                  │
│  ...                                                             │
└──────────────────────────────────────────────────────────────────┘
```

### Skill-specific form fields

| Skill | Extra fields |
|---|---|
| lint-and-test     | `language`: auto / python / node |
| build-and-release | `target`: wheel / npm / docker；`version`: 字串；`dry_run`: 強制 true（UI 不開放關閉）|
| dependency-audit  | `ecosystem`: auto / pypi / npm / cargo / go |
| security-scan     | `scan_types`: checkbox `[sast] [secrets] [container]`，預設前兩個 |

### State transitions（前端）

```
idle ──pick skill──▶ form_visible
form_visible ──submit──▶ submitting (POST invoke)
submitting ──202──▶ streaming (open SSE)
streaming ──"completed"/"failed"──▶ result_shown
result_shown ──pick skill again──▶ form_visible
```

### API key 管理

第一次進站 `localStorage["skills_api_key"]` 為空 → top bar 輸入框聚焦 + 紅框提示。
所有 fetch / EventSource 帶 `Authorization: Bearer <key>`。
401 → 清掉 key、提示重輸。

### Idempotency 演示

- 預設每次開 form 時 auto-generate UUID 進 input
- 評審按 [Generate new] 可重新產生
- 評審手動把同一個 key 再 submit 一次 → 應該回相同 `run_id`、status 直接是 `completed`
- UI 在 result 區塊上方加 banner：「Idempotency hit — reused run X」

## Data Flow（一個 lint-and-test 端到端）

```
1. User picks lint-and-test card
2. Form: repo=https://github.com/psf/black, ref=24.10.0, key=<uuid>
3. POST /skills/lint-and-test/invoke
   headers: Authorization: Bearer ..., Idempotency-Key: <uuid>
   body:    { repo, ref, language: "auto" }
4. Gateway: 202 { run_id, status: "queued" }
5. UI: open EventSource(/runs/<run_id>/stream)
6. Worker dequeues, status → "running"
7. Worker: git clone --depth=1 --branch 24.10.0 https://github.com/psf/black /tmp/skill_sandbox/<run_id>
8. Handler: ruff check . → pytest -q
9. Worker: UPDATE runs SET status='completed', result_json=...
10. SSE: event: result, data: { ok, lint, test, ... }
11. UI: render result panel
12. Worker: shutil.rmtree(sandbox)
```

## Error Handling

| 失敗點 | 行為 |
|---|---|
| Bad API key | Gateway 401 → UI 紅框 + 清 localStorage |
| Repo URL 不是 github.com | Worker 在 git_fetch 階段 raise → run 標 `failed`，error="only https://github.com/ URLs allowed" |
| Ref 不存在 | git clone exit_code != 0 → run 標 `failed`，error 含 git stderr |
| Repo 無 pyproject.toml 也無 package.json | Handler 回 `{ok: false, error: "unsupported language"}`，run 仍 `completed`（區分 platform error vs. skill-level fail）|
| pytest timeout 300s | Handler 回 `{ok: false, test: { timed_out: true }}` |
| Clone timeout 120s | run 標 `failed` |
| SSE 斷線 | UI 退回 polling `/runs/{id}` 每 2s |

## End-to-End Test Plan

部署 / 接 Zeabur 前，先在本機跑這組驗收：

| # | Skill | Repo | Expected | 驗證點 |
|---|---|---|---|---|
| 1 | lint-and-test | `psf/black` @ `24.10.0` | `ok=true`, lint+test 都過 | 真 git clone、真 ruff/pytest |
| 2 | lint-and-test | `psf/black` @ `24.10.0` 同一個 Idempotency-Key 再打 | 回**相同** run_id | Idempotency 第 1 層 |
| 3 | dependency-audit | `psf/requests` @ `main` | OSV / GHSA finding list（任意數量）| Multi-ecosystem detect = python |
| 4 | security-scan | `psf/requests` @ `main` | Semgrep + gitleaks 結果，token 若有要被 redact | Secret redaction |
| 5 | build-and-release | 我們自己的 repo `dry_run=true` | wheel 建出來、不 push | `disable-model-invocation` 仍允許 explicit invoke |
| 6 | lint-and-test | `https://gitlab.com/foo/bar` | run `failed`, error="only https://github.com/ URLs allowed" | URL prefix guard |
| 7 | lint-and-test | `https://github.com/does/not/exist` | run `failed`, error 含 git stderr | Clone 失敗處理 |
| 8 | lint-and-test | 一個沒有 pyproject 也沒有 package.json 的 repo（e.g. `torvalds/linux` 太大會超時，改用 `Microsoft/vcpkg` 或自建小 repo）| `ok=false, error="unsupported language"`，run `completed` | Platform error vs. skill-level fail 區分 |

第 1、3、5 是 happy path；第 2 是 idempotency；第 6、7、8 是 silent-failure 防範。
全部用 UI 跑（不 curl），逐一截圖或錄成 GIF 放 README。

## File Deliverables

新檔：
- `ui/index.html`
- `ui/app.js`
- `ui/styles.css`
- `src/workers/ci/git_fetch.py`
- `tests/test_git_fetch.py`
- `tests/test_runs_list.py`
- `docs/superpowers/specs/2026-05-03-task1-ui-design.md`（此檔）

改檔：
- `src/gateway/main.py` — mount StaticFiles，加 root redirect
- `src/gateway/routes/runs.py` — 加 list endpoint
- `src/workers/ci/__main__.py` — 包 git_fetch + cleanup
- `README.md` — 加 UI 截圖 + curl 對照範例

## Risk / YAGNI Cuts

- ❌ **CSV / 匯出 run history** — 不做，題目沒問
- ❌ **Diff 兩次 run 結果** — 不做
- ❌ **Webhook / GitHub App** — 不做（Day 7 之後再評估）
- ❌ **多語系** — 不做（評審是中文 OK 的）
- ❌ **暗黑模式** — 不做
- ✅ **基本 a11y**：input label、button 可鍵盤觸發、aria-live 給 status 區塊（成本低、面試官一眼看出細心）

## Time-box

**Hard cap：今天（2026-05-03）下班前 ship + e2e 跑完**。
若 UI polish 拉太長，先有醜版再美化。Backend gap 必須 100% 完成。
