from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
BACKUPS_DIR = ROOT / "backups"

PATTERNS = ["playerdb*", "recentplayers*", "match_history*", "logfile.log"]


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUPS_DIR / timestamp
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    for pattern in PATTERNS:
        for source in APP_DIR.glob(pattern):
            destination = target / source.name
            if source.is_file():
                shutil.copy2(source, destination)
                copied += 1

    print(f"Backup created at: {target}")
    print(f"Files copied: {copied}")


if __name__ == "__main__":
    main()
