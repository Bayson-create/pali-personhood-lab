"""Dependency-free deterministic mirror of docs/personhood/engine.js."""
from __future__ import annotations

from copy import deepcopy

from .evidence import has_evidence
from .schema import CANONICAL, SCHEMA_VERSION, SYNTHESIS, validate_input


def _round(value: float) -> float:
    return round(value, 3)


def _intervention(interventions: dict, agent_id: str) -> dict:
    value = interventions.get(agent_id, {}) if isinstance(interventions, dict) else {}
    return {"pause": value} if isinstance(value, bool) else (value or {})


def _tendency(agent: dict, valence: str) -> float:
    return agent["tendencies"][{"pleasant": "lobha", "painful": "dosa", "neutral": "moha"}[valence]]


def _training(agent: dict, intervention: dict) -> float:
    t = agent["training"]
    value = t["sati"] * .30 + t["sampajanna"] * .20 + t["sila"] * .15 + t["metta"] * .15 + t["panna"] * .20
    value += .16 if intervention.get("mindfulness") else 0
    value += .12 if intervention.get("pause") else 0
    value += .10 if intervention.get("metta") else 0
    value += .10 if intervention.get("restraint") else 0
    return min(1.0, value)


def _conditions(agent: dict, scenario: dict) -> dict:
    obj = scenario["primary_object"]
    return {
        "door": obj["door"], "object_id": obj["id"], "object_kind": obj["kind"], "object_value": obj["value"],
        "consciousness": f'{agent["id"]}:consciousness-at-{obj["door"]}',
        "contact_formula": "root + object + consciousness", "shared_object": obj["observable"] is True,
        "uncertainty": "animal-inner-experience-uncertain" if agent["species"] == "animal" else None,
    }


def _event(agent: dict, index: int, kind: str, phase: str, conditions: dict, aggregates: dict,
           action, branch, evidence_ids: list[str], **extra) -> dict:
    result = {
        "id": f'{agent["id"]}:e{index + 1:02d}:{kind}', "actor_id": agent["id"], "step": index + 1,
        "phase": phase, "kind": kind, "conditions": conditions, "aggregates": aggregates,
        "action": action, "branch": branch, "evidence_ids": evidence_ids,
        "uncertainty": conditions.get("uncertainty"),
    }
    result.update(extra)
    return result


def _action(scenario: dict, branch: str, intervention: dict) -> dict:
    value = scenario["primary_object"]["value"]
    if branch == "trained":
        if intervention.get("pause"):
            return {"type": "pause", "observable": True, "text": "暂停并保持可观察的安静"}
        if intervention.get("metta"):
            return {"type": "kind-speech", "observable": True, "text": "以善意、不过度取著的方式回应"}
        return {"type": "restrained-response", "observable": True, "text": "先觉察再作适当回应"}
    if scenario["primary_object"]["valence"] == "pleasant":
        return {"type": "appropriating-speech", "observable": True, "text": "追逐更多赞许：" + value}
    if scenario["primary_object"]["valence"] == "painful":
        return {"type": "aversive-speech", "observable": True, "text": "以防卫或反击回应：" + value}
    return {"type": "confused-action", "observable": True, "text": "在不明了中作出惯性回应：" + value}


