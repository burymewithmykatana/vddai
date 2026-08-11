"""Query the local experiment ledger without direct SQLite access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.experiment_tracking import (
    DEFAULT_EXPERIMENT_TRACKER_PATH,
    RUN_STATUSES,
    ExperimentTracker,
    ExperimentTrackingError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query tracked VDDAI experiments.")
    parser.add_argument("--tracker", type=Path, default=DEFAULT_EXPERIMENT_TRACKER_PATH)
    parser.add_argument("--run-id")
    parser.add_argument("--status", choices=RUN_STATUSES)
    parser.add_argument("--experiment-name")
    parser.add_argument("--dataset-version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        tracker = ExperimentTracker(args.tracker)
        if args.run_id:
            result: object = tracker.get_run(args.run_id)
        else:
            result = tracker.list_runs(
                status=args.status,
                experiment_name=args.experiment_name,
                dataset_version=args.dataset_version,
            )
    except ExperimentTrackingError as exc:
        raise SystemExit(f"Experiment query failed: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
