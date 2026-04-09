"""
Startup diagnostics for LCARS foosball app.

Performs preflight checks for assets, database access, and pygame initialization.
Warns on missing but recoverable components; aborts on critical failures.

Diagnostics are logged to startup.log in the app directory for persistent inspection.
"""

import sys
from pathlib import Path
import shelve
import datetime
from typing import Optional


def _log_write(log_file: Path, message: str) -> None:
    """Write message to both stderr and log file."""
    print(message, file=sys.stderr)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def check_assets(log_file: Optional[Path] = None) -> bool:
    """Verify required asset files exist.
    
    Returns:
        bool: True if all required assets found, False if critical assets missing.
    """
    app_dir = Path(__file__).parent
    required_assets = [
        "assets/bg_main.png",
        "assets/audio/panel",
    ]
    
    missing = []
    for asset in required_assets:
        asset_path = app_dir / asset
        if not asset_path.exists():
            missing.append(asset)
    
    if missing:
        msg = f"WARNING: Missing required assets: {', '.join(missing)}"
        if log_file:
            _log_write(log_file, f"  {msg}")
        else:
            print(msg, file=sys.stderr)
        return False
    
    return True


def check_database_access(log_file: Optional[Path] = None) -> bool:
    """Verify database files can be created/accessed.
    
    Returns:
        bool: True if database access is functional, False otherwise.
    """
    app_dir = Path(__file__).parent
    db_names = ["playerdb", "recentplayers", "tagdb"]
    
    for db_name in db_names:
        db_path = app_dir / db_name
        try:
            # Try to open each database to verify access
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


def check_pygame(log_file: Optional[Path] = None) -> bool:
    """Verify pygame can be initialized.
    
    Returns:
        bool: True if pygame initialization successful, False otherwise.
    """
    try:
        import pygame
        pygame.init()
        pygame.quit()
        return True
    except Exception as e:
        msg = f"ERROR: pygame initialization failed: {e}"
        if log_file:
            _log_write(log_file, f"  {msg}")
        else:
            print(msg, file=sys.stderr)
        return False


def run_diagnostics() -> bool:
    """Run all startup diagnostics.
    
    Performs asset, database, and pygame checks. Warnings are non-blocking;
    errors on critical components abort startup.
    
    Diagnostics are logged to startup.log in the app directory.
    
    Returns:
        bool: True if all critical checks pass, False otherwise.
    """
    app_dir = Path(__file__).parent
    log_file = app_dir / "startup.log"
    
    # Open log file in append mode
    with log_file.open("a", encoding="utf-8") as log:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\n{'='*60}\n")
        log.write(f"Startup diagnostics started: {timestamp}\n")
        log.write(f"{'='*60}\n")
        
        # Check assets (non-critical, many assets are loaded dynamically)
        log.write("[1/3] Checking assets...\n")
        assets_ok = check_assets(log_file)
        log.write(f"  Result: {'OK' if assets_ok else 'WARNINGS'}\n")
        
        # Check database access (non-critical, databases auto-create)
        log.write("[2/3] Checking database access...\n")
        db_ok = check_database_access(log_file)
        log.write(f"  Result: {'OK' if db_ok else 'WARNINGS'}\n")
        
        # Check pygame (critical)
        log.write("[3/3] Checking pygame initialization...\n")
        pygame_ok = check_pygame(log_file)
        log.write(f"  Result: {'OK' if pygame_ok else 'FAILED'}\n")
        
        if not pygame_ok:
            log.write("ERROR: Cannot start app without pygame. Check pygame installation.\n")
            log.write(f"Diagnostics completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            msg = f"ERROR: Cannot start app without pygame. Log written to: {log_file}"
            print(msg, file=sys.stderr)
            return False
        
        log.write(f"Diagnostics completed successfully at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Log file: {log_file}\n")
        
    # Print log file location to stderr so user knows where to find details
    print(f"[startup] Diagnostics passed. Details logged to: {log_file}", file=sys.stderr)
    return True
