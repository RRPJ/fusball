from __future__ import annotations

import argparse
import json

from werkzeug.security import generate_password_hash


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate hash values for phone API PIN authentication")
    parser.add_argument("--read-pin", help="Plain read PIN to hash")
    parser.add_argument("--write-pin", help="Plain writer PIN to hash")
    parser.add_argument(
        "--format",
        choices=["json", "text", "dotenv"],
        default="text",
        help="Output format",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.read_pin and not args.write_pin:
        parser.error("at least one of --read-pin or --write-pin is required")

    values: dict[str, str] = {}
    if args.read_pin:
        values["READ_PIN_HASH"] = generate_password_hash(args.read_pin)
    if args.write_pin:
        values["WRITE_PIN_HASH"] = generate_password_hash(args.write_pin)

    if args.format == "json":
        print(json.dumps(values))
        return

    if args.format == "dotenv":
        for key, value in values.items():
            print(f"{key}={value}")
        return

    for key, value in values.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
