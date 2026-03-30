from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate(run_id: str, threshold: float, artifacts_dir: Path) -> bool:
    metrics_path = artifacts_dir / run_id / "metrics.json"

    if not metrics_path.exists():
        print(f"[validate] ERROR: metrics.json not found at {metrics_path}", file=sys.stderr)
        sys.exit(1)

    with metrics_path.open() as f:
        metrics: dict = json.load(f)

    val_token_accuracy: float = metrics["val_token_accuracy"]
    approved = val_token_accuracy >= threshold

    print(f"[validate] run_id:            {run_id}")
    print(f"[validate] val_token_accuracy: {val_token_accuracy:.4f}")
    print(f"[validate] threshold:         {threshold:.4f}")
    print(f"[validate] result:            {'APPROVED' if approved else 'REJECTED'}")

    return approved


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate model metrics against a quality threshold.")
    parser.add_argument("--run_id", required=True, help="Run ID to validate.")
    parser.add_argument("--threshold", type=float, required=True, help="Minimum val_token_accuracy to approve.")
    parser.add_argument("--artifacts_dir", default="artifacts", help="Root artifacts directory.")
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    approved = validate(args.run_id, args.threshold, artifacts_dir)

    sys.exit(0 if approved else 1)


if __name__ == "__main__":
    main()
