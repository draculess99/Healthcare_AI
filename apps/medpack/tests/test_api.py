import json
from backend.server import app

def test_api_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data.decode("utf-8"))
    assert data["status"] == "ok"
    assert data["service"] == "MedPack AI backend"
    
def test_api_data_sources():
    client = app.test_client()
    response = client.get("/api/data-sources")
    assert response.status_code == 200
    data = json.loads(response.data.decode("utf-8"))
    assert data["project"] == "MedPack AI / MedAIM"
