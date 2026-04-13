#!/bin/sh
# LEGACY - X11/xinit launcher for Raspberry Pi kiosk.
# Kept for reference. Use app/fusball.py directly for modern deployments.

cd app
xinit /usr/bin/python3 lcars.py
