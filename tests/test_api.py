from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get('/v1/health')
    assert response.status_code == 200
    assert response.json()['version'] == '6.4.0'


def test_internal_endpoint_is_protected():
    client = TestClient(app)
    response = client.post('/v1/triage/internal', json={'complaint_text': 'mal de tête'})
    assert response.status_code == 403
