#!/usr/bin/env python3
"""
zotero_tag_migrate.py

Migrate Zotero tags using a JSON mapping file.

For each item matched by a search query (or all items in a collection),
removes tags matching specified patterns and adds new tags per a mapping.
All other tags are preserved.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_tag_migrate.py --map migration.json --dry-run
    python zotero_tag_migrate.py --map migration.json --collection "Methods"
    python zotero_tag_migrate.py --map migration.json --delete-pattern "#A1-*"
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials


RATE_LIMIT_DEFAULT = 1.0
SKIP_ITEM_TYPES = {'attachment', 'annotation', 'note'}


def load_migration_map(map_path: str) -> dict:
    """
    Load tag migration map from JSON file.

    Expected format:
    {
        "mappings": [
            {
                "old_tag": "#A1-01a-Prior",
                "new_tags": ["#Sec-LitReview", "#RQ1"]
            }
        ],
        "delete_patterns": ["#NonDiss-*", "cs\\\\..*"]
    }

    Returns:
        Dict with 'mappings' list and optional 'delete_patterns' list.
    """
    path = Path(map_path)
    if not path.exists():
        print(f"ERROR: Migration map not found: {map_path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    mappings = data.get('mappings', [])
    delete_patterns = data.get('delete_patterns', [])

    # Validate structure
    for i, m in enumerate(mappings):
        if 'old_tag' not in m or 'new_tags' not in m:
            print(f"ERROR: Mapping {i} missing 'old_tag' or 'new_tags' field")
            sys.exit(1)

    print(f"Loaded migration map: {len(mappings)} tag mappings, "
          f"{len(delete_patterns)} delete patterns")
    return data


def tag_matches_pattern(tag: str, pattern: str) -> bool:
    """Check if a tag matches a glob-style pattern (supports * wildcard)."""
    regex = re.escape(pattern).replace(r'\*', '.*')
    return bool(re.fullmatch(regex, tag, re.IGNORECASE))


def compute_tag_changes(
    current_tags: list[str],
    mappings: list[dict],
    delete_patterns: list[str],
    cli_delete_patterns: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Compute which tags to remove and add for an item.

    Args:
        current_tags: List of current tag strings on the item.
        mappings: List of {old_tag, new_tags} dicts.
        delete_patterns: Patterns from migration map file.
        cli_delete_patterns: Patterns from --delete-pattern CLI args.

    Returns:
        Tuple of (tags_to_remove, tags_to_add, final_tags).
    """
    tags_to_remove = set()
    tags_to_add = set()
    all_delete_patterns = delete_patterns + cli_delete_patterns

    # Apply mappings: if old_tag matches, queue removal + addition
    for mapping in mappings:
        old_tag = mapping['old_tag']
        new_tags = mapping['new_tags']
        if old_tag in current_tags:
            tags_to_remove.add(old_tag)
            for new_tag in new_tags:
                tags_to_add.add(new_tag)

    # Apply delete patterns: remove any tag matching a pattern
    for tag in current_tags:
        for pattern in all_delete_patterns:
            if tag_matches_pattern(tag, pattern):
                tags_to_remove.add(tag)
                break

    # Don't add tags that already exist
    tags_to_add -= set(current_tags)
    # Don't add tags we're also removing (edge case: mapping adds a tag
    # that matches a delete pattern — removal wins)
    tags_to_add -= tags_to_remove

    # Compute final tag list
    surviving = [t for t in current_tags if t not in tags_to_remove]
    final_tags = surviving + sorted(tags_to_add)

    return sorted(tags_to_remove), sorted(tags_to_add), final_tags


