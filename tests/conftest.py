"""Keep tests off the developer's data/closureiq.db: importing api.main builds an app."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp(prefix="closureiq-test-")) / "closureiq.db"))
os.environ.setdefault("LEGACY_DB_PATH", str(Path(tempfile.mkdtemp(prefix="closureiq-legacy-")) / "legacy.db"))
