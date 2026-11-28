"""Read one private worker metrics snapshot and report aggregate quality shifts."""

import argparse
import json
import math
import re
from pathlib import Path

from prometheus_client.parser import text_string_to_metric_families

from app.services.quality_monitor import (
    DIMENSION_BOUNDS,
    FORMATS,
    MIN_OBSERVATIONS,
    SCORE_BOUNDS,
    WARNING_SIGNALS,
    WINDOW_MINUTES,
)

MAX_SCRAPE_BYTES = 1024 * 1024
BIN_BOUNDS = {
    "width": (*map(str, DIMENSION_BOUNDS), "+Inf"),
    "height": (*map(str, DIMENSION_BOUNDS), "+Inf"),
    "score": (*map(str, SCORE_BOUNDS), "+Inf"),
}


def report_from_scrape(text: str) -> dict[str, object]:
    samples = {}
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name.startswith("vddai_quality_"):
                key = (sample.name, tuple(sorted(sample.labels.items())))
                if key in samples or not math.isfinite(sample.value):
                    raise ValueError("Invalid quality metric sample.")
                samples[key] = sample.value

    def value(suffix: str, **labels: str) -> float:
        key = (f"vddai_quality_{suffix}", tuple(sorted(labels.items())))
        if key not in samples:
            raise ValueError("Required quality metric is unavailable.")
        return samples[key]

    def count_value(suffix: str, **labels: str) -> int:
        sample = value(suffix, **labels)
        if sample < 0 or sample != int(sample):
            raise ValueError("Invalid quality observation count.")
        return int(sample)

    ready = value("comparison_ready")
    count = count_value("window_count")
    references = {
        source: count_value("reference_count", source=source)
        for source in ("normal_validation", "synthetic_fixture")
        if ("vddai_quality_reference_count", (("source", source),)) in samples
    }
    if (
        ready not in (0, 1)
        or len(references) > 1
        or any(total < MIN_OBSERVATIONS for total in references.values())
        or (ready and (count < MIN_OBSERVATIONS or len(references) != 1))
    ):
        raise ValueError("Invalid comparison readiness.")
    report = {
        "window_minutes": WINDOW_MINUTES,
        "observations": count,
        "comparison": "available" if ready else "unavailable",
        "reference": references or None,
        "warnings": None,
    }
    if count:
        identities = [
            labels[0][1]
            for (name, labels), sample in samples.items()
            if name == "vddai_quality_package_info"
            and len(labels) == 1
            and labels[0][0] == "package_id"
            and sample == 1
        ]
        if len(identities) != 1 or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{7,99}", identities[0]
        ):
            raise ValueError("Invalid quality package identity.")
        formats = {name: count_value("format_count", format=name) for name in FORMATS}
        bins = {
            signal: {
                bound: count_value("window_bin_count", signal=signal, upper_bound=bound)
                for bound in bounds
            }
            for signal, bounds in BIN_BOUNDS.items()
        }
        if sum(formats.values()) != count or any(
            sum(b.values()) != count for b in bins.values()
        ):
            raise ValueError("Quality distribution counts do not match the window.")
        mean = value("pixel_mean")
        contrast = value("pixel_contrast")
        anomaly_rate = value("anomaly_rate")
        if not (0 <= mean <= 1 and 0 <= contrast <= 0.5 and 0 <= anomaly_rate <= 1):
            raise ValueError("Invalid quality aggregate.")
        report.update(
            package_id=identities[0],
            image_formats=formats,
            distribution_bins=bins,
            pixel_mean=mean,
            pixel_contrast=contrast,
            anomaly_rate=anomaly_rate,
        )
    if ready:
        warnings = {
            signal: value("shift_warning", signal=signal) for signal in WARNING_SIGNALS
        }
        if any(sample not in (0, 1) for sample in warnings.values()):
            raise ValueError("Invalid quality warning.")
        report["warnings"] = [signal for signal, sample in warnings.items() if sample]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        with args.snapshot.open("rb") as snapshot:
            contents = snapshot.read(MAX_SCRAPE_BYTES + 1)
        if len(contents) > MAX_SCRAPE_BYTES:
            raise ValueError("Snapshot exceeds the size limit.")
        report = report_from_scrape(contents.decode("utf-8"))
    except (OSError, ValueError):
        parser.exit(
            2, "Quality report unavailable: invalid or missing metrics snapshot.\n"
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
