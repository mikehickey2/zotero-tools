#!/usr/bin/env python3
"""
zotero_multi_search.py

Multi-strategy search combining keyword and tag searches with deduplication
and relevance ranking.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_multi_search.py --query "LLM aviation"
    python zotero_multi_search.py --query "ASRS" --expand-tags
    python zotero_multi_search.py --query "inter-rater" --limit 10 --format json
    python zotero_multi_search.py --query "prompt" -v
"""

import argparse
import json
import os
import sys
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


def search_keyword_fulltext(zot: zotero.Zotero, query: str, limit: int = 50) -> list:
    """Search library by keyword (full-text mode)."""
    try:
        return zot.items(q=query, qmode='everything', limit=limit)
    except HTTPError as e:
        print(f"WARNING: Full-text search failed: {e}")
        return []


def search_keyword_title(zot: zotero.Zotero, query: str, limit: int = 50) -> list:
    """Search library by keyword (title/creator/year mode)."""
    try:
        return zot.items(q=query, qmode='titleCreatorYear', limit=limit)
    except HTTPError as e:
        print(f"WARNING: Title search failed: {e}")
        return []


def search_by_tags(zot: zotero.Zotero, query_terms: list[str], limit: int = 50) -> list:
    """Search for items matching tags that contain query terms."""
    try:
        all_tags = zot.tags()
        matching_tags = []

        for tag_obj in all_tags:
            # Handle both dict format {'tag': 'name'} and string format 'name'
            if isinstance(tag_obj, dict):
                tag_name = tag_obj.get('tag', '').lower()
                tag_value = tag_obj.get('tag', '')
            else:
                tag_name = str(tag_obj).lower()
                tag_value = str(tag_obj)

            for term in query_terms:
                if term.lower() in tag_name:
                    matching_tags.append(tag_value)
                    break

        if not matching_tags:
            return []

        # Fetch items for each matching tag
        items = []
        for tag in matching_tags[:5]:  # Limit to 5 tags to avoid API overload
            try:
                tag_items = zot.items(tag=tag, limit=limit // 5 or 10)
                items.extend(tag_items)
            except HTTPError:
                continue

        return items
    except HTTPError as e:
        print(f"WARNING: Tag search failed: {e}")
        return []


def merge_results(item_lists: list[list]) -> dict:
    """Merge multiple item lists, deduplicating by key."""
    merged = {}
    for items in item_lists:
        for item in items:
            key = item.get('key')
            if key and key not in merged:
                # Skip attachments and notes
                item_type = item.get('data', {}).get('itemType', '')
                if item_type not in ['attachment', 'note']:
                    merged[key] = item
    return merged


def score_item(item: dict, query_terms: list[str]) -> int:
    """Score an item based on query term relevance."""
    score = 0
    data = item.get('data', {})

    title = data.get('title', '').lower()
    abstract = data.get('abstractNote', '').lower()
    tags = [t.get('tag', '').lower() for t in data.get('tags', [])]

    for term in query_terms:
        term_lower = term.lower()
        if term_lower in title:
            score += 10  # Title match
        if term_lower in abstract:
            score += 2   # Abstract match
        if any(term_lower in tag for tag in tags):
            score += 5   # Tag match

    # Recency bonus
    year = data.get('date', '')[:4] if data.get('date') else ''
    if year and year.isdigit():
        if int(year) >= 2024:
            score += 3
        elif int(year) >= 2023:
            score += 1

    return score


def rank_results(items: dict, query_terms: list[str]) -> list:
    """Rank items by relevance score."""
    scored = [(item, score_item(item, query_terms)) for item in items.values()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored]


def format_item_markdown(item: dict, score: Optional[int] = None) -> str:
    """Format a single item as markdown."""
    data = item['data']

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
    item_type = data.get('itemType', 'unknown')

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

    if score is not None:
        lines.append(f"- **Relevance:** {score}")

    lines.append(f"- **Zotero:** [Open](zotero://select/library/items/{item['key']})")
    lines.append("")

    return '\n'.join(lines)


def format_item_json(item: dict, score: Optional[int] = None) -> dict:
    """Format a single item as a simplified dict."""
    data = item['data']

    creators = data.get('creators', [])
    if creators:
        first_author = creators[0].get('lastName', creators[0].get('name', 'Unknown'))
        authors = [c.get('lastName', c.get('name', '')) for c in creators]
    else:
        first_author = "Unknown"
        authors = []

    result = {
        'key': item['key'],
        'title': data.get('title', ''),
        'authors': authors,
        'first_author': first_author,
        'year': data.get('date', '')[:4] if data.get('date') else '',
        'type': data.get('itemType', ''),
        'tags': [t.get('tag', '') for t in data.get('tags', [])],
        'date_added': data.get('dateAdded', ''),
    }

    if score is not None:
        result['relevance_score'] = score

    return result


def output_results(items: list, query_terms: list[str], format_type: str,
                   output_file: Optional[str] = None, show_scores: bool = False):
    """Output results in specified format."""
    if format_type == 'md':
        lines = [f"# Multi-Strategy Search Results", f"*{len(items)} items found*\n"]
        for item in items:
            score = score_item(item, query_terms) if show_scores else None
            md = format_item_markdown(item, score)
            if md:
                lines.append(md)
        output = '\n'.join(lines)
    else:  # json
        formatted = []
        for item in items:
            score = score_item(item, query_terms) if show_scores else None
            formatted.append(format_item_json(item, score))
        output = json.dumps(formatted, indent=2)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Results written to: {output_file}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-strategy Zotero search with deduplication and ranking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --query "LLM aviation"              Multi-strategy keyword search
  %(prog)s --query "ASRS" --expand-tags        Include tag-based search
  %(prog)s --query "inter-rater" --limit 10    Limit results
  %(prog)s --query "prompt" -v                 Verbose output
  %(prog)s --query "safety" --format json      JSON output
        """
    )

    parser.add_argument('--query', '-q', required=True,
                        help='Search query (searches title, author, full-text)')
    parser.add_argument('--expand-tags', '-e', action='store_true',
                        help='Also search for matching tags')
    parser.add_argument('--limit', '-l', type=int, default=15,
                        help='Maximum items to return (default: 15)')
    parser.add_argument('--format', '-f', choices=['md', 'json'], default='md',
                        help='Output format (default: md)')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write output to file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show search breakdown and scores')

    args = parser.parse_args()

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

    # Parse query into terms
    query_terms = args.query.split()

    # Execute searches
    if args.verbose:
        print(f"\nSearching for: {args.query}")
        print("-" * 40)

    # Strategy 1: Full-text search
    fulltext_items = search_keyword_fulltext(zot, args.query)
    if args.verbose:
        print(f"Full-text search: {len(fulltext_items)} items")

    # Strategy 2: Title/creator/year search
    title_items = search_keyword_title(zot, args.query)
    if args.verbose:
        print(f"Title/author search: {len(title_items)} items")

    # Strategy 3: Tag search (optional)
    tag_items = []
    if args.expand_tags:
        tag_items = search_by_tags(zot, query_terms)
        if args.verbose:
            print(f"Tag search: {len(tag_items)} items")

    # Merge and deduplicate
    merged = merge_results([fulltext_items, title_items, tag_items])
    if args.verbose:
        print(f"-" * 40)
        print(f"Unique items after dedup: {len(merged)}")

    # Rank by relevance
    ranked = rank_results(merged, query_terms)

    # Limit results
    limited = ranked[:args.limit]

    if args.verbose:
        print(f"Returning top {len(limited)} results\n")

    # Output
    if limited:
        output_results(limited, query_terms, args.format, args.output,
                       show_scores=args.verbose)
    else:
        print("No items found.")


if __name__ == '__main__':
    main()
