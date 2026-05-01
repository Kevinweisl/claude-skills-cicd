---
name: build-and-release
description: |
  Build a Python wheel, npm package, or container image AND optionally push it
  to a registry — a side-effecting write operation. Use this when the user asks
  to "release", "publish", "ship a new version", "push to PyPI", "build and
  push the docker image", "cut a release", or any explicit publish/release
  request. Do NOT use for: simply running tests or linters (use lint-and-test),
  scanning the build for secrets (use security-scan), checking dependencies for
  vulnerabilities (use dependency-audit), or read-only "show me the build
  config" requests. Side-effecting WRITE — `disable-model-invocation: true` so
  Claude must be explicitly directed by the human to invoke this skill.
allowed-tools: "Bash(python -m build) Bash(npm run build) Bash(npm publish *) Bash(docker build *) Bash(docker push *) Bash(git tag *)"
worker_target: ci
disable-model-invocation: true
---

# build-and-release

Build a release artifact and (optionally) push it to its registry.
**Side-effecting**: this skill mutates external state (registry, git tags). The
`disable-model-invocation: true` flag means Claude will not auto-invoke this
skill from a model decision — only an explicit human-issued tool call will run
it. This is the "press the deploy button" boundary.

## Pattern: Side-effecting write + content-addressed safety

Idempotency is content-addressed: the artifact's SHA-256 digest is computed
BEFORE push. If a prior run with the same digest already pushed, this run
returns `{pushed: false, reason: "already-published"}` and exits without
re-pushing. Tag immutability is enforced for OCI images (no `latest` overwrite).

`dry_run: true` (default) computes the digest, validates the build, but does
NOT push. This is the safe rehearsal mode.

## Input
```json
{
  "target": "wheel" | "npm" | "docker",
  "version": "1.2.3",                        // semver — required
  "dry_run": true,                           // default true; must be set false to publish
  "registry": "https://upload.pypi.org/...", // target registry
  "image_name": "ghcr.io/org/repo"           // for docker target
}
```

## Output
```json
{
  "ok": true,
  "target": "wheel",
  "digest": "sha256:abcd...",
  "pushed": false,
  "dry_run": true,
  "tag_created": null,
  "registry_url": null
}
```

## Auth & safety

API token comes from the worker's environment (`PYPI_TOKEN`, `NPM_TOKEN`,
`DOCKER_PASS`) — never from the input payload. Token-bearing fields in errors
are redacted. Two-factor publish protections (e.g. PyPI trusted publishers)
should be enabled at the registry side, not relied on at the skill layer.
