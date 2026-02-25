from __future__ import annotations

import logging
import sys


class StructuredFormatter(logging.Formatter):
    """Formatador de log com campos estruturados no estilo JSON-like.

    Produz linhas no formato:
        time=<iso> level=<LEVEL> logger=<name> message=<msg> [extra=<extras>]
    """

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro de log em uma string estruturada.

        Args:
            record: O objeto LogRecord a ser formatado.

        Returns:
            String formatada com os campos estruturados.
        """
        base = (
            f"time={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} "
            f"level={record.levelname} "
            f"logger={record.name} "
            f"message={record.getMessage()}"
        )

        # Adiciona campos extras, se presentes
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "taskName",
            )
        }

        if extras:
            extras_str = " ".join(f"{k}={v}" for k, v in extras.items())
            base = f"{base} {extras_str}"

        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"

        return base


def setup_logging(level: int = logging.INFO) -> None:
    """Configura o logging raiz com o formatador estruturado.

    Deve ser chamado uma única vez na inicialização da aplicação.

    Args:
        level: Nível de log desejado (padrão: logging.INFO).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Evita duplicação de handlers em re-inicializações (ex.: testes)
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers.clear()
        root_logger.addHandler(handler)

