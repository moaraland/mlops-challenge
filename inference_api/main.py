from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from inference_api.logging_config import setup_logging
from inference_api.metrics import metrics
from inference_api.model_manager import ModelManager
from inference_api.schemas import (
    HealthResponse,
    MetricsResponse,
    ModelResponse,
    PredictRequest,
    PredictResponse,
    ReloadRequest,
    ReloadResponse,
)

setup_logging()

logger = logging.getLogger(__name__)


def get_env(name: str, default: str = "") -> str:
    """Lê uma variável de ambiente com valor padrão.

    Args:
        name: Nome da variável de ambiente.
        default: Valor padrão caso a variável esteja ausente ou vazia.

    Returns:
        Valor da variável ou o padrão fornecido.
    """
    value = os.getenv(name)
    return value if value not in (None, "") else default


manager = ModelManager(
    artifacts_dir=get_env("ARTIFACTS_DIR", "artifacts"),
    default_run_id=get_env("DEFAULT_RUN_ID", ""),
)


def _build_model_response() -> ModelResponse:
    """Serializa o estado atual do modelo carregado."""
    info = manager.current_model_info()
    if info is None:
        return ModelResponse(run_id=manager.current_run_id())

    return ModelResponse(
        run_id=info.run_id,
        git_sha=info.git_sha,
        published_at=info.published_at,
        artifact_path=info.artifact_path,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia o ciclo de vida da aplicação FastAPI.

    Realiza a carga inicial do modelo na inicialização e registra o
    encerramento da aplicação.

    Args:
        app: Instância da aplicação FastAPI.

    Yields:
        Controle para a aplicação durante seu tempo de vida.
    """
    logger.info("Iniciando a API de inferência...")
    try:
        rid = manager.load()
        info = manager.current_model_info()
        logger.info(
            "Modelo carregado na inicialização: run_id=%s git_sha=%s artifact_path=%s",
            rid,
            info.git_sha if info else None,
            info.artifact_path if info else None,
        )
    except Exception:
        logger.warning(
            "Não foi possível carregar o modelo na inicialização; será tentado na primeira requisição."
        )

    yield

    logger.info("Encerrando a API de inferência.")


app = FastAPI(
    title="Inference API",
    version="1.1.0",
    description="API de tradução EN→PT baseada em SavedModel TensorFlow.",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler global para exceções não tratadas.

    Captura qualquer exceção que não tenha sido tratada pelos endpoints
    e retorna uma resposta 500 padronizada.

    Args:
        request: Objeto de requisição do FastAPI.
        exc: Exceção capturada.

    Returns:
        JSONResponse com status 500 e detalhe do erro.
    """

    if isinstance(exc, HTTPException):
        raise exc

    logger.exception(
        "Erro interno não tratado em %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor."},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Verifica o estado de saúde da API.

    Returns:
        HealthResponse com status, run_id e indicador de modelo carregado.
    """
    return HealthResponse(
        status="ok",
        run_id=manager.current_run_id(),
        model_loaded=manager.is_loaded(),
    )


@app.get("/model", response_model=ModelResponse)
def model() -> ModelResponse:
    """Retorna o run_id do modelo atualmente ativo.

    Returns:
        ModelResponse com o campo run_id.
    """
    return _build_model_response()


@app.get("/metrics")
def get_metrics() -> Response:
    """Expõe métricas no formato de scrape do Prometheus."""
    return Response(
        content=metrics.render_prometheus(),
        media_type=metrics.content_type,
    )


@app.get("/metrics/json", response_model=MetricsResponse)
def get_metrics_json() -> MetricsResponse:
    """Retorna os contadores de métricas da aplicação em JSON."""
    return MetricsResponse(**metrics.to_dict())


@app.post("/reload", response_model=ReloadResponse)
def reload_model(req: ReloadRequest) -> ReloadResponse:
    """Recarrega o modelo a partir do run_id e artifacts_dir fornecidos ou configurados.

    Args:
        req: Corpo opcional com ``run_id`` e/ou ``artifacts_dir``.

    Returns:
        ReloadResponse com status e run_id do modelo recém-carregado.
    """
    try:
        target_manager = (
            ModelManager(
                artifacts_dir=req.artifacts_dir,
                default_run_id=manager.default_run_id,
            )
            if req.artifacts_dir
            else manager
        )
        rid = target_manager.load(run_id=req.run_id or None)

        if req.artifacts_dir:
            manager.adopt_loaded_state(target_manager)

        info = (
            manager.current_model_info()
            if req.artifacts_dir
            else target_manager.current_model_info()
        )
        logger.info(
            "Modelo recarregado via /reload: run_id=%s git_sha=%s published_at=%s artifact_path=%s",
            rid,
            info.git_sha if info else None,
            info.published_at if info else None,
            info.artifact_path if info else None,
        )
        return ReloadResponse(
            status="reloaded",
            run_id=rid,
            git_sha=info.git_sha if info else None,
            published_at=info.published_at if info else None,
            artifact_path=info.artifact_path if info else None,
        )
    except Exception as exc:
        logger.exception("Falha ao recarregar o modelo via /reload")

        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    """Traduz um texto de inglês para português.

    Args:
        req: PredictRequest contendo o texto a ser traduzido.

    Returns:
        PredictResponse com a tradução, run_id e latência em ms.
    """
    metrics.increment_requests()
    start = time.monotonic()

    try:
        translation, rid = manager.translate(req.text)
    except FileNotFoundError as exc:
        metrics.increment_errors()
        logger.warning("Modelo indisponível durante /predict: %s", exc)

        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        metrics.increment_errors()
        logger.exception("Erro inesperado durante /predict")

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency_ms = (time.monotonic() - start) * 1000
    metrics.increment_translations()
    logger.info("Tradução concluída: run_id=%s latency_ms=%.2f", rid, latency_ms)

    return PredictResponse(translation=translation, run_id=rid, latency_ms=latency_ms)
