from __future__ import annotations

import argparse
import shutil
import shelve
from pathlib import Path

import trueskill

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
DEFAULT_TARGET = ROOT / "sandbox" / "dev-data"
PATTERNS = ["playerdb*", "recentplayers*", "match_history*", "logfile.log"]
SEED_PLAYERS = ["alice", "bob", "carol", "dave", "eve", "frank", "grace", "heidi"]


def copy_data(source_dir: Path, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pattern in PATTERNS:
        for source in source_dir.glob(pattern):
            if not source.is_file():
                continue
            destination = target_dir / source.name
            shutil.copy2(source, destination)
            copied += 1
    return copied


def clear_data(target_dir: Path) -> int:
    removed = 0
    for pattern in PATTERNS:
        for file_path in target_dir.glob(pattern):
            if file_path.is_file():
                file_path.unlink()
                removed += 1
    return removed


def seed_demo_players(target_dir: Path) -> None:
    with shelve.open(str(target_dir / "playerdb")) as playerdb:
        for name in SEED_PLAYERS:
            if name not in playerdb:
                playerdb[name] = (trueskill.Rating(), trueskill.Rating())

    with shelve.open(str(target_dir / "recentplayers")) as recent:
        recent["names"] = SEED_PLAYERS[:]



def main() -> None:
    parser = argparse.ArgumentParser(description="Create or refresh isolated dev data sandbox")
    parser.add_argument(
        "--source",
        default=str(APP_DIR),
        help="Source data directory (defaults to app)",
    )
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="Sandbox target data directory",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Seed demo players after copying data",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete existing sandbox data files before copying",
    )
    parser.add_argument(
        "--only-seed",
        action="store_true",
        help="Clear sandbox and seed demo players only; skip copying from source entirely",
    )
    args = parser.parse_args()

    target_dir = Path(args.target).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    removed = 0
    copied = 0

    if args.only_seed:
        removed = clear_data(target_dir)
        seed_demo_players(target_dir)
    else:
        source_dir = Path(args.source).resolve()
        if not source_dir.exists():
            raise SystemExit(f"Source directory does not exist: {source_dir}")

        if args.fresh:
            removed = clear_data(target_dir)

        copied = copy_data(source_dir, target_dir)

        if args.seed_demo:
            seed_demo_players(target_dir)

    print(f"Sandbox target: {target_dir}")
    print(f"Files removed: {removed}")
    print(f"Files copied: {copied}")
    print(f"Demo seed applied: {'yes' if args.seed_demo else 'no'}")


if __name__ == "__main__":
    main()
