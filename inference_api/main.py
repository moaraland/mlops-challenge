from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

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

# Inicializa o logging antes de qualquer uso
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
        logger.info("Modelo carregado na inicialização: run_id=%s", rid)
    except Exception:
        logger.warning("Não foi possível carregar o modelo na inicialização; será tentado na primeira requisição.")

    yield

    logger.info("Encerrando a API de inferência.")


app = FastAPI(
    title="Inference API",
    version="1.1.0",
    description="API de tradução PT→EN baseada em SavedModel TensorFlow.",
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
    # HTTPException já é tratada pelo FastAPI — não interceptamos aqui
    if isinstance(exc, HTTPException):
        raise exc

    logger.exception("Erro interno não tratado em %s %s", request.method, request.url.path)
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
    return ModelResponse(run_id=manager.current_run_id())


@app.get("/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    """Retorna os contadores de métricas da aplicação.

    Returns:
        MetricsResponse com requests_total, errors_total e translations_total.
    """
    return MetricsResponse(**metrics.to_dict())


@app.post("/reload", response_model=ReloadResponse)
def reload_model(req: ReloadRequest) -> ReloadResponse:
    """Recarrega o modelo a partir do run_id e artifacts_dir fornecidos ou configurados.

    Quando ``run_id`` é enviado, esse modelo é carregado diretamente.
    Quando ``artifacts_dir`` é enviado, busca o modelo nesse diretório alternativo.
    Sem body, utiliza os valores configurados nas variáveis de ambiente.

    Args:
        req: Corpo opcional com ``run_id`` e/ou ``artifacts_dir``.

    Returns:
        ReloadResponse com status e run_id do modelo recém-carregado.

    Raises:
        HTTPException: 500 se ocorrer qualquer erro durante a recarga.
    """
    try:
        # Determina o artifacts_dir efetivo para esta operação
        effective_dir = req.artifacts_dir or str(manager.artifacts_dir)
        target_manager = (
            ModelManager(artifacts_dir=effective_dir, default_run_id=manager.default_run_id)
            if req.artifacts_dir
            else manager
        )
        rid = target_manager.load(run_id=req.run_id or None)

        # Se usou um manager temporário, propaga o modelo carregado para o manager principal
        if req.artifacts_dir:
            with manager._lock:
                manager._translator = target_manager._translator
                manager._run_id = target_manager._run_id

        logger.info("Modelo recarregado via /reload: run_id=%s", rid)
        return ReloadResponse(status="reloaded", run_id=rid)
    except Exception as exc:
        logger.exception("Falha ao recarregar o modelo via /reload")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    """Traduz um texto de português para inglês.

    Args:
        req: PredictRequest contendo o texto a ser traduzido.

    Returns:
        PredictResponse com a tradução, run_id e latência em ms.

    Raises:
        HTTPException: 503 se o modelo não estiver disponível; 500 para outros erros.
    """
    metrics.increment_requests()
    start = time.monotonic()

    try:
        translation, rid = manager.translate(req.text)
    except FileNotFoundError as exc:
        metrics.increment_errors()
        logger.warning("Modelo indisponível durante /predict: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        metrics.increment_errors()
        logger.exception("Erro inesperado durante /predict")
        raise HTTPException(status_code=500, detail=str(exc))

    latency_ms = (time.monotonic() - start) * 1000
    metrics.increment_translations()
    logger.info("Tradução concluída: run_id=%s latency_ms=%.2f", rid, latency_ms)

    return PredictResponse(translation=translation, run_id=rid, latency_ms=latency_ms)
