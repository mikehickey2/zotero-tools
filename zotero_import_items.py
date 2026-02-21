#!/usr/bin/env python3
"""
zotero_import_items.py

Import pre-formatted items into a Zotero library from a JSON file.
Supports any Zotero item type (report, newspaperArticle, webpage, etc.).

Usage:
    python zotero_import_items.py --input data/grey_lit_import.json --dry-run
    python zotero_import_items.py --input data/grey_lit_import.json --collection "00-Inbox"
"""

import argparse
import json
import sys
import time
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

RATE_LIMIT_DELAY = 0.5

REQUIRED_FIELDS = {
    "report": ["title", "creators"],
    "newspaperArticle": ["title", "creators"],
    "webpage": ["title", "creators", "url"],
    "journalArticle": ["title", "creators"],
    "book": ["title", "creators"],
    "document": ["title", "creators"],
}


def load_items(json_path: str) -> list[dict]:
    """Load and validate JSON array of Zotero items."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: File not found: {json_path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("ERROR: JSON must be an array of items")
        sys.exit(1)

    for i, item in enumerate(data):
        if "itemType" not in item:
            print(f"ERROR: Item {i} missing required field 'itemType'")
            sys.exit(1)
        if "title" not in item:
            print(f"ERROR: Item {i} missing required field 'title'")
            sys.exit(1)

    return data


def validate_item(item: dict) -> list[str]:
    """Check recommended fields per itemType. Returns warning strings."""
    warnings = []
    item_type = item.get("itemType", "unknown")
    required = REQUIRED_FIELDS.get(item_type, ["title", "creators"])

    for field in required:
        if field not in item or not item[field]:
            warnings.append(f"Missing recommended field '{field}' for {item_type}")

    return warnings


def get_collection_key(zot: zotero.Zotero, collection_name: str) -> str | None:
    """Find collection key by name (case-insensitive)."""
    collections = zot.collections()
    for coll in collections:
        if coll["data"].get("name", "").lower() == collection_name.lower():
            return coll["key"]
    return None


def check_duplicate(zot: zotero.Zotero, item: dict) -> str | None:
    """Check if an item with matching title or reportNumber already exists."""
    title = item.get("title", "")
    report_number = item.get("reportNumber", "")

    search_term = title[:80]
    try:
        results = zot.items(q=search_term, limit=10)
        for result in results:
            data = result["data"]
            if report_number and data.get("reportNumber") == report_number:
                return result["key"]
            if report_number and report_number in data.get("url", ""):
                return result["key"]
            if data.get("title", "").lower() == title.lower():
                return result["key"]
    except HTTPError:
        pass

    return None


def create_item(
    zot: zotero.Zotero, item: dict, collection_key: str | None
) -> str | None:
    """Create a Zotero item from pre-formatted dict. Returns item key or None."""
    item_type = item["itemType"]
    template = zot.item_template(item_type)

    # Merge fields into template
    for key, value in item.items():
        if key == "itemType":
            continue
        if key == "creators":
            template["creators"] = value
            continue
        if key in template:
            template[key] = value

    resp = zot.create_items([template])

    if resp.get("success"):
        item_key = list(resp["success"].values())[0]
        if collection_key:
            created = zot.item(item_key)
            zot.addto_collection(collection_key, created)
        return item_key

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Import pre-formatted items into Zotero from JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True, help="Path to JSON file")
    parser.add_argument(
        "--collection", "-c", default="00-Inbox", help="Collection name (default: 00-Inbox)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    items = load_items(args.input)
    print(f"Loaded {len(items)} item(s) from {args.input}")

    # Validate and preview
    for i, item in enumerate(items, 1):
        warnings = validate_item(item)
        if args.verbose or args.dry_run:
            print(f"\n{'='*60}")
            print(f"[{i}/{len(items)}] {item['itemType']}: {item['title'][:70]}")
            if item.get("reportNumber"):
                print(f"  Report #: {item['reportNumber']}")
            if item.get("date"):
                print(f"  Date: {item['date']}")
            if item.get("url"):
                print(f"  URL: {item['url']}")
            for w in warnings:
                print(f"  ⚠ {w}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would create {len(items)} item(s) in '{args.collection}'")
        return

    # Connect to Zotero
    library_id, library_type, api_key = load_credentials()
    if args.verbose:
        print(f"\nConnecting to Zotero ({library_type} library: {library_id})...")

    zot = zotero.Zotero(library_id, library_type, api_key)

    # Resolve collection
    collection_key = None
    if args.collection:
        collection_key = get_collection_key(zot, args.collection)
        if not collection_key:
            print(f"ERROR: Collection '{args.collection}' not found")
            print("\nAvailable collections:")
            for c in zot.collections():
                print(f"  - {c['data']['name']}")
            sys.exit(1)
        if args.verbose:
            print(f"Target collection: {args.collection} (key: {collection_key})")

    # Create items
    created = 0
    skipped = 0
    failed = 0

    for i, item in enumerate(items, 1):
        try:
            existing = check_duplicate(zot, item)
            if existing:
                print(f"  [{i}/{len(items)}] SKIP (duplicate): {item['title'][:50]}... -> {existing}")
                skipped += 1
                continue

            item_key = create_item(zot, item, collection_key)
            if item_key:
                print(f"  [{i}/{len(items)}] Created: {item['title'][:50]}... -> {item_key}")
                if collection_key:
                    print(f"    Added to: {args.collection}")
                created += 1
            else:
                print(f"  [{i}/{len(items)}] FAILED: {item['title'][:50]}...")
                failed += 1

            if i < len(items):
                time.sleep(RATE_LIMIT_DELAY)

        except HTTPError as e:
            print(f"  [{i}/{len(items)}] ERROR: {item['title'][:50]}... — {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Created: {created}")
    print(f"Skipped (duplicate): {skipped}")
    print(f"Failed: {failed}")
    print(f"Total: {len(items)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
