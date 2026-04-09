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

The project is being modernized to support **smartphone access** instead of kiosk hardware. This will likely use:
- A thin HTTP API (FastAPI/Flask) for remote score entry and leaderboard
- SQLite or similar for data persistence and cloud sync
- Web/mobile client for score entry and viewing

If you need to revive kiosk support in the future, these files provide a reference for the original architecture.
