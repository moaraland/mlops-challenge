from __future__ import annotations
import os
os.environ.setdefault("WRAPT_DISABLE_EXTENSIONS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")

from pathlib import Path
from typing import Tuple

import tensorflow as tf

try:
    import tensorflow_text  # registra ops necessárias do TF Text
    _TF_TEXT_OK = True
except Exception:
    _TF_TEXT_OK = False


TOKENIZER_MODEL_NAME = "ted_hrlr_translate_pt_en_converter"
TOKENIZER_ZIP_URL = (
    "https://storage.googleapis.com/download.tensorflow.org/models/"
    f"{TOKENIZER_MODEL_NAME}.zip"
)


def _require_tf_text() -> None:
    if not _TF_TEXT_OK:
        raise RuntimeError(
            "tensorflow-text é necessário para carregar os tokenizers do SavedModel. "
            "Use Linux x86_64 (ex.: Docker/WSL2) com Python compatível."
        )


def download_and_load_tokenizers(base_dir: str | Path) -> tf.types.experimental.Trackable:
    """
    Baixa e extrai o SavedModel de tokenizers dentro de `base_dir` e retorna
    o objeto carregado via `tf.saved_model.load`.
    """
    _require_tf_text()
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    base_dir = tf.keras.utils.get_file(
        fname=f"{TOKENIZER_MODEL_NAME}.zip",
        origin=TOKENIZER_ZIP_URL,
        cache_dir=str(base_dir),
        cache_subdir="",
        extract=True,
    )
    model_dir = Path(base_dir) / TOKENIZER_MODEL_NAME
    return tf.saved_model.load(str(model_dir))


def get_start_end_ids(tokenizer: tf.types.experimental.Trackable) -> Tuple[int, int]:
    start_end = tokenizer.tokenize([""])[0]
    start_id = int(start_end[0].numpy())
    end_id = int(start_end[1].numpy())
    return start_id, end_id


def vocab_size(tokenizer: tf.types.experimental.Trackable) -> int:
    return int(tokenizer.get_vocab_size().numpy())
