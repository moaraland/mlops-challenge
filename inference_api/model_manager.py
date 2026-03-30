from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModelInfo:
    """Metadados do modelo atualmente carregado."""

    run_id: str
    git_sha: str | None
    published_at: str | None
    artifact_path: str


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
        self.artifacts_dir = Path(artifacts_dir)
        self.default_run_id = default_run_id.strip()
        self._lock = threading.Lock()
        self._translator = None
        self._run_id: Optional[str] = None
        self._model_info: Optional[LoadedModelInfo] = None

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

    def current_model_info(self) -> Optional[LoadedModelInfo]:
        """Retorna os metadados do modelo atualmente carregado."""
        return self._model_info

    def adopt_loaded_state(self, other: "ModelManager") -> None:
        """Adota o estado carregado de outro gerenciador sem trocar configuração."""
        with other._lock:
            translator = other._translator
            run_id = other._run_id
            model_info = other._model_info

        with self._lock:
            self._translator = translator
            self._run_id = run_id
            self._model_info = model_info

    @staticmethod
    def _resolve_published_root(artifacts_dir: Path) -> Path:
        """Normaliza o diretório raiz para a área publicada."""
        return (
            artifacts_dir
            if artifacts_dir.name == "published"
            else artifacts_dir / "published"
        )

    def _resolve_run_dir(self, run_id: str) -> Path:
        """Resolve o diretório publicado que contém os artefatos do run."""
        return self._resolve_published_root(self.artifacts_dir) / run_id

    def _load_saved_model(self, export_dir: Path) -> Any:
        """Carrega o SavedModel sob demanda para manter o import leve nos testes."""
        import tensorflow as tf

        try:
            import tensorflow_text  # noqa: F401
        except Exception:
            pass

        return tf.saved_model.load(str(export_dir))

    def _read_model_info(
        self,
        run_dir: Path,
        run_id: str,
        export_dir: Path,
    ) -> LoadedModelInfo:
        """Lê metadados do artefato publicado para rastreabilidade operacional."""
        metadata_path = run_dir / "metadata.json"
        provenance_path = run_dir / "provenance.json"
        payload: dict[str, Any] = {}

        if metadata_path.exists():
            with metadata_path.open(encoding="utf-8") as file:
                payload = json.load(file)
        elif provenance_path.exists():
            with provenance_path.open(encoding="utf-8") as file:
                payload = json.load(file)

        return LoadedModelInfo(
            run_id=payload.get("run_id", run_id),
            git_sha=payload.get("git_sha"),
            published_at=payload.get("published_at") or payload.get("timestamp"),
            artifact_path=str(export_dir),
        )

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

        run_dir = self._resolve_run_dir(rid)
        export_dir = run_dir / "saved_model"
        if not export_dir.exists():
            logger.error("SavedModel não encontrado: %s", export_dir)
            raise FileNotFoundError(f"SavedModel não encontrado: {export_dir}")

        logger.info("Carregando modelo run_id=%s de %s", rid, export_dir)
        try:
            translator = self._load_saved_model(export_dir)
        except Exception:
            logger.exception("Falha ao carregar o modelo run_id=%s", rid)
            raise
        model_info = self._read_model_info(run_dir, rid, export_dir)

        with self._lock:
            self._translator = translator
            self._run_id = rid
            self._model_info = model_info

        logger.info(
            "Modelo carregado com sucesso: run_id=%s git_sha=%s published_at=%s artifact_path=%s",
            model_info.run_id,
            model_info.git_sha,
            model_info.published_at,
            model_info.artifact_path,
        )
        return rid

    def translate(self, text: str) -> Tuple[str, str]:
        """Realiza a tradução de um texto usando o modelo carregado.

        Carrega o modelo automaticamente se ainda não estiver em memória.

        Args:
            text: Texto em inglês a ser traduzido.

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
            import tensorflow as tf

            out = translator(tf.constant(text)).numpy().decode("utf-8")
        except Exception:
            logger.exception("Erro durante a inferência com run_id=%s", rid)
            raise

        return out, rid
