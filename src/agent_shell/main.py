"""Anthropic Agent SDK web shell.

POST /chat with header `X-Anthropic-Key: sk-ant-...` and JSON body
{"messages": [...]} streams the conversation back as SSE events:

  - event: text         (model text delta — full block, not delta-stream)
  - event: tool_use     (Claude calling a skill)
  - event: tool_result  (skill output)
  - event: done         (model finished, no more tool calls)
  - event: error        (anything went wrong)

Why is the API key in the header (not server-side)? So that we can host this
publicly without putting our credentials on the server. Each evaluator brings
their own Anthropic key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agent_shell.skill_loader import load_skills  # noqa: E402
from agent_shell.tool_runner import run_skill  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
UI_DIR = REPO_ROOT / "ui"

DEFAULT_MODEL = "claude-opus-4-7"  # strongest tool-routing + JSON summarisation in the lineup

app = FastAPI(title="Claude Skills CI/CD — Agent Shell")


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = DEFAULT_MODEL


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/skills")
def list_skills_endpoint() -> list[dict]:
    """Public — let UI render a sidebar of available skills."""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in load_skills(SKILLS_DIR)
    ]


def _sse(event: str, payload) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.post("/chat")
async def chat(
    req: ChatRequest,
    x_anthropic_key: str = Header(..., alias="X-Anthropic-Key"),
) -> StreamingResponse:
    if not x_anthropic_key.startswith("sk-ant-"):
        raise HTTPException(401, "invalid API key shape (expected sk-ant-...)")

    client = anthropic.Anthropic(api_key=x_anthropic_key)
    tools = load_skills(SKILLS_DIR)
    system = (
        "You have access to 4 CI/CD skills (lint-and-test, build-and-release, "
        "dependency-audit, security-scan). When the user asks for one, use the "
        "matching tool. Surface the skill's JSON output to the user in a clear, "
        "human-readable form — call out failures and missing scanner binaries "
        "honestly."
    )

    async def gen():
        messages = list(req.messages)
        try:
            for _ in range(8):
                resp = client.messages.create(
                    model=req.model,
                    max_tokens=4096,
                    system=system,
                    tools=tools,
                    messages=messages,
                )
                tool_use_block = None
                for block in resp.content:
                    if block.type == "text":
                        yield _sse("text", {"text": block.text})
                    elif block.type == "tool_use":
                        tool_use_block = block
                        yield _sse("tool_use", {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                if tool_use_block is None:
                    yield _sse("done", {})
                    return

                result = run_skill(tool_use_block.name, tool_use_block.input)
                yield _sse("tool_result", {
                    "id": tool_use_block.id,
                    "name": tool_use_block.name,
                    "result": result,
                })
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": json.dumps(result),
                }]})

            yield _sse("done", {"warning": "max tool round-trips reached (8)"})
        except anthropic.AuthenticationError:
            yield _sse("error", {"error": "invalid API key"})
        except anthropic.APIError as exc:
            yield _sse("error", {"error": f"Anthropic API error: {exc}"})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"error": f"server error: {type(exc).__name__}: {exc}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


# Mount UI last so /chat /skills /health win path matching first.
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
