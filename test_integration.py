#!/usr/bin/env python3
"""Quick test of startup diagnostics integration."""

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

# Test 2: Import modified lcars
print("Test 2: Importing lcars module...")
try:
    # Just check the syntax, don't run main()
    import lcars
    print("  ✓ lcars module imported successfully")
except Exception as e:
    print(f"  ✗ Failed to import lcars: {e}", file=sys.stderr)
    sys.exit(1)

# Test 3: Run diagnostics
print("Test 3: Running diagnostics...")
try:
    result = run_diagnostics()
    print(f"  ✓ Diagnostics completed (result: {result})")
except Exception as e:
    print(f"  ✗ Diagnostics failed: {e}", file=sys.stderr)
    sys.exit(1)

print("\nAll integration tests passed!")
