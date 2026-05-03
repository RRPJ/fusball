from __future__ import annotations

import argparse
import shelve
import time
from pathlib import Path

import trueskill

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"

import sys

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from odds import playerLevel  # noqa: E402


def ensure_seed_players(playerdb: shelve.Shelf) -> list[str]:
    seeds = ["alice", "bob", "carol", "dave", "eve", "frank", "grace", "heidi"]
    for name in seeds:
        if name not in playerdb:
            playerdb[name] = (trueskill.Rating(), trueskill.Rating())
    return seeds


def update_recentplayers(work_dir: Path, names: list[str]) -> None:
    with shelve.open(str(work_dir / "recentplayers")) as recent:
        existing = recent.get("names", [])
        merged: list[str] = []
        for name in names + existing:
            lname = name.lower()
            if lname not in merged:
                merged.append(lname)
        recent["names"] = merged


def apply_match_result(
    playerdb: shelve.Shelf,
    team1: tuple[str, ...],
    team2: tuple[str, ...],
    score1: int,
    score2: int,
) -> None:
    newratings = [[playerdb[team1[0]][0]], [playerdb[team2[0]][0]]]

    if len(team1) > 1:
        newratings[0].append(playerdb[team1[1]][1])
    else:
        newratings[0].append(playerdb[team1[0]][1])

    if len(team2) > 1:
        newratings[1].append(playerdb[team2[1]][1])
    else:
        newratings[1].append(playerdb[team2[0]][1])

    newratings_t = (tuple(newratings[0]), tuple(newratings[1]))

    num_draws = min(score1, score2)
    num_wins = max(score1, score2) - num_draws

    for _ in range(num_draws):
        newratings_t = trueskill.rate(newratings_t, ranks=[1, 1])

    team1_won = score1 > score2
    for _ in range(num_wins):
        newratings_t = trueskill.rate(newratings_t, ranks=[0, 1] if team1_won else [1, 0])

    updated = dict(playerdb.items())

    updated[team1[0]] = (newratings_t[0][0], updated[team1[0]][1])
    updated[team2[0]] = (newratings_t[1][0], updated[team2[0]][1])

    if len(team1) > 1:
        updated[team1[1]] = (updated[team1[1]][0], newratings_t[0][1])
    else:
        updated[team1[0]] = (updated[team1[0]][0], newratings_t[0][1])

    if len(team2) > 1:
        updated[team2[1]] = (updated[team2[1]][0], newratings_t[1][1])
    else:
        updated[team2[0]] = (updated[team2[0]][0], newratings_t[1][1])

    for key, value in updated.items():
        playerdb[key] = value


def append_log(work_dir: Path, team1: tuple[str, ...], team2: tuple[str, ...], score1: int, score2: int) -> None:
    logfile = work_dir / "logfile.log"
    with logfile.open("a", encoding="utf-8") as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: simulated match {team1} vs {team2} => {score1}:{score2}\n")


def print_top(playerdb: shelve.Shelf, count: int = 10) -> None:
    ranked = sorted(playerdb.items(), key=lambda kv: playerLevel(kv[1]), reverse=True)
    print("Top players:")
    for idx, (name, rating) in enumerate(ranked[:count], start=1):
        level = round(playerLevel(rating), 2)
        print(f"{idx:2d}. {name:10s} level={level:6.2f} off={rating[0].mu:.2f}/{rating[0].sigma:.2f} def={rating[1].mu:.2f}/{rating[1].sigma:.2f}")


def print_data_files(work_dir: Path) -> None:
    print("Data files:")
    for pattern in ("playerdb*", "recentplayers*", "match_history*", "logfile.log"):
        for file in sorted(work_dir.glob(pattern)):
            if file.is_file():
                print(f"- {file.name}: {file.stat().st_size} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate matches and inspect resulting leaderboard/data files.")
    parser.add_argument("--work-dir", default=str(APP_DIR), help="Directory containing app shelve files")
    parser.add_argument("--matches", type=int, default=10, help="Number of simulation matches to run")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()

    print(f"Using work dir: {work_dir}")
    print_data_files(work_dir)

    with shelve.open(str(work_dir / "playerdb")) as playerdb:
        ensure_seed_players(playerdb)

        schedule = [
            (("alice", "bob"), ("carol", "dave"), 5, 3),
            (("alice", "eve"), ("frank", "grace"), 5, 2),
            (("heidi", "dave"), ("alice", "carol"), 4, 5),
            (("bob", "frank"), ("eve", "grace"), 5, 4),
            (("carol", "heidi"), ("alice", "bob"), 1, 5),
            (("alice",), ("frank",), 5, 1),
            (("grace",), ("dave",), 3, 5),
            (("eve", "heidi"), ("carol", "frank"), 5, 0),
            (("alice", "grace"), ("bob", "dave"), 5, 4),
            (("carol",), ("eve",), 5, 2),
        ]

        for i in range(args.matches):
            team1, team2, score1, score2 = schedule[i % len(schedule)]
            apply_match_result(playerdb, team1, team2, score1, score2)
            update_recentplayers(work_dir, list(team1 + team2))
            append_log(work_dir, team1, team2, score1, score2)

        print()
        print_top(playerdb)

    print()
    print_data_files(work_dir)


if __name__ == "__main__":
    main()
