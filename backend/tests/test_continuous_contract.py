from personhood.engine import run_interaction


def test_two_agent_observable_only_continuous_trace():
    request = {
        "modelVersion": "pali-canonical/v1",
        "seed": "two-agent",
        "maxRounds": 2,
        "scenario": {
            "id": "two-agent", "title": "可观察言语", "primary_object": {
                "id": "speech", "kind": "speech", "door": "ear", "value": "一句可观察的话", "valence": "painful", "observable": True
            },
        },
        "agents": [
            {"id": "agent-a", "label": "甲", "species": "human"},
            {"id": "agent-b", "label": "乙", "species": "human"},
        ],
    }
    trace = run_interaction(request)
    assert trace["validation"]["ok"] is True
    assert trace["interaction_limits"]["private_state_shared"] is False
    assert all(edge["accessible_state"] == "observable-action-only" for edge in trace["observable_edges"])
