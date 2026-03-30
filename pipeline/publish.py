from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def publish(
    run_id: str,
    git_sha: str,
    epochs: int,
    threshold: float,
    artifacts_dir: Path,
) -> Path:
    source_dir = artifacts_dir / run_id
    metrics_path = source_dir / "metrics.json"
    source_metadata_path = source_dir / "metadata.json"

    if not source_dir.exists():
        print(f"[publish] ERROR: artifacts directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    if not metrics_path.exists():
        print(f"[publish] ERROR: metrics.json not found at {metrics_path}", file=sys.stderr)
        sys.exit(1)

    if not source_metadata_path.exists():
        print(
            f"[publish] ERROR: metadata.json not found at {source_metadata_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    dest_dir = artifacts_dir / "published" / run_id

    if dest_dir.exists():
        print(f"[publish] WARNING: already published at {dest_dir} — skipping (idempotent).")
        return dest_dir

    shutil.copytree(str(source_dir), str(dest_dir))

    with metrics_path.open() as f:
        metrics: dict = json.load(f)
    with source_metadata_path.open() as f:
        metadata: dict = json.load(f)

    published_metadata = {
        **metadata,
        "artifact_stage": "published",
        "run_id": run_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "epochs": epochs,
        "threshold": threshold,
        "metrics": metrics,
        "source_artifact_dir": str(source_dir.as_posix()),
        "export_dir": str((dest_dir / "saved_model").as_posix()),
    }

    published_metadata_path = dest_dir / "metadata.json"
    with published_metadata_path.open("w") as f:
        json.dump(published_metadata, f, indent=2)

    print(f"[publish] published to: {dest_dir}")
    print(f"[publish] metadata:    {json.dumps(published_metadata, indent=2)}")

    return dest_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish validated model artifacts with provenance metadata.")
    parser.add_argument("--run_id", required=True, help="Run ID to publish.")
    parser.add_argument("--git_sha", required=True, help="Git commit SHA for provenance.")
    parser.add_argument("--epochs", type=int, required=True, help="Number of training epochs.")
    parser.add_argument("--threshold", type=float, required=True, help="Quality threshold used during validation.")
    parser.add_argument("--artifacts_dir", default="artifacts", help="Root artifacts directory.")
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    publish(args.run_id, args.git_sha, args.epochs, args.threshold, artifacts_dir)


if __name__ == "__main__":
    main()
