from __future__ import annotations

import shelve
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"


def inspect_shelf(name: str) -> None:
    path = APP_DIR / name
    print(f"== {name} ==")
    try:
        with shelve.open(str(path)) as db:
            keys = sorted(db.keys())
            print(f"entries: {len(keys)}")
            if name == "recentplayers" and "names" in db:
                names = db["names"]
                print(f"recent names count: {len(names)}")
                print(f"recent names sample: {names[:10]}")
            elif name == "playerdb":
                for k in keys[:10]:
                    print(f"player: {k}")
            elif name == "match_history":
                for k in keys[-3:]:
                    record = db[k]
                    print(
                        "history: {} {} {}:{} -> winner {}".format(
                            record.get("timestamp", "?"),
                            record.get("team1", []),
                            record.get("score1", "?"),
                            record.get("score2", "?"),
                            record.get("winner", []),
                        )
                    )
            else:
                print(f"keys sample: {keys[:10]}")
    except Exception as exc:
        print(f"open error: {exc}")


def inspect_files() -> None:
    print("== app data files ==")
    for pattern in ("playerdb*", "recentplayers*", "tagdb*", "match_history*", "logfile.log"):
        for p in sorted(APP_DIR.glob(pattern)):
            if p.is_file():
                print(f"{p.name}\t{p.stat().st_size} bytes")


if __name__ == "__main__":
    inspect_files()
    print()
    for shelf_name in ("playerdb", "recentplayers", "tagdb", "match_history"):
        inspect_shelf(shelf_name)
        print()
