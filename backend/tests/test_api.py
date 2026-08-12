from fastapi.testclient import TestClient

from api import app


def test_health_and_episode_contract():
    client = TestClient(app)
    assert client.get('/healthz').json()['status'] == 'ok'
    response = client.post('/api/personhood/episodes', json={"seed": "api"})
    assert response.status_code == 200
    body = response.json()
    assert body['persisted'] is False
    assert body['trace']['validation']['ok'] is True


def test_explain_is_deterministic_fallback():
    body = {"seed": "api", "question": "为什么这里止息？"}
    response = TestClient(app).post('/api/personhood/explain', json=body)
    assert response.status_code == 200
    assert response.json()['explanation']['ai']['degraded'] is True
