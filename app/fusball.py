"""Canonical app entrypoint.

This module keeps backward compatibility by delegating to the legacy
`lcars.py` entrypoint, which remains intact for existing scripts and deployments.
"""

from lcars import main


if __name__ == "__main__":
    main()
