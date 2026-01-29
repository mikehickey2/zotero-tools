#!/usr/bin/env python3
"""
zotero_add_item.py

Create Zotero items from NTSB CAROL JSON data.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_add_item.py --input case.json --dry-run
    python zotero_add_item.py --input case.json --collection "Collisions"
"""

import argparse
import json
import sys
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials


def load_carol_json(json_path: str) -> list[dict]:
    """Load NTSB CAROL JSON file."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: File not found: {json_path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # CAROL exports as array
    if isinstance(data, list):
        return data
    return [data]


def main():
    parser = argparse.ArgumentParser(
        description="Create Zotero items from NTSB CAROL JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--input', '-i', required=True, help='Path to CAROL JSON file')
    parser.add_argument('--collection', '-c', help='Collection name to add items to')
    parser.add_argument('--dry-run', action='store_true', help='Preview without creating')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Load JSON
    cases = load_carol_json(args.input)
    print(f"Loaded {len(cases)} case(s) from {args.input}")

    if args.dry_run:
        print("\n[DRY RUN] Would create items - no changes made")
        return

    print("\nItem creation not yet implemented")


if __name__ == '__main__':
    main()
