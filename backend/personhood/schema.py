"""Portable input/output contract for the Pali personhood process model."""
from __future__ import annotations

from copy import deepcopy

SCHEMA_VERSION = "pali-personhood/0.1"
CANONICAL = "pali-canonical/v1"
SYNTHESIS = "theravada-synthesis/v1"
DOORS = ("eye", "ear", "nose", "tongue", "body", "mind")
VALENCES = ("pleasant", "painful", "neutral")


def default_scenario() -> dict:
    return {
        "id": "scenario-praise-eye",
        "title": "赞美在耳门出现",
        "description": "一位同伴公开赞美 Agent A；只记录可观察的声音、姿态和回应。",
        "primary_object": {
            "id": "obj-praise", "kind": "speech", "door": "ear",
            "value": "赞美：你这次的工作很有帮助。", "valence": "pleasant",
            "observable": True, "source_agent_id": "agent-b",
        },
        "context": {"language": "zh", "location": "shared-space", "time_index": 0},
        "observable_events": [],
    }


def default_agents() -> list[dict]:
    return [
        {
            "id": "agent-a", "label": "Agent A", "species": "human",
            "tendencies": {"lobha": 0.62, "dosa": 0.35, "moha": 0.48},
            "training": {"sati": 0.35, "sampajanna": 0.35, "sila": 0.45, "metta": 0.4, "panna": 0.25},
            "notes": "示例条件倾向，不是人格分数、诊断或资格判断。",
        },
        {
            "id": "agent-b", "label": "Agent B", "species": "human",
            "tendencies": {"lobha": 0.38, "dosa": 0.46, "moha": 0.42},
            "training": {"sati": 0.6, "sampajanna": 0.55, "sila": 0.58, "metta": 0.62, "panna": 0.42},
            "notes": "示例条件倾向，不是人格分数、诊断或资格判断。",
        },
    ]


def normalise_agent(agent: dict | None, index: int = 0) -> dict:
    source = agent or {}
    tendency = source.get("tendencies", {})
    training = source.get("training", {})

    def bounded(value, fallback):
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return fallback

    return {
        "id": source.get("id") or f"agent-{chr(97 + index)}",
        "label": source.get("label") or f"Agent {chr(65 + index)}",
        "species": source.get("species") if source.get("species") in {"human", "animal", "unknown"} else "unknown",
        "tendencies": {key: bounded(tendency.get(key), 0.5) for key in ("lobha", "dosa", "moha")},
        "training": {key: bounded(training.get(key), 0.5) for key in ("sati", "sampajanna", "sila", "metta", "panna")},
        "notes": source.get("notes") or "条件性建模资料；不构成诊断。",
    }


def normalise_scenario(scenario: dict | None) -> dict:
    source = scenario or default_scenario()
    obj = source.get("primary_object", {})
    if obj.get("door") not in DOORS:
        raise ValueError("Scenario.primary_object.door must be one of the six doors")
    if obj.get("valence") not in VALENCES:
        raise ValueError("Scenario.primary_object.valence is invalid")
    raw_observations = source.get("observations") or []
    observations = []
    for index, raw in enumerate(raw_observations[:6]):
        item = dict(raw or {})
        if item.get("door") not in DOORS or item.get("valence") not in VALENCES:
            raise ValueError(f"Scenario.observations[{index}] has an invalid door or valence")
        observations.append({
            "id": item.get("id") or f"object-{index + 1}", "kind": item.get("kind") or "unspecified",
            "door": item["door"], "value": "" if item.get("value") is None else str(item.get("value")),
            "valence": item["valence"], "observable": item.get("observable", True) is not False,
            "source_agent_id": item.get("source_agent_id"),
        })
    return {
        "id": source.get("id") or "scenario-untitled",
        "title": source.get("title") or "未命名情境",
        "description": source.get("description", ""),
        "primary_object": {
            "id": obj.get("id") or "object-1", "kind": obj.get("kind") or "unspecified",
            "door": obj["door"], "value": "" if obj.get("value") is None else str(obj.get("value")),
            "valence": obj["valence"], "observable": obj.get("observable", True) is not False,
            "source_agent_id": obj.get("source_agent_id"),
        },
        "context": deepcopy(source.get("context", {})),
        "observable_events": deepcopy(source.get("observable_events", [])),
        "observations": observations,
        "max_rounds": max(1, min(6, int(source.get("max_rounds", source.get("maxRounds", 1)) or 1))),
    }


def validate_input(request: dict | None) -> dict:
    source = request or {}
    model = source.get("modelVersion", CANONICAL)
    if model not in {CANONICAL, SYNTHESIS}:
        raise ValueError(f"Unknown modelVersion: {model}")
    raw_agents = source.get("agents") or default_agents()
    agents = [normalise_agent(agent, index) for index, agent in enumerate(raw_agents)]
    if not agents:
        raise ValueError("At least one agent is required")
    return {
        "modelVersion": model, "scenario": normalise_scenario(source.get("scenario")),
        "agents": agents, "interventions": deepcopy(source.get("interventions", {})),
        "seed": str(source.get("seed", 0)),
    }
