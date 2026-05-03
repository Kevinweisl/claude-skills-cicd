"""Token-shape redaction so skill output never leaks credentials."""

from __future__ import annotations

import re

_TOKEN_PATTERNS = [
    re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),                    # GitHub PAT
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                        # AWS access key
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),             # OpenAI / Anthropic
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{30,}\b"),               # NVIDIA NIM
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),  # JWT
]


def redact_tokens(text: str) -> tuple[str, int]:
    """Replace token-shaped strings with <redacted-N>. Returns (text, count)."""
    redactions = 0
    for pat in _TOKEN_PATTERNS:
        for _ in pat.finditer(text):
            redactions += 1
        text = pat.sub(lambda m, c=[0]: (
            f"<redacted-{(c.__setitem__(0, c[0] + 1) or c[0])}>"
        ), text)
    return text, redactions
