import os
import sys
from pathlib import Path

APP_ID = "com.local.ledger-report-generator"


def app_data_dir() -> Path:
    override = os.getenv("LEDGER_REPORTER_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / APP_ID


def app_cache_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_ID
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / APP_ID / "cache"


def resource_path(name: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "ledger_reporter"
    else:
        base = Path(__file__).resolve().parent
    resources = base / "resources"
    candidate = (resources / name).resolve()
    if resources.resolve() not in candidate.parents:
        raise ValueError("resource path escapes resources directory")
    return candidate
