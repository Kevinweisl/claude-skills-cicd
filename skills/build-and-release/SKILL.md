---
name: build-and-release
description: Build a Python wheel, npm package, or Docker image AND optionally push it to a registry — a side-effecting write operation. Use this when the user asks to "release v1.2.3", "publish to PyPI", "twine upload", "npm publish", "ship a new version", "build and push the docker image to ghcr", "cut a github release", "tag and push", "deploy the SDK", or any explicit publish/release request. For running tests or linters, use lint-and-test. For SAST or secret scans, use security-scan. For dependency CVE checks, use dependency-audit.
allowed-tools: Bash(git clone:*), Bash(python:*), Bash(./skills/build-and-release/scripts/run.py:*), Bash(rm -rf /tmp/skill_sandbox*)
disable-model-invocation: true
---

# build-and-release

Build a wheel / npm tarball / Docker image; optionally push to a registry. **Write skill** — `disable-model-invocation: true` is set so Claude must be explicitly asked to run this; it will not auto-trigger from ambiguous requests.

## When to use

Trigger only on explicit publish/release requests:

- "release v1.2.3 to PyPI"
- "build and push the docker image to ghcr"
- "npm publish this package"
- "ship a new version, dry run first"

**Don't use for**: lint/test (`lint-and-test`), CVE audit (`dependency-audit`), SAST/secrets (`security-scan`), or any request that doesn't explicitly mention publishing/releasing.

## How to use

### Step 1 — confirm intent before doing anything

This skill writes to a registry only when `--no-dry-run` is passed. **Default to dry-run on first invocation.** If the user explicitly says "actually push" / "for real" / "no dry run", then pass `--no-dry-run`.

### Step 2 — get the repo onto disk

If a `https://github.com/...` URL was given, clone shallowly:

```bash
SANDBOX=/tmp/skill_sandbox/build-$$
git clone --depth=1 --branch <REF> <REPO_URL> $SANDBOX
```

If a local path was given, use it directly.

### Step 3 — run the script

```bash
python skills/build-and-release/scripts/run.py \
    --repo-path $SANDBOX \
    --target wheel|npm|docker \
    --version 1.2.3 \
    [--image-name owner/name]    # required only for --target docker
    [--no-dry-run]                # only if user explicitly asked
```

The script prints exactly one JSON object on stdout.

### Step 4 — interpret the JSON

Happy path:

```json
{
  "ok": true,
  "target": "wheel",
  "version": "1.2.3",
  "artifact": "mypkg-1.2.3-py3-none-any.whl",
  "digest": "sha256:9a1f...",
  "pushed": false,
  "dry_run": true
}
```

Failure cases:

- `ok=false` + `error="build failed"` → look at `stderr_tail`
- `ok=false` + `error="no wheel produced"` → version arg likely doesn't match `pyproject` version
- `ok=false` + `error="image_name required"` → only happens for `--target docker`

If `pushed=true`, the artifact is on the registry. `digest` is content-addressed, so re-running with the same content is a no-op (registries reject duplicate digests).

### Step 5 — clean up

```bash
rm -rf /tmp/skill_sandbox/build-*
```

## Boundaries

- **Side-effecting.** Writes to the registry when `--no-dry-run` is set.
- **Auth required for push.** Caller must have `TWINE_*` / `NPM_TOKEN` / docker login configured.
- **No tests run here.** Use `lint-and-test` first to verify the build is good before publishing.
- **`disable-model-invocation: true`** — explicit Claude invocation only, no auto-routing.
- **Idempotent by digest.** Re-pushing the same content is a no-op at the registry.
