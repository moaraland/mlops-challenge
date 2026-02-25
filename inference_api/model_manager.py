from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional, Tuple

import tensorflow as tf

try:
    import tensorflow_text  # noqa: F401
except Exception:
    pass

logger = logging.getLogger(__name__)


class ModelManager:
    """Gerencia o ciclo de vida do SavedModel TensorFlow.

    Suporta carregamento thread-safe a partir de um artifacts_dir e run_id.

    Args:
        artifacts_dir: Diretório raiz onde os artefatos estão armazenados.
        default_run_id: run_id utilizado quando nenhum é fornecido explicitamente.
    """

    def __init__(
        self,
        artifacts_dir: str,
        default_run_id: str = "",
    ) -> None:
        """Inicializa o ModelManager.

        Args:
            artifacts_dir: Diretório raiz dos artefatos.
            default_run_id: run_id padrão a carregar.
        """
        self.artifacts_dir = Path(artifacts_dir.strip('/'))
        self.default_run_id = default_run_id.strip()
        self._lock = threading.Lock()
        self._translator = None
        self._run_id: Optional[str] = None

    def current_run_id(self) -> Optional[str]:
        """Retorna o run_id do modelo atualmente carregado.

        Returns:
            run_id atual ou None se nenhum modelo foi carregado.
        """
        return self._run_id

    def is_loaded(self) -> bool:
        """Verifica se um modelo está carregado e pronto para inferência.

        Returns:
            True se o modelo estiver carregado, False caso contrário.
        """
        return self._translator is not None and self._run_id is not None

    def load(self, run_id: Optional[str] = None) -> str:
        """Carrega o SavedModel correspondente ao run_id informado ou ao padrão.

        Realiza o carregamento de forma thread-safe e atualiza o estado interno.

        Args:
            run_id: run_id a carregar. Se None, utiliza ``default_run_id``.

        Returns:
            run_id do modelo carregado.

        Raises:
            ValueError: Se nenhum run_id estiver disponível.
            FileNotFoundError: Se o diretório do SavedModel não existir.
            Exception: Para qualquer erro durante o carregamento do TF.
        """
        rid = (run_id or self.default_run_id).strip()
        if not rid:
            raise ValueError(
                "Nenhum run_id disponível. Forneça um run_id ou defina DEFAULT_RUN_ID."
            )

        export_dir = self.artifacts_dir / rid / "saved_model"
        if not export_dir.exists():
            logger.error("SavedModel não encontrado: %s", export_dir)
            raise FileNotFoundError(f"SavedModel não encontrado: {export_dir}")

        logger.info("Carregando modelo run_id=%s de %s", rid, export_dir)
        try:
            translator = tf.saved_model.load(str(export_dir))
        except Exception:
            logger.exception("Falha ao carregar o modelo run_id=%s", rid)
            raise

        with self._lock:
            self._translator = translator
            self._run_id = rid

        logger.info("Modelo carregado com sucesso: run_id=%s", rid)
        return rid

    def translate(self, text: str) -> Tuple[str, str]:
        """Realiza a tradução de um texto usando o modelo carregado.

        Carrega o modelo automaticamente se ainda não estiver em memória.

        Args:
            text: Texto em português a ser traduzido.

        Returns:
            Tupla (translation, run_id) com o texto traduzido e o run_id utilizado.

        Raises:
            ValueError: Se nenhum run_id padrão estiver configurado.
            FileNotFoundError: Se o modelo não puder ser carregado.
            Exception: Para qualquer erro durante a inferência.
        """
        with self._lock:
            translator = self._translator
            rid = self._run_id

        if translator is None or rid is None:
            logger.warning("Modelo não carregado; realizando carga sob demanda.")
            rid = self.load()
            with self._lock:
                translator = self._translator

        logger.debug("Traduzindo texto (len=%d) com run_id=%s", len(text), rid)
        try:
            out = translator(tf.constant(text)).numpy().decode("utf-8")
        except Exception:
            logger.exception("Erro durante a inferência com run_id=%s", rid)
            raise

        return out, rid
