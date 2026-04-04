#!/usr/bin/env python3
"""
zotero_copy_items.py

Copy items between Zotero libraries (e.g., dissertation → comp-exam).
Copies metadata only — PDFs/attachments must be re-added manually.

Usage:
    # Copy specific items by key from source to target library
    python zotero_copy_items.py \
        --source-library 6042289 \
        --keys N36HWJF4 TQ37QUBM KA5PYJNE \
        --collection uasint \
        --dry-run

    # Target library set via ZOTERO_LIBRARY_ID env var
    ZOTERO_LIBRARY_ID=6448487 python zotero_copy_items.py \
        --source-library 6042289 \
        --keys N36HWJF4 TQ37QUBM \
        --collection uasint
"""

import argparse
import os
import sys
import time

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

RATE_LIMIT_DELAY = 0.5

# Fields to strip when copying (library-specific or non-transferable)
STRIP_FIELDS = {
    "key", "version", "dateAdded", "dateModified",
    "collections", "relations", "parentItem",
}


def connect_library(library_id: str, api_key: str) -> zotero.Zotero:
    """Connect to a Zotero group library."""
    return zotero.Zotero(library_id, "group", api_key)


def get_collection_key(zot: zotero.Zotero, name: str) -> str | None:
    """Find collection key by name (case-insensitive)."""
    for coll in zot.collections():
        if coll["data"].get("name", "").lower() == name.lower():
            return coll["key"]
    return None


def check_duplicate(zot: zotero.Zotero, title: str) -> str | None:
    """Check if item with same title exists in target library."""
    search_term = title[:80]
    try:
        results = zot.items(q=search_term, limit=10)
        for result in results:
            if result["data"].get("title", "").lower() == title.lower():
                return result["key"]
    except HTTPError:
        pass
    return None


def copy_item(
    source_zot: zotero.Zotero,
    target_zot: zotero.Zotero,
    item_key: str,
    collection_key: str | None,
    dry_run: bool = False,
) -> tuple[str, str | None]:
    """Copy a single item from source to target library.

    Returns (status, target_key) where status is 'created', 'skipped', or 'failed'.
    """
    # Get source item
    try:
        source_item = source_zot.item(item_key)
    except HTTPError as e:
        print(f"  ERROR: Could not fetch source item {item_key}: {e}")
        return ("failed", None)

    data = source_item["data"]
    title = data.get("title", "(untitled)")
    item_type = data.get("itemType", "unknown")

    # Skip non-regular items
    if item_type in ("attachment", "annotation", "note"):
        print(f"  SKIP (type={item_type}): {title[:60]}")
        return ("skipped", None)

    print(f"  {item_type}: {title[:70]}")

    if dry_run:
        return ("dry-run", None)

    # Check for duplicate in target
    existing = check_duplicate(target_zot, title)
    if existing:
        print(f"    SKIP (duplicate in target): {existing}")
        # Still add to collection if not already there
        if collection_key:
            try:
                target_item = target_zot.item(existing)
                target_zot.addto_collection(collection_key, target_item)
                print(f"    Added existing item to collection")
            except HTTPError:
                pass
        return ("skipped", existing)

    # Build template and merge data
    template = target_zot.item_template(item_type)
    for key, value in data.items():
        if key in STRIP_FIELDS or key == "itemType":
            continue
        if key == "creators":
            template["creators"] = value
            continue
        if key == "tags":
            # Strip dissertation-specific tags, keep generic ones
            template["tags"] = [
                t for t in value
                if not t.get("tag", "").startswith("#Sec-")
                and not t.get("tag", "").startswith("#RQ")
                and not t.get("tag", "").startswith("#Status-")
                and not t.get("tag", "").startswith("Status-")
            ]
            continue
        if key in template:
            template[key] = value

    # Create in target
    try:
        resp = target_zot.create_items([template])
        if resp.get("success"):
            new_key = list(resp["success"].values())[0]
            print(f"    CREATED: {new_key}")
            if collection_key:
                created_item = target_zot.item(new_key)
                target_zot.addto_collection(collection_key, created_item)
                print(f"    Added to collection")
            return ("created", new_key)
        else:
            print(f"    FAILED: {resp}")
            return ("failed", None)
    except HTTPError as e:
        print(f"    ERROR: {e}")
        return ("failed", None)


def main():
    parser = argparse.ArgumentParser(
        description="Copy items between Zotero libraries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source-library", "-s", required=True,
        help="Source library ID (e.g., 6042289 for uas-sightings)"
    )
    parser.add_argument(
        "--keys", "-k", nargs="+", required=True,
        help="Item keys to copy from source library"
    )
    parser.add_argument(
        "--collection", "-c", default=None,
        help="Target collection name in target library"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")

    args = parser.parse_args()

    # Target library from env/config
    target_id, target_type, api_key = load_credentials()
    source_id = args.source_library

    print(f"Source library: {source_id}")
    print(f"Target library: {target_id}")
    print(f"Items to copy: {len(args.keys)}")

    if source_id == str(target_id):
        print("ERROR: Source and target are the same library")
        sys.exit(1)

    # Connect
    source_zot = connect_library(source_id, api_key)
    target_zot = connect_library(str(target_id), api_key)

    # Resolve collection
    collection_key = None
    if args.collection:
        collection_key = get_collection_key(target_zot, args.collection)
        if not collection_key:
            print(f"ERROR: Collection '{args.collection}' not found in target library")
            print("\nAvailable collections:")
            for c in target_zot.collections():
                print(f"  - {c['data']['name']}")
            sys.exit(1)
        print(f"Target collection: {args.collection} ({collection_key})")

    if args.dry_run:
        print("\n[DRY RUN] Preview only:\n")

    # Copy items
    created = 0
    skipped = 0
    failed = 0

    for i, key in enumerate(args.keys, 1):
        print(f"\n[{i}/{len(args.keys)}] {key}")
        status, new_key = copy_item(
            source_zot, target_zot, key, collection_key, args.dry_run
        )
        if status == "created":
            created += 1
        elif status in ("skipped", "dry-run"):
            skipped += 1
        else:
            failed += 1

        if not args.dry_run and i < len(args.keys):
            time.sleep(RATE_LIMIT_DELAY)

    print(f"\n{'='*60}")
    print(f"Created: {created}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
