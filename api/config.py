"""Environment-backed settings for the ClosureIQ backend."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    project_root: Path = PROJECT_ROOT
    db_path: Path = Path(os.getenv("DB_PATH", "data/closureiq.db"))
    data_mode: str = os.getenv("DATA_MODE", "live").strip().lower()
    nws_user_agent: str = os.getenv(
        "NWS_USER_AGENT", "ClosureIQ-MVP/1.0 (closureiq-team@example.com)"
    )
    nws_timeout_seconds: float = float(os.getenv("NWS_TIMEOUT_SECONDS", "12"))
    nws_retry_seconds: float = float(os.getenv("NWS_RETRY_SECONDS", "5"))
    poll_on_startup: bool = _bool("POLL_ON_STARTUP", True)
    enable_scheduler: bool = _bool("ENABLE_SCHEDULER", True)
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    notification_mode: str = os.getenv("NOTIFICATION_MODE", "simulated").strip().lower()

    def resolved_db_path(self) -> Path:
        path = self.db_path
        if not path.is_absolute():
            path = self.project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()

if settings.data_mode not in {"live", "replay"}:
    settings.data_mode = "live"
