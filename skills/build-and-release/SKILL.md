---
name: build-and-release
description: Build a Python wheel, npm package, or Docker image AND optionally push it to a registry. This is a SIDE-EFFECTING WRITE OPERATION. Default behaviour reads `$PWD` (the repo the user is releasing) and runs in dry-run mode (build only, no push). Use this when the user asks to "release v1.2.3", "publish to PyPI", "twine upload", "npm publish", "ship a new version", "build and push the docker image to ghcr", "cut a github release", "tag and push", "deploy the SDK", or any explicit publish/release request on the current repo. The user may also pass a GitHub URL to release a different repo. For running tests or linters, use lint-and-test. For SAST or secret scans, use security-scan. For dependency CVE checks, use dependency-audit.
allowed-tools: Bash(python:*), Bash(./skills/build-and-release/scripts/run.py:*)
disable-model-invocation: true
---

# build-and-release

Build a wheel / npm tarball / docker image. Push to a registry only when explicitly told to via `--no-dry-run`. **Side-effecting.** Idempotent by content digest (re-pushing the same artifact is a no-op at the registry level).

## When to use

This skill has `disable-model-invocation: true`, so Claude must NOT auto-fire it from a soft natural-language ask. The user has to explicitly invoke it via `/claude-skills-cicd:build-and-release` or be very direct in chat ("run the build-and-release skill on this repo"); even then Claude should usually confirm before pushing.

- "build and release v1.2.3" → run on the user's current repo
- "build and release https://github.com/foo/bar at v1.2.3" → shallow-clone, then build

## How to invoke

### Default: current repository (build the user's own work)

```bash
python skills/build-and-release/scripts/run.py \
    --target wheel --version 1.2.3
```

The script reads `$PWD`, validates `.git/`, and builds against the working tree.

### Remote: shallow-clone a GitHub URL

```bash
python skills/build-and-release/scripts/run.py \
    --repo-url https://github.com/foo/bar --ref v1.2.3 \
    --target wheel --version 1.2.3
```

Same dry-run / push semantics; sandbox is auto-cleaned.

## Required arguments

- `--target wheel|npm|docker`
- `--version SEMVER` (required for `wheel` and `docker`)
- `--image-name OWNER/NAME` (required for `docker`)

## Push semantics

- **Default**: dry-run. Build the artifact, compute its digest, do not push.
- **`--no-dry-run`**: actually push (twine upload / npm publish / docker push). Caller must already have credentials configured (`~/.pypirc`, `~/.npmrc`, docker login).

## Interpret the JSON output

```json
{
  "ok": true,
  "target": "wheel",
  "version": "1.2.3",
  "artifact": "yourpkg-1.2.3-py3-none-any.whl",
  "digest": "sha256:abc...",
  "dry_run": true,
  "pushed": false,
  "push_log_tail": null
}
```

`pushed=true` only when `--no-dry-run` was passed AND the push succeeded.

## Boundaries

- **`disable-model-invocation: true`**: Claude does not fire this from a free-form prompt. Human gate is the safety boundary.
- **Dry-run by default.** Push is opt-in via explicit flag.
- **No tagging / no `git push`** of source. Only artifacts go out.
- **URL guard.** Only `https://github.com/` accepted in `--repo-url`.
