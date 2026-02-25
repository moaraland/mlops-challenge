from __future__ import annotations

import threading
from typing import Dict


class AppMetrics:
    """Contadores de métricas da aplicação, thread-safe.

    Attributes:
        requests_total: Total de requisições recebidas no endpoint /predict.
        errors_total: Total de erros retornados pelo endpoint /predict.
        translations_total: Total de traduções realizadas com sucesso.
    """

    def __init__(self) -> None:
        """Inicializa os contadores zerados e o lock de thread."""
        self._lock = threading.Lock()
        self.requests_total: int = 0
        self.errors_total: int = 0
        self.translations_total: int = 0

    def increment_requests(self) -> None:
        """Incrementa o contador de requisições recebidas."""
        with self._lock:
            self.requests_total += 1

    def increment_errors(self) -> None:
        """Incrementa o contador de erros."""
        with self._lock:
            self.errors_total += 1

    def increment_translations(self) -> None:
        """Incrementa o contador de traduções bem-sucedidas."""
        with self._lock:
            self.translations_total += 1

    def to_dict(self) -> Dict[str, int]:
        """Serializa os contadores em um dicionário.

        Returns:
            Dicionário com os valores atuais dos contadores.
        """
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "translations_total": self.translations_total,
            }


# Instância singleton compartilhada pela aplicação
metrics = AppMetrics()

