from __future__ import annotations

import hashlib
import json
import os
import random
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)


def read_json(path: str | Path) -> Any:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_run_id(prefix: str = "run") -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    rand = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}_{ts}_{rand}"


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class PreparedDatasetInfo:
    dataset_name: str
    max_tokens: int
    train_records: int
    val_records: int
    tokenizer_dir: str
    pt_vocab_size: int
    en_vocab_size: int
