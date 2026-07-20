from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATASET_ROOT = PROJECT_ROOT / "data" / "raw" / "mvtec_ad" / "tile"
METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "mvtec_ad_tile.json"

EXPECTED_DIRECTORIES = (
    "train",
    "test",
    "ground_truth",
)