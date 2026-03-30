import json
from pathlib import Path

from fastapi.testclient import TestClient

import inference_api.main as main_module
from inference_api.main import app
from inference_api.model_manager import ModelManager

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    """Cria um TestClient sem acionar o lifespan (model load)."""
    return TestClient(app, raise_server_exceptions=False)


def _write_published_artifact(artifacts_dir: Path, run_id: str) -> Path:
    run_dir = artifacts_dir / "published" / run_id
    saved_model_dir = run_dir / "saved_model"
    saved_model_dir.mkdir(parents=True)
    metadata = {
        "run_id": run_id,
        "git_sha": "abc1234",
        "published_at": "2026-03-29T12:00:00+00:00",
        "artifact_stage": "published",
        "export_dir": str(saved_model_dir),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return saved_model_dir


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


def test_metrics_endpoint_returns_prometheus_text():
    """GET /metrics deve retornar o formato de exposição do Prometheus."""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "requests_total" in r.text
    assert "errors_total" in r.text
    assert "translations_total" in r.text


def test_metrics_json_endpoint_returns_counters():
    """GET /metrics/json deve retornar os contadores esperados em JSON."""
    client = TestClient(app)
    r = client.get("/metrics/json")
    assert r.status_code == 200
    body = r.json()
    assert "requests_total" in body
    assert "errors_total" in body
    assert "translations_total" in body
    assert isinstance(body["requests_total"], int)
    assert isinstance(body["errors_total"], int)
    assert isinstance(body["translations_total"], int)


def test_metrics_increments_on_predict():
    """POST /predict deve incrementar requests_total e errors_total nas métricas JSON."""
    client = TestClient(app)

    before = client.get("/metrics/json").json()
    client.post("/predict", json={"text": "teste"})
    after = client.get("/metrics/json").json()

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


def test_reload_uses_published_artifacts_and_returns_metadata(tmp_path, monkeypatch):
    """POST /reload deve carregar de artifacts/published/<run_id> e expor lineage."""
    run_id = "nmt_test"
    expected_export_dir = _write_published_artifact(tmp_path, run_id)
    load_calls: list[Path] = []

    def fake_load_saved_model(self, export_dir: Path):
        load_calls.append(export_dir)
        return object()

    test_manager = ModelManager(str(tmp_path), default_run_id="")
    monkeypatch.setattr(ModelManager, "_load_saved_model", fake_load_saved_model)
    monkeypatch.setattr(main_module, "manager", test_manager)

    client = TestClient(main_module.app)
    response = client.post("/reload", json={"run_id": run_id})

    assert response.status_code == 200
    assert load_calls == [expected_export_dir]
    body = response.json()
    assert body["run_id"] == run_id
    assert body["git_sha"] == "abc1234"
    assert body["published_at"] == "2026-03-29T12:00:00+00:00"
    assert body["artifact_path"] == str(expected_export_dir)


def test_model_endpoint_exposes_loaded_model_metadata(tmp_path, monkeypatch):
    """GET /model deve refletir os metadados do artefato publicado carregado."""
    run_id = "nmt_test_model"
    _write_published_artifact(tmp_path, run_id)

    def fake_load_saved_model(self, export_dir: Path):
        return object()

    test_manager = ModelManager(str(tmp_path), default_run_id="")
    monkeypatch.setattr(ModelManager, "_load_saved_model", fake_load_saved_model)
    monkeypatch.setattr(main_module, "manager", test_manager)

    client = TestClient(main_module.app)
    reload_response = client.post("/reload", json={"run_id": run_id})
    assert reload_response.status_code == 200

    model_response = client.get("/model")
    assert model_response.status_code == 200
    body = model_response.json()
    assert body["run_id"] == run_id
    assert body["git_sha"] == "abc1234"
    assert (
        body["artifact_path"].endswith(f"published\\{run_id}\\saved_model")
        or body["artifact_path"].endswith(f"published/{run_id}/saved_model")
    )
