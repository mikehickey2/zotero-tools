#!/usr/bin/env python3
"""
zotero_search.py

Search and browse a Zotero library via the API.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_search.py --query "LLM aviation"          # Search by keyword
    python zotero_search.py --collection "Methods"          # List collection items
    python zotero_search.py --recent 7                      # Items added last 7 days
    python zotero_search.py --tag "#A1-02a-LLM-Aviation"    # Filter by tag
    python zotero_search.py --list-collections              # Show all collections
    python zotero_search.py --format md --output results.md # Export to markdown
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError


def load_credentials() -> tuple[str, str, str]:
    """Load Zotero credentials from environment."""
    load_dotenv()

    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')
    api_key = os.getenv('ZOTERO_API_KEY')

    missing = []
    if not library_id:
        missing.append('ZOTERO_LIBRARY_ID')
    if not api_key:
        missing.append('ZOTERO_API_KEY')

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        sys.exit(1)

    return library_id, library_type, api_key


def get_collection_key(zot: zotero.Zotero, collection_name: str) -> Optional[str]:
    """Find collection key by name (case-insensitive)."""
    collections = zot.collections()
    for coll in collections:
        if coll['data'].get('name', '').lower() == collection_name.lower():
            return coll['key']
    return None


def format_item_markdown(item: dict) -> str:
    """Format a single item as markdown."""
    data = item['data']
    item_type = data.get('itemType', 'unknown')

    if item_type in ['attachment', 'note']:
        return ""

    title = data.get('title', '(no title)')

    # Get authors
    creators = data.get('creators', [])
    if creators:
        first_author = creators[0].get('lastName', creators[0].get('name', 'Unknown'))
        if len(creators) > 1:
            authors = f"{first_author} et al."
        else:
            authors = first_author
    else:
        authors = "Unknown"

    year = data.get('date', '')[:4] if data.get('date') else 'n.d.'

    # Get tags
    tags = [t.get('tag', '') for t in data.get('tags', [])]
    tags_str = ', '.join(tags) if tags else 'none'

    # Get citation key if available
    citekey = data.get('extra', '')
    if 'Citation Key:' in citekey:
        citekey = citekey.split('Citation Key:')[1].split('\n')[0].strip()
    else:
        citekey = ''

    lines = [
        f"### {title}",
        f"- **Authors:** {authors}",
        f"- **Year:** {year}",
        f"- **Type:** {item_type}",
    ]

    if citekey:
        lines.append(f"- **Citekey:** `{citekey}`")

    lines.append(f"- **Tags:** {tags_str}")
    lines.append(f"- **Zotero:** [Open](zotero://select/library/items/{item['key']})")
    lines.append("")

    return '\n'.join(lines)


def format_item_json(item: dict) -> dict:
    """Format a single item as a simplified dict."""
    data = item['data']

    if data.get('itemType') in ['attachment', 'note']:
        return None

    creators = data.get('creators', [])
    if creators:
        first_author = creators[0].get('lastName', creators[0].get('name', 'Unknown'))
        authors = [
            c.get('lastName', c.get('name', ''))
            for c in creators
        ]
    else:
        first_author = "Unknown"
        authors = []

    return {
        'key': item['key'],
        'title': data.get('title', ''),
        'authors': authors,
        'first_author': first_author,
        'year': data.get('date', '')[:4] if data.get('date') else '',
        'type': data.get('itemType', ''),
        'tags': [t.get('tag', '') for t in data.get('tags', [])],
        'date_added': data.get('dateAdded', ''),
    }


def search_library(zot: zotero.Zotero, query: str, limit: int = 50) -> list:
    """Search library by keyword."""
    try:
        items = zot.items(q=query, limit=limit)
        return items
    except HTTPError as e:
        print(f"ERROR: Search failed: {e}")
        return []


def get_collection_items(zot: zotero.Zotero, collection_key: str, limit: int = 100) -> list:
    """Get all items in a collection."""
    try:
        items = zot.collection_items(collection_key, limit=limit)
        return items
    except HTTPError as e:
        print(f"ERROR: Failed to get collection items: {e}")
        return []


def get_recent_items(zot: zotero.Zotero, days: int = 7, limit: int = 50) -> list:
    """Get items added in the last N days."""
    try:
        # Get all items sorted by date added (descending)
        items = zot.items(sort='dateAdded', direction='desc', limit=limit)

        # Filter by date
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for item in items:
            date_added = item['data'].get('dateAdded', '')
            if date_added:
                try:
                    item_date = datetime.fromisoformat(date_added.replace('Z', '+00:00'))
                    if item_date.replace(tzinfo=None) >= cutoff:
                        recent.append(item)
                except ValueError:
                    pass

        return recent
    except HTTPError as e:
        print(f"ERROR: Failed to get recent items: {e}")
        return []


def get_items_by_tag(zot: zotero.Zotero, tag: str, limit: int = 100) -> list:
    """Get items with a specific tag."""
    try:
        items = zot.items(tag=tag, limit=limit)
        return items
    except HTTPError as e:
        print(f"ERROR: Failed to get items by tag: {e}")
        return []


def list_collections(zot: zotero.Zotero) -> list:
    """Get all collections with item counts."""
    try:
        collections = zot.collections()
        result = []
        for coll in collections:
            data = coll['data']
            if not data.get('deleted', False):
                result.append({
                    'key': coll['key'],
                    'name': data.get('name', ''),
                    'item_count': coll['meta'].get('numItems', 0),
                })
        return sorted(result, key=lambda x: x['name'].lower())
    except HTTPError as e:
        print(f"ERROR: Failed to list collections: {e}")
        return []


def list_tags(zot: zotero.Zotero) -> list:
    """Get all tags with usage counts."""
    try:
        tags = zot.tags()
        result = []
        for tag in tags:
            result.append({
                'tag': tag['tag'],
                'count': tag['meta'].get('numItems', 0),
            })
        return sorted(result, key=lambda x: (-x['count'], x['tag'].lower()))
    except HTTPError as e:
        print(f"ERROR: Failed to list tags: {e}")
        return []


def output_results(items: list, format_type: str, output_file: Optional[str] = None):
    """Output results in specified format."""
    if format_type == 'md':
        lines = [f"# Zotero Search Results", f"*{len(items)} items found*\n"]
        for item in items:
            md = format_item_markdown(item)
            if md:
                lines.append(md)
        output = '\n'.join(lines)
    else:  # json
        formatted = [format_item_json(item) for item in items]
        formatted = [f for f in formatted if f is not None]
        output = json.dumps(formatted, indent=2)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Results written to: {output_file}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Search and browse a Zotero library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --query "LLM aviation"           Search by keyword
  %(prog)s --collection "Methods"           List items in collection
  %(prog)s --recent 7                       Items added last 7 days
  %(prog)s --tag "#A1-02a-LLM-Aviation"     Filter by tag
  %(prog)s --list-collections               Show all collections
  %(prog)s --list-tags                      Show all tags with counts
  %(prog)s --format md --output results.md  Export to markdown
        """
    )

    # Search/filter options
    parser.add_argument('--query', '-q', help='Search query (title, author, full-text)')
    parser.add_argument('--collection', '-c', help='Collection name to list')
    parser.add_argument('--recent', '-r', type=int, metavar='DAYS',
                        help='Show items added in last N days')
    parser.add_argument('--tag', '-t', help='Filter by tag')

    # List options
    parser.add_argument('--list-collections', action='store_true',
                        help='List all collections')
    parser.add_argument('--list-tags', action='store_true',
                        help='List all tags with usage counts')

    # Output options
    parser.add_argument('--format', '-f', choices=['md', 'json'], default='md',
                        help='Output format (default: md)')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write output to file')
    parser.add_argument('--limit', '-l', type=int, default=50,
                        help='Maximum items to return (default: 50)')

    # Verbose
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Require at least one action
    if not any([args.query, args.collection, args.recent, args.tag,
                args.list_collections, args.list_tags]):
        parser.print_help()
        sys.exit(1)

    # Load credentials and connect
    library_id, library_type, api_key = load_credentials()

    if args.verbose:
        print(f"Connecting to Zotero ({library_type} library: {library_id})...")

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Execute requested action
    if args.list_collections:
        collections = list_collections(zot)
        print(f"\n{'Collection':<35} Items")
        print("-" * 45)
        for coll in collections:
            print(f"{coll['name']:<35} {coll['item_count']:>5}")
        print("-" * 45)
        print(f"{'Total collections:':<35} {len(collections):>5}")

    elif args.list_tags:
        tags = list_tags(zot)
        print(f"\n{'Tag':<40} Count")
        print("-" * 50)
        for tag in tags[:30]:  # Top 30
            print(f"{tag['tag']:<40} {tag['count']:>5}")
        if len(tags) > 30:
            print(f"... and {len(tags) - 30} more tags")

    elif args.query:
        if args.verbose:
            print(f"Searching for: {args.query}")
        items = search_library(zot, args.query, limit=args.limit)
        if items:
            output_results(items, args.format, args.output)
        else:
            print("No items found.")

    elif args.collection:
        collection_key = get_collection_key(zot, args.collection)
        if not collection_key:
            print(f"Collection '{args.collection}' not found.")
            print("\nAvailable collections:")
            for coll in list_collections(zot):
                print(f"  - {coll['name']}")
            sys.exit(1)

        if args.verbose:
            print(f"Getting items from collection: {args.collection}")
        items = get_collection_items(zot, collection_key, limit=args.limit)
        if items:
            output_results(items, args.format, args.output)
        else:
            print("No items in collection.")

    elif args.recent:
        if args.verbose:
            print(f"Getting items added in last {args.recent} days")
        items = get_recent_items(zot, days=args.recent, limit=args.limit)
        if items:
            output_results(items, args.format, args.output)
        else:
            print(f"No items added in the last {args.recent} days.")

    elif args.tag:
        if args.verbose:
            print(f"Getting items with tag: {args.tag}")
        items = get_items_by_tag(zot, args.tag, limit=args.limit)
        if items:
            output_results(items, args.format, args.output)
        else:
            print(f"No items found with tag '{args.tag}'.")


if __name__ == '__main__':
    main()
