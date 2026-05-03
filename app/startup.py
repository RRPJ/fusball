"""Startup diagnostics for the Fusball phone API runtime.

The phone API can run against the default app data directory or a custom data
directory, so diagnostics focus on shelve accessibility and log-file location
rather than any UI assets.
"""

import datetime
import shelve
import sys
from pathlib import Path
from typing import Optional


def _log_write(log_file: Path, message: str) -> None:
    """Write message to both stderr and log file."""
    print(message, file=sys.stderr)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def check_database_access(db_dir: Path, log_file: Optional[Path] = None) -> bool:
    """Verify database files can be created/accessed.

    Returns:
        bool: True if database access is functional, False otherwise.
    """
    db_names = ["playerdb", "recentplayers", "match_history"]

    for db_name in db_names:
        db_path = db_dir / db_name
        try:
            with shelve.open(str(db_path)):
                pass
        except Exception as e:
            msg = f"WARNING: Cannot access {db_name}: {e}"
            if log_file:
                _log_write(log_file, f"  {msg}")
            else:
                print(msg, file=sys.stderr)
            return False
    
    return True


def check_log_destination(db_dir: Path, log_file: Optional[Path] = None) -> bool:
    """Verify the data directory exists and can host legacy text logs."""
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        with (db_dir / "logfile.log").open("a", encoding="utf-8"):
            pass
        return True
    except Exception as e:
        msg = f"WARNING: Cannot access logfile.log in {db_dir}: {e}"
        if log_file:
            _log_write(log_file, f"  {msg}")
        else:
            print(msg, file=sys.stderr)
        return False


def run_diagnostics(db_dir: str | Path | None = None) -> bool:
    """Run all startup diagnostics.

    Performs data-directory, shelve, and log-file checks. Warnings are
    non-blocking because the phone API can create missing stores on demand.

    Diagnostics are logged to startup.log in the target data directory.

    Returns:
        bool: True if the diagnostics complete.
    """
    target_dir = Path(db_dir).resolve() if db_dir else Path(__file__).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "startup.log"

    with log_file.open("a", encoding="utf-8") as log:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\n{'='*60}\n")
        log.write(f"Startup diagnostics started: {timestamp}\n")
        log.write(f"{'='*60}\n")

        log.write("[1/2] Checking database access...\n")
        db_ok = check_database_access(target_dir, log_file)
        log.write(f"  Result: {'OK' if db_ok else 'WARNINGS'}\n")

        log.write("[2/2] Checking log destination...\n")
        log_ok = check_log_destination(target_dir, log_file)
        log.write(f"  Result: {'OK' if log_ok else 'WARNINGS'}\n")

        log.write(f"Diagnostics completed successfully at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Log file: {log_file}\n")

    print(f"[startup] Diagnostics passed. Details logged to: {log_file}", file=sys.stderr)
    return True
