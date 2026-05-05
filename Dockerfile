FROM python:3.12-slim

# OS-level tools the skills depend on.
#   git           : skills/_shared/git_fetch.py shallow-clones target repos
#   ca-certificates, curl : for fetching the gitleaks binary release
#   build-essential : some Python wheels (e.g. lxml deps for semgrep) need a C toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# gitleaks: download a pinned release binary (no apt package). Pin a known-good version.
ENV GITLEAKS_VERSION=8.21.2
RUN curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        | tar -xz -C /usr/local/bin gitleaks \
    && chmod +x /usr/local/bin/gitleaks

# Python-side scanner binaries. Installed globally so the skills' subprocess
# calls find them on PATH. Heavy ones (Node/Rust/Go/Docker/trivy) are skipped
# on purpose: each skill returns `error: "binary not installed"` and an empty
# result list rather than crashing.
RUN pip install --no-cache-dir \
        ruff \
        pytest \
        pip-audit \
        bandit \
        semgrep \
        build

WORKDIR /app

# Install Python deps first (cacheable layer) before copying the rest.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY skills ./skills
COPY ui ./ui
COPY .claude-plugin ./.claude-plugin
COPY evals ./evals

RUN pip install --no-cache-dir -e .

# Zeabur injects $PORT at runtime. Bind to 0.0.0.0 so the container is reachable.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn agent_shell.main:app --host 0.0.0.0 --port ${PORT} --app-dir src"]
