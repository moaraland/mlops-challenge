from __future__ import annotations

from typing import Dict

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)


class AppMetrics:
    """Contadores de métricas da aplicação, thread-safe via prometheus_client.

    Attributes:
        _requests: Contador de requisições recebidas no endpoint /predict.
        _errors: Contador de erros retornados pelo endpoint /predict.
        _translations: Contador de traduções realizadas com sucesso.
    """

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._requests = Counter(
            "requests",
            "Total de requisições recebidas no endpoint /predict.",
            registry=self._registry,
        )
        self._errors = Counter(
            "errors",
            "Total de erros retornados pelo endpoint /predict.",
            registry=self._registry,
        )
        self._translations = Counter(
            "translations",
            "Total de traduções realizadas com sucesso.",
            registry=self._registry,
        )

    def increment_requests(self) -> None:
        """Incrementa o contador de requisições recebidas."""
        self._requests.inc()

    def increment_errors(self) -> None:
        """Incrementa o contador de erros."""
        self._errors.inc()

    def increment_translations(self) -> None:
        """Incrementa o contador de traduções bem-sucedidas."""
        self._translations.inc()

    def to_dict(self) -> Dict[str, int]:
        """Serializa os contadores em um dicionário.

        Returns:
            Dicionário com os valores atuais dos contadores.
        """

        def _get(name: str) -> int:
            return int(self._registry.get_sample_value(name) or 0)

        return {
            "requests_total": _get("requests_total"),
            "errors_total": _get("errors_total"),
            "translations_total": _get("translations_total"),
        }

    def render_prometheus(self) -> bytes:
        """Serializa as métricas no formato de exposição do Prometheus."""
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        """Content-Type esperado pelo Prometheus."""
        return CONTENT_TYPE_LATEST


# Instância singleton compartilhada pela aplicação
metrics = AppMetrics()