def _agent_trace(agent: dict, request: dict) -> dict:
    scenario = request["scenario"]
    obj = scenario["primary_object"]
    intervention = _intervention(request["interventions"], agent["id"])
    reactivity = _tendency(agent, obj["valence"])
    training = _training(agent, intervention)
    branch = "untrained" if reactivity > training else "trained"
    conditions = _conditions(agent, scenario)
    aggregates = {"form": "body-and-object", "feeling": obj["valence"], "perception": "recognition-of-" + obj["kind"], "formations": "conditional-intention", "consciousness": conditions["consciousness"]}
    events, index = [], 0
    events.append(_event(agent, index, "contact", "arising", conditions, aggregates, None, None, ["sn35.23", "sn12.23"], statement="门、所缘与识共同构成可观察的接触条件。")); index += 1
    events.append(_event(agent, index, "coarising-aggregates", "arising", conditions, aggregates, None, None, ["sn22.59"], statement="五蕴以共同生起的条件聚合显示；不是固定人格实体。")); index += 1
    events.append(_event(agent, index, "feeling", "arising", conditions, aggregates, None, None, ["sn12.23", "sn22.59"], statement="受依触而起，标为乐、苦或不苦不乐。")); index += 1
    events.append(_event(agent, index, "perception-and-thought", "elaboration", conditions, aggregates, None, None, ["mn18"], statement="想与寻思可进一步展开为戏论；这不是所有心过程的物理时间序列。")); index += 1
    if request["modelVersion"] == SYNTHESIS:
        events.append(_event(agent, index, "citta-vithi-view", "interpretive", conditions, aggregates, None, None, ["abhidhamma.citta-vithi"], layer="abhidhamma", interpretation_status="later-systematisation", statement="后期上座部分析视图：以心路、随眠或速行等术语补充解释。")); index += 1
    if branch == "untrained":
        events.append(_event(agent, index, "craving", "conditioning", conditions, aggregates, None, branch, ["sn12.23"], statement="受缘爱：反应循环继续。")); index += 1
        events.append(_event(agent, index, "clinging-and-becoming", "conditioning", conditions, aggregates, None, branch, ["sn12.23"], statement="取与有在本模拟中表示局部反应模式的加深，不是永久自我。")); index += 1
    else:
        events.append(_event(agent, index, "mindfulness-and-clear-comprehension", "intervention", conditions, aggregates, None, branch, ["mn10", "dn22"], statement="正念、明觉、戒护或暂停改变后续条件。")); index += 1
        events.append(_event(agent, index, "non-clinging", "cessation", conditions, aggregates, None, branch, ["dn22", "sn12.23"], statement="局部爱取反应链在当前情境中止息；不表示涅槃或证悟。")); index += 1
    events.append(_event(agent, index, "observable-action", "expression", conditions, aggregates, _action(scenario, branch, intervention), branch, ["mn10"] if branch == "trained" else ["sn12.23"], statement="只有动作、言语、姿态等外化结果可进入交互交换。"))
    return {"agent_id": agent["id"], "agent_label": agent["label"], "species": agent["species"], "tendency_used": _round(reactivity), "training_available": _round(training), "branch": branch, "intervention": deepcopy(intervention), "events": events, "caveats": ["动物内在经验不可由此读心；只模拟共享刺激与可观察反馈。"] if agent["species"] == "animal" else []}


def validate_trace(trace: dict) -> dict:
    errors: list[str] = []
    agent_ids = {agent["id"] for agent in trace.get("agents", [])}
    events_checked = 0
    for stream in trace.get("streams", []):
        events_checked += len(stream.get("events", []))
        if stream.get("agent_id") not in agent_ids:
            errors.append("stream actor missing: " + str(stream.get("agent_id")))
        for item in stream.get("events", []):
            if item.get("actor_id") != stream.get("agent_id"):
                errors.append("event actor does not match stream: " + item.get("id", ""))
            for evidence_id in item.get("evidence_ids", []):
                if not has_evidence(evidence_id):
                    errors.append("unresolved evidence: " + evidence_id)
            if item.get("kind") == "contact":
                conditions = item.get("conditions", {})
                if not all(conditions.get(key) for key in ("door", "object_id", "consciousness")):
                    errors.append("contact lacks door/object/consciousness: " + item.get("id", ""))
            if item.get("observed_internal_state") or item.get("accessed_agent_state"):
                errors.append("internal-state leakage: " + item.get("id", ""))
    for edge in trace.get("observable_edges", []):
        if edge.get("accessible_state") != "observable-action-only":
            errors.append("edge exposes non-observable state")
        if edge.get("from_agent_id") == edge.get("to_agent_id"):
            errors.append("self interaction edge")
    if trace.get("model_version") not in {CANONICAL, SYNTHESIS}:
        errors.append("invalid model version")
    return {"ok": not errors, "errors": errors, "checked_events": events_checked}


def run_episode(request: dict | None = None) -> dict:
    source = validate_input(request)
    streams = [_agent_trace(agent, source) for agent in source["agents"]]
    edges = []
    for stream in streams:
        actions = [item for item in stream["events"] if item["kind"] == "observable-action"]
        if not actions:
            continue
        for other in source["agents"]:
            if other["id"] == stream["agent_id"]:
                continue
            action = actions[0]
            edges.append({"from_agent_id": stream["agent_id"], "to_agent_id": other["id"], "kind": "observable-feedback", "source_event_id": action["id"], "value": action["action"]["text"], "accessible_state": "observable-action-only"})
    trace = {"schema_version": SCHEMA_VERSION, "trace_kind": "InteractionTrace" if len(source["agents"]) > 1 else "EpisodeTrace", "model_version": source["modelVersion"], "seed": source["seed"], "scenario": source["scenario"], "agents": source["agents"], "streams": streams, "observable_edges": edges, "evidence_manifest_version": "personhood-evidence/2026-08-12", "interpretation_notes": ["新增的 citta-vīthi 视图属于后期系统化解释，已逐事件标记。"] if source["modelVersion"] == SYNTHESIS else ["本版本以经藏/律藏核心为准；不把五蕴写成线性实体或固定人格。"], "forbidden_claims": ["nibbana-simulation", "enlightenment-certification", "clinical-diagnosis", "animal-mind-reading"]}
    validation = validate_trace(trace)
    if not validation["ok"]:
        raise ValueError("Trace validation failed: " + "; ".join(validation["errors"]))
    trace["validation"] = validation
    return trace