def fetch_items(
    zot: zotero.Zotero,
    collection_key: str | None = None,
    query: str | None = None,
    item_keys: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch items from Zotero, filtering out non-content types.

    Args:
        zot: Initialized Zotero client.
        collection_key: Optional collection key to scope the fetch.
        query: Optional search query.
        item_keys: Optional list of specific item keys.
        limit: Maximum items to fetch per request.

    Returns:
        List of Zotero item dicts (content items only).
    """
    if item_keys:
        items = []
        for key in item_keys:
            items.append(zot.item(key))
        return items

    kwargs = {'limit': limit}
    if query:
        kwargs['q'] = query

    if collection_key:
        items = zot.collection_items(collection_key, **kwargs)
    else:
        items = zot.items(**kwargs)

    # Filter out attachments, annotations, notes
    return [
        item for item in items
        if item['data'].get('itemType') not in SKIP_ITEM_TYPES
    ]


def resolve_collection_key(zot: zotero.Zotero, name: str) -> str | None:
    """Find collection key by name (case-insensitive)."""
    for coll in zot.collections():
        if coll['data'].get('name', '').lower() == name.lower():
            return coll['key']
    return None


def migrate_tags(
    zot: zotero.Zotero,
    items: list[dict],
    mappings: list[dict],
    delete_patterns: list[str],
    cli_delete_patterns: list[str],
    dry_run: bool = True,
    verbose: bool = False,
    rate_limit: float = RATE_LIMIT_DEFAULT,
    audit_log_path: str | None = None,
) -> dict:
    """
    Apply tag migration to a list of items.

    Returns:
        Stats dict with counts and audit log entries.
    """
    stats = {
        'total': len(items),
        'changed': 0,
        'unchanged': 0,
        'errors': 0,
        'tags_removed': 0,
        'tags_added': 0,
    }
    audit_entries = []
    mode = "[DRY RUN] " if dry_run else ""

    for i, item in enumerate(items, 1):
        data = item['data']
        item_key = data.get('key', item.get('key', '???'))
        title = data.get('title', '(no title)')
        current_tags = [t['tag'] for t in data.get('tags', [])]

        to_remove, to_add, final_tags = compute_tag_changes(
            current_tags, mappings, delete_patterns, cli_delete_patterns,
        )

        if not to_remove and not to_add:
            stats['unchanged'] += 1
            if verbose:
                print(f"  [{i}/{len(items)}] No change: {title[:60]}")
            continue

        stats['changed'] += 1
        stats['tags_removed'] += len(to_remove)
        stats['tags_added'] += len(to_add)

        title_display = title[:55] + "..." if len(title) > 55 else title
        print(f"{mode}[{i}/{len(items)}] {title_display}")
        if to_remove:
            print(f"  - Remove: {', '.join(to_remove)}")
        if to_add:
            print(f"  + Add:    {', '.join(to_add)}")

        # Record audit entry
        audit_entries.append({
            'item_key': item_key,
            'title': title,
            'tags_removed': to_remove,
            'tags_added': to_add,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })

        # Apply changes
        if not dry_run:
            data['tags'] = [{'tag': t} for t in final_tags]
            try:
                zot.update_item(item)
            except HTTPError as e:
                print(f"  ERROR: {e}")
                stats['errors'] += 1
                continue

            if i < len(items):
                time.sleep(rate_limit)

    # Write audit log
    if audit_log_path and audit_entries:
        path = Path(audit_log_path)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(audit_entries, f, indent=2)
        print(f"\nAudit log written to: {path}")

    return stats


def print_summary(stats: dict, dry_run: bool):
    """Print migration summary."""
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"{mode}MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total items scanned:   {stats['total']}")
    print(f"Items changed:         {stats['changed']}")
    print(f"Items unchanged:       {stats['unchanged']}")
    print(f"Tags removed:          {stats['tags_removed']}")
    print(f"Tags added:            {stats['tags_added']}")
    if stats['errors']:
        print(f"Errors:                {stats['errors']}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Zotero tags using a JSON mapping file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Migration map format (JSON):
  {
    "mappings": [
      {"old_tag": "#A1-01a-Prior", "new_tags": ["#Sec-LitReview"]}
    ],
    "delete_patterns": ["#NonDiss-*", "cs\\\\..*"]
  }

Examples:
  %(prog)s --map migration.json --dry-run
  %(prog)s --map migration.json --collection "Methods" --verbose
  %(prog)s --map migration.json --delete-pattern "#A1-*" --dry-run
  %(prog)s --map migration.json --items KEY1 KEY2 KEY3

Environment variables (or .env file):
  ZOTERO_LIBRARY_ID     Your Zotero library ID
  ZOTERO_LIBRARY_TYPE   'group' (default) or 'user'
  ZOTERO_API_KEY        Your Zotero API key
        """
    )
    parser.add_argument(
        '--map', '-m', required=True, dest='map_path',
        help='Path to migration map JSON file'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview changes without modifying (recommended first run)'
    )
    parser.add_argument(
        '--collection', '-c',
        help='Limit migration to items in this collection (by name)'
    )
    parser.add_argument(
        '--query', '-q',
        help='Limit migration to items matching this search query'
    )
    parser.add_argument(
        '--items', nargs='+', metavar='KEY',
        help='Migrate specific items by Zotero item key'
    )
    parser.add_argument(
        '--delete-pattern', action='append', default=[],
        help='Additional tag patterns to delete (glob-style, e.g. "#A1-*"). '
             'Can be specified multiple times.'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show unchanged items in output'
    )
    parser.add_argument(
        '--audit-log', metavar='PATH',
        help='Write JSON audit log of all changes to this path'
    )
    parser.add_argument(
        '--rate-limit', type=float, default=RATE_LIMIT_DEFAULT,
        metavar='SECONDS',
        help=f'Delay between API writes (default: {RATE_LIMIT_DEFAULT}s)'
    )
    parser.add_argument(
        '--limit', type=int, default=100,
        help='Maximum number of items to fetch (default: 100)'
    )

    args = parser.parse_args()

    # Load migration map
    migration_data = load_migration_map(args.map_path)
    mappings = migration_data.get('mappings', [])
    delete_patterns = migration_data.get('delete_patterns', [])

    # Load credentials and connect
    library_id, library_type, api_key = load_credentials()

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print(f"Connected to Zotero ({library_type} library: {library_id})")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Resolve collection name to key
    collection_key = None
    if args.collection:
        collection_key = resolve_collection_key(zot, args.collection)
        if not collection_key:
            print(f"ERROR: Collection '{args.collection}' not found")
            sys.exit(1)
        print(f"Scoping to collection: {args.collection} ({collection_key})")

    # Fetch items
    print(f"\nFetching items (limit: {args.limit})...")
    items = fetch_items(
        zot,
        collection_key=collection_key,
        query=args.query,
        item_keys=args.items,
        limit=args.limit,
    )
    print(f"Found {len(items)} content items")

    if not items:
        print("No items to process.")
        sys.exit(0)

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN MODE — No changes will be made")
        print(f"{'='*60}")

    # Run migration
    stats = migrate_tags(
        zot, items, mappings, delete_patterns,
        cli_delete_patterns=args.delete_pattern,
        dry_run=args.dry_run,
        verbose=args.verbose,
        rate_limit=args.rate_limit,
        audit_log_path=args.audit_log,
    )

    print_summary(stats, args.dry_run)

    if stats['errors']:
        sys.exit(1)


if __name__ == '__main__':
    main()
