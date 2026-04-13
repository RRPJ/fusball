#!/usr/bin/env python3
"""Quick test of startup diagnostics and fusball entrypoint integration."""

import sys
from pathlib import Path

# Add app to path
app_path = Path(__file__).parent / "app"
sys.path.insert(0, str(app_path))

# Test 1: Import startup module
print("Test 1: Importing startup module...")
try:
    from startup import run_diagnostics
    print("  ✓ startup module imported successfully")
except Exception as e:
    print(f"  ✗ Failed to import startup: {e}", file=sys.stderr)
    sys.exit(1)

# Test 2: Import fusball entrypoint
print("Test 2: Importing fusball (new entrypoint)...")
try:
    import fusball
    print("  ✓ fusball module imported successfully")
except Exception as e:
    print(f"  ✗ Failed to import fusball: {e}", file=sys.stderr)
    sys.exit(1)

# Test 3: Import lcars (legacy, should still work for compatibility)
print("Test 3: Importing lcars (legacy for compatibility)...")
try:
    import lcars
    print("  ✓ lcars module imported successfully (legacy support OK)")
except Exception as e:
    print(f"  ✗ Failed to import lcars: {e}", file=sys.stderr)
    sys.exit(1)

# Test 4: Run diagnostics
print("Test 4: Running startup diagnostics...")
try:
    result = run_diagnostics()
    print(f"  ✓ Diagnostics completed (result: {result})")
except Exception as e:
    print(f"  ✗ Diagnostics failed: {e}", file=sys.stderr)
    sys.exit(1)

print("\nAll integration tests passed!")