def _namespace_round(trace: dict, round_index: int) -> tuple[list[dict], list[dict]]:
    """Give each round stable, collision-free event and edge identifiers."""
    prefix = f"r{round_index}:"
    streams = []
    event_ids: dict[str, str] = {}
    for stream in trace.get("streams", []):
        events = []
        for event in stream.get("events", []):
            copied = deepcopy(event)
            old_id = copied["id"]
            copied["id"] = prefix + old_id
            event_ids[old_id] = copied["id"]
            copied["round_index"] = round_index
            events.append(copied)
        streams.append({**deepcopy(stream), "events": events, "round_index": round_index})
    edges = []
    for edge in trace.get("observable_edges", []):
        copied = deepcopy(edge)
        copied["source_event_id"] = event_ids.get(copied.get("source_event_id"), prefix + str(copied.get("source_event_id")))
        copied["round_index"] = round_index
        edges.append(copied)
    return streams, edges


def run_interaction(request: dict | None = None) -> dict:
    """Run a bounded interaction over observable conditions only.

    If ``scenario.observations`` is supplied, each item is the next shared
    object. Otherwise the first agent's observable action becomes the next
    neutral speech object. Private states never cross the round boundary.
    """
    source = validate_input(request)
    scenario = source["scenario"]
    raw_request = request or {}
    requested_rounds = raw_request.get("maxRounds", raw_request.get("max_rounds", scenario.get("max_rounds", 1)))
    try:
        max_rounds = max(1, min(6, int(requested_rounds)))
    except (TypeError, ValueError):
        max_rounds = 1
    supplied = list(scenario.get("observations") or [])
    current_object = supplied[0] if supplied else scenario["primary_object"]
    rounds: list[dict] = []
    streams: list[dict] = []
    edges: list[dict] = []
    for round_index in range(1, max_rounds + 1):
        round_scenario = deepcopy(scenario)
        round_scenario["id"] = f'{scenario["id"]}:round-{round_index}'
        round_scenario["primary_object"] = deepcopy(current_object)
        round_scenario["observations"] = []
        round_request = {
            "modelVersion": source["modelVersion"], "scenario": round_scenario,
            "agents": deepcopy(source["agents"]), "interventions": deepcopy(source["interventions"]),
            "seed": f'{source["seed"]}:round-{round_index}',
        }
        round_trace = run_episode(round_request)
        round_trace["round_index"] = round_index
        rounds.append(round_trace)
        round_streams, round_edges = _namespace_round(round_trace, round_index)
        streams.extend(round_streams)
        edges.extend(round_edges)
        if round_index >= max_rounds:
            break
        if round_index < len(supplied):
            current_object = supplied[round_index]
            continue
        if supplied:
            break
        actions = [event for stream in round_trace["streams"] for event in stream["events"] if event["kind"] == "observable-action" and event.get("action", {}).get("observable")]
        if not actions:
            break
        action = actions[0]
        current_object = {
            "id": f"feedback-{round_index + 1}", "kind": "speech", "door": "ear",
            "value": action["action"]["text"], "valence": "neutral", "observable": True,
            "source_agent_id": action["actor_id"],
        }
    combined = {
        "schema_version": SCHEMA_VERSION, "trace_kind": "InteractionTrace",
        "model_version": source["modelVersion"], "seed": source["seed"],
        "scenario": source["scenario"], "agents": source["agents"],
        "streams": streams, "observable_edges": edges, "rounds": rounds,
        "evidence_manifest_version": "personhood-evidence/2026-08-12",
        "interaction_limits": {"max_rounds": 6, "rounds_completed": len(rounds), "private_state_shared": False},
        "interpretation_notes": ["每一轮只把外化的言语、动作、姿态或共同环境作为下一轮所缘。"],
        "forbidden_claims": ["nibbana-simulation", "enlightenment-certification", "clinical-diagnosis", "animal-mind-reading"],
    }
    validation = validate_trace(combined)
    if not validation["ok"]:
        raise ValueError("Interaction trace validation failed: " + "; ".join(validation["errors"]))
    combined["validation"] = validation
    return combined
