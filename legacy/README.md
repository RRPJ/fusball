# Legacy - Kiosk/Touchscreen Hardware

This directory contains files specific to the original Raspberry Pi kiosk deployment with touchscreen hardware. These are kept for reference only and are no longer maintained.

## Files

- `run.sh` — X11/xinit launcher for the Raspberry Pi kiosk
- `setup.sh` — Raspberry Pi dependency installer (one-time setup)
- `touchscreen.py` — Serial driver for the resistive touchscreen hardware (custom protocol)
- `fixdpms.sh` — Display power management (DPMS) for X11 kiosk
- `xinitrc` — X11 init config for Raspberry Pi (entry point for kiosk)
- `demo.py` — Old UI framework prototype (not used)

## Future Access Plan

The project now supports a kiosk-first model with a separate **smartphone web/API path**.
Current implementation includes a thin HTTP API and mobile page for leaderboard access and authenticated write slices.

Near-term modernization continues with:
- Structured match history and safer portability/migration paths
- Expanded analytics and season/tournament foundations
- Additional remote workflows after validation and data-model hardening

See `README.md`, `docs/development.md`, `docs/architecture.md`, `docs/backlog.md`, and `docs/modernization-plan.md` for current status and sequencing.

If you need to revive kiosk support in the future, these files provide a reference for the original architecture.
