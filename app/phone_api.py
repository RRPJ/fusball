"""Read-only phone API and mobile leaderboard page.

This module provides a small Flask app that reads the existing shelve-backed
player database and exposes:
- JSON API for leaderboard data
- Mobile-friendly HTML leaderboard view
"""

from __future__ import annotations

import shelve
from pathlib import Path
from string import capwords

from flask import Flask, jsonify, request

from odds import playerLevel
from services.player_store import rank_labels_by_name, ranked_players


ROOT_DIR = Path(__file__).resolve().parent


def _playerdb_exists(db_dir: Path) -> bool:
    """Return whether any shelve artifact for playerdb exists in the directory."""
    return any(db_dir.glob("playerdb*"))


def _load_leaderboard(db_dir: Path, limit: int = 50) -> list[dict[str, object]]:
    db_path = db_dir / "playerdb"
    if not _playerdb_exists(db_dir):
        return []

    with shelve.open(str(db_path)) as players:
        ranked = ranked_players(players.items())
        labels = rank_labels_by_name(ranked)

        rows = []
        for index, (name, rating) in enumerate(ranked[:limit], start=1):
            rows.append(
                {
                    "position": index,
                    "name": capwords(name),
                    "rank": labels[name],
                    "level": round(playerLevel(rating), 2),
                    "offense_mu": round(rating[0].mu, 2),
                    "offense_sigma": round(rating[0].sigma, 2),
                    "defense_mu": round(rating[1].mu, 2),
                    "defense_sigma": round(rating[1].sigma, 2),
                }
            )
        return rows


def _render_phone_html(rows: list[dict[str, object]]) -> str:
    table_rows = "\n".join(
        (
            "<tr>"
            f"<td>{row['position']}</td>"
            f"<td>{row['name']}</td>"
            f"<td>{row['rank']}</td>"
            f"<td>{row['level']}</td>"
            "</tr>"
        )
        for row in rows
    )

    if not table_rows:
        table_rows = "<tr><td colspan='4'>No players found.</td></tr>"

    return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Foosball Leaderboard</title>
  <style>
    :root {{
      --bg: #0b1721;
      --bg-2: #122535;
      --accent: #ef8a17;
      --text: #e7eef4;
      --muted: #9fb3c4;
      --panel: rgba(14, 34, 49, 0.92);
      --line: rgba(159, 179, 196, 0.28);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      background:
        radial-gradient(1200px 480px at 10% -10%, #1f4c6c 0%, transparent 70%),
        radial-gradient(800px 500px at 100% 0%, #253f59 0%, transparent 65%),
        linear-gradient(165deg, var(--bg), var(--bg-2));
      color: var(--text);
      min-height: 100vh;
      padding: 18px;
    }}
    .panel {{
      width: min(720px, 100%);
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0;
      font-size: 1.05rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    .muted {{ color: var(--muted); font-size: 0.82rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 12px 10px; text-align: left; border-bottom: 1px solid var(--line); }}
    th {{ font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.07em; }}
    td {{ font-size: 0.95rem; }}
    tr:last-child td {{ border-bottom: none; }}
    td:first-child {{ width: 56px; color: var(--accent); font-weight: 700; }}
  </style>
</head>
<body>
  <main class='panel'>
    <header>
      <h1>LCARS Kickers Leaderboard</h1>
      <div class='muted'>Read-only mobile view</div>
    </header>
    <table aria-label='Leaderboard'>
      <thead>
        <tr><th>#</th><th>Player</th><th>Rank</th><th>Level</th></tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </main>
</body>
</html>"""


def create_app(db_dir: Path | None = None) -> Flask:
    """Create the phone API app.

    Args:
        db_dir: Directory containing shelve files. Defaults to app directory.
    """
    app = Flask(__name__)
    data_dir = db_dir or ROOT_DIR

    @app.get("/api/health")
    def health() -> object:
        return jsonify({"ok": True})

    @app.get("/api/leaderboard")
    def leaderboard() -> object:
        limit = request.args.get("limit", default=50, type=int)
        limit = max(1, min(limit, 200))
        rows = _load_leaderboard(data_dir, limit)
        return jsonify({"count": len(rows), "items": rows})

    @app.get("/phone")
    def phone_view() -> str:
        rows = _load_leaderboard(data_dir, limit=50)
        return _render_phone_html(rows)

    return app


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
