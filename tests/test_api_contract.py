from fastapi.testclient import TestClient

from inference_api.main import app


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _client() -> TestClient:
    """Cria um TestClient sem acionar o lifespan (model load)."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """GET /health deve retornar 200 com campo status='ok'."""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "run_id" in body


def test_health_has_model_loaded_field():
    """GET /health deve incluir o campo booleano model_loaded."""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "model_loaded" in body
    assert isinstance(body["model_loaded"], bool)


# ---------------------------------------------------------------------------
# /predict
# ---------------------------------------------------------------------------

def test_predict_without_model_returns_503_or_500():
    """POST /predict sem modelo carregado deve retornar 503 ou 500."""
    client = TestClient(app)
    r = client.post("/predict", json={"text": "olá"})
    assert r.status_code in (503, 500)


def test_predict_validates_empty_text():
    """POST /predict com texto vazio deve retornar 422 (validação Pydantic)."""
    client = TestClient(app)
    r = client.post("/predict", json={"text": ""})
    assert r.status_code == 422


def test_predict_validates_max_length():
    """POST /predict com texto acima de 512 caracteres deve retornar 422."""
    client = TestClient(app)
    long_text = "a" * 513
    r = client.post("/predict", json={"text": long_text})
    assert r.status_code == 422


def test_predict_missing_text_field_returns_422():
    """POST /predict sem o campo 'text' deve retornar 422."""
    client = TestClient(app)
    r = client.post("/predict", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_counters():
    """GET /metrics deve retornar os três contadores esperados."""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "requests_total" in body
    assert "errors_total" in body
    assert "translations_total" in body
    assert isinstance(body["requests_total"], int)
    assert isinstance(body["errors_total"], int)
    assert isinstance(body["translations_total"], int)


def test_metrics_increments_on_predict():
    """POST /predict deve incrementar requests_total e errors_total nas métricas."""
    client = TestClient(app)

    before = client.get("/metrics").json()
    client.post("/predict", json={"text": "teste"})
    after = client.get("/metrics").json()

    assert after["requests_total"] >= before["requests_total"] + 1
    # Sem modelo carregado, errors_total também deve ter incrementado
    assert after["errors_total"] >= before["errors_total"] + 1


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------

def test_model_endpoint_returns_run_id():
    """GET /model deve retornar o campo run_id."""
    client = TestClient(app)
    r = client.get("/model")
    assert r.status_code == 200
    assert "run_id" in r.json()
