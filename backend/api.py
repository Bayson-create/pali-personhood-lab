"""Standalone, evidence-audited FastAPI service for the personhood lab."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from personhood.engine import run_interaction

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "research" / "PERSONHOOD_EVIDENCE_AUDIT.json"


class EpisodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    modelVersion: str = "pali-canonical/v1"
    scenario: dict[str, Any] | None = None
    agents: list[dict[str, Any]] | None = None
    interventions: dict[str, Any] = Field(default_factory=dict)
    seed: str | int = 0
    maxRounds: int = Field(default=1, ge=1, le=6)


class ExplainRequest(EpisodeRequest):
    question: str = Field(default="请解释这条条件过程。", min_length=1, max_length=2000)


class CaseSaveRequest(BaseModel):
    """Standalone service deliberately exposes no account persistence.

    The contract remains available so the static client can report a truthful
    degraded state instead of silently pretending a local save is durable.
    """
    title: str = Field(default="连续互动案例", min_length=1, max_length=200)
    snapshot: dict[str, Any]


app = FastAPI(title="Pali Personhood Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _run(payload: EpisodeRequest) -> dict[str, Any]:
    try:
        return run_interaction(payload.model_dump(by_alias=True, exclude_none=True))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _fallback(trace: dict[str, Any], question: str) -> dict[str, Any]:
    events = [event for stream in trace.get("streams", []) for event in stream.get("events", [])]
    return {
        "answer": (
            f"这是一个由门、所缘、识、触、受、想与行动条件化的可审计过程（问题：{question.strip()}）。"
            f"本次生成 {len(events)} 个事件；模型只显示条件与外化行动，不读取任何私有心念。"
        ),
        "event_refs": [event.get("id") for event in events],
        "evidence_refs": sorted({item for event in events for item in event.get("evidence_ids", [])}),
        "limits": [
            "五蕴在此是共同生起的观察标签，不是固定人格实体。",
            "‘灭’只表示当前局部爱取或反应循环止息，不是证悟认证。",
            "动物场景只模拟共享刺激与可观察反馈，不推断动物内在经验。",
        ],
        "ai": {"enabled": False, "degraded": True, "provider": "deterministic-local"},
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "pali-personhood-lab"}


@app.post("/api/personhood/episodes")
def episodes(payload: EpisodeRequest) -> dict[str, Any]:
    return {"trace": _run(payload), "persisted": False, "evidence_audit_required": True}


@app.get("/api/personhood/evidence")
def evidence() -> dict[str, Any]:
    if not AUDIT_PATH.exists():
        raise HTTPException(status_code=503, detail="证据审计快照尚未生成")
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


@app.post("/api/personhood/explain")
def explain(payload: ExplainRequest) -> dict[str, Any]:
    trace = _run(payload)
    return {"trace": trace, "explanation": _fallback(trace, payload.question), "persisted": False}


@app.post("/api/personhood/cases", status_code=501)
def cases_unavailable(_: CaseSaveRequest) -> None:
    raise HTTPException(status_code=501, detail="独立预览服务不保存账户案例；请使用本地导出或集成后的账户服务")
