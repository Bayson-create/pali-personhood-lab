from personhood.engine import run_interaction


def test_standalone_engine_is_deterministic_and_bounded():
    request = {
        "modelVersion": "pali-canonical/v1",
        "scenario": {
            "id": "ci-two-rounds",
            "primary_object": {"id": "o1", "kind": "speech", "door": "ear", "value": "赞美", "valence": "pleasant"},
            "observations": [{"id": "o1", "kind": "speech", "door": "ear", "value": "赞美", "valence": "pleasant"}, {"id": "o2", "kind": "speech", "door": "ear", "value": "回应", "valence": "neutral"}],
        },
        "agents": [{"id": "agent-a", "species": "human"}, {"id": "agent-b", "species": "human"}],
        "seed": "ci",
        "maxRounds": 2,
    }
    first = run_interaction(request)
    assert first == run_interaction(request)
    assert len(first["rounds"]) == 2
    assert first["interaction_limits"]["private_state_shared"] is False
    assert first["validation"]["ok"] is True
