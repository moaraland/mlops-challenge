from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Corpo da requisição de tradução.

    Attributes:
        text: Texto em português a ser traduzido (entre 1 e 512 caracteres).
    """

    text: str = Field(..., min_length=1, max_length=512, description="Entrada em português")


class PredictResponse(BaseModel):
    """Corpo da resposta de tradução.

    Attributes:
        translation: Texto traduzido para o inglês.
        run_id: Identificador do modelo utilizado.
        latency_ms: Latência da inferência em milissegundos.
    """

    translation: str
    run_id: str
    latency_ms: float = Field(..., description="Latência da inferência em milissegundos")


class HealthResponse(BaseModel):
    """Corpo da resposta de saúde da API.

    Attributes:
        status: Estado geral da API (ex.: 'ok').
        run_id: Identificador do modelo atualmente carregado, ou None.
        model_loaded: Indica se o modelo está carregado e pronto para inferência.
    """

    status: str
    run_id: str | None = None
    model_loaded: bool = False


class ModelResponse(BaseModel):
    """Corpo da resposta do endpoint de consulta do modelo ativo.

    Attributes:
        run_id: Identificador do modelo atualmente carregado, ou None.
    """

    run_id: str | None = None


class MetricsResponse(BaseModel):
    """Corpo da resposta do endpoint de métricas.

    Attributes:
        requests_total: Total de requisições recebidas no endpoint /predict.
        errors_total: Total de erros retornados pelo endpoint /predict.
        translations_total: Total de traduções realizadas com sucesso.
    """

    requests_total: int = Field(..., description="Total de requisições recebidas.")
    errors_total: int = Field(..., description="Total de erros retornados.")
    translations_total: int = Field(..., description="Total de traduções bem-sucedidas.")


class ReloadRequest(BaseModel):
    """Corpo opcional da requisição de recarga de modelo.

    Permite especificar qual run_id carregar sem alterar as variáveis
    de ambiente da aplicação.

    Attributes:
        run_id: run_id específico a carregar. Se omitido, usa DEFAULT_RUN_ID.
        artifacts_dir: Diretório alternativo de artefatos. Se omitido, usa o configurado.
    """

    run_id: str | None = Field(
        default=None,
        description="run_id do modelo a carregar.",
    )
    artifacts_dir: str | None = Field(
        default='/artifacts',
        description="Diretório alternativo de artefatos (ex.: '/artifacts').",
    )

    # preprocessamento artifacts_dir remove trailing slash para evitar problemas de path
    def __init__(self, **data):
        super().__init__(**data)
        if self.artifacts_dir:
            self.artifacts_dir = self.artifacts_dir.rstrip('/')


class ReloadResponse(BaseModel):
    """Corpo da resposta do endpoint de recarga de modelo.

    Attributes:
        status: Resultado da operação (ex.: 'reloaded').
        run_id: Identificador do modelo recém-carregado, ou None.
    """

    status: str
    run_id: str | None = None
