#!/usr/bin/env python3
"""
zotero_dedup.py

Find and remove duplicate items in a Zotero group library.

Root cause: BBT export + re-import created a duplicate of every item.
Strategy: Match by DOI or normalized title+author+year, keep the original
(earlier dateAdded), merge tags/collections/children, trash the duplicate.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_dedup.py --backup                    # Export full library JSON
    python zotero_dedup.py --dry-run --verbose         # Preview what would happen
    python zotero_dedup.py --execute                   # Perform dedup (requires prior backup)
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

RATE_LIMIT_DELAY = 0.5
SKIP_ITEM_TYPES = {'attachment', 'annotation', 'note'}
BACKUP_DIR = Path(__file__).parent / 'backups'
FUZZY_THRESHOLD = 0.90


def normalize_title(title: str) -> str:
    """Normalize title for comparison: lowercase, strip punctuation, collapse whitespace."""
    title = title.lower().strip()
    title = unicodedata.normalize('NFKD', title)
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title


def get_first_author_last(creators: list[dict]) -> str:
    """Extract first author's last name, normalized."""
    if not creators:
        return ''
    first = creators[0]
    last_name = first.get('lastName', '')
    if not last_name:
        # Handle single-field name (e.g., "National Transportation Safety Board")
        name = first.get('name', '')
        last_name = name.split()[-1] if name else ''
    return last_name.lower().strip()


def get_doi(data: dict) -> str:
    """Extract DOI from item data, normalized."""
    doi = data.get('DOI', '').strip().lower()
    if not doi:
        # Check extra field for DOI
        extra = data.get('extra', '')
        doi_match = re.search(r'doi:\s*(10\.\S+)', extra, re.IGNORECASE)
        if doi_match:
            doi = doi_match.group(1).lower()
    return doi


def simple_similarity(a: str, b: str) -> float:
    """Simple character-level similarity ratio (avoids external dependency)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Use longest common subsequence ratio
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0
    # Quick length check
    if min(len_a, len_b) / max(len_a, len_b) < 0.5:
        return 0.0
    # Character overlap ratio (fast approximation)
    set_a, set_b = set(a), set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    jaccard = intersection / union if union else 0.0
    # Also check shared bigrams for order sensitivity
    bigrams_a = {a[i:i+2] for i in range(len(a)-1)}
    bigrams_b = {b[i:i+2] for i in range(len(b)-1)}
    if bigrams_a and bigrams_b:
        bigram_sim = len(bigrams_a & bigrams_b) / len(bigrams_a | bigrams_b)
    else:
        bigram_sim = 0.0
    return (jaccard + bigram_sim) / 2


def backup_library(zot: zotero.Zotero) -> Path:
    """Export entire library as JSON for backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d')
    backup_path = BACKUP_DIR / f'pre-dedup-{timestamp}.json'

    print("Fetching all items for backup...")
    items = zot.everything(zot.items())
    print(f"  Retrieved {len(items)} total items")

    # Also get collections
    collections = zot.collections()
    print(f"  Retrieved {len(collections)} collections")

    backup_data = {
        'timestamp': datetime.now().isoformat(),
        'item_count': len(items),
        'collection_count': len(collections),
        'items': items,
        'collections': collections,
    }

    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"  Backup saved: {backup_path} ({size_mb:.1f} MB)")
    return backup_path


def find_duplicates(items: list[dict], verbose: bool = False) -> dict:
    """
    Find duplicate items using tiered confidence matching.

    Returns dict with:
        'tier1': [(keeper, duplicate), ...] — DOI or exact match (auto-merge)
        'tier2': [(keeper, duplicate), ...] — normalized match (auto-merge)
        'tier3': [(keeper, duplicate, similarity), ...] — fuzzy (review required)
    """
    content_items = [
        i for i in items
        if i['data'].get('itemType') not in SKIP_ITEM_TYPES
    ]
    print(f"  Analyzing {len(content_items)} content items...")

    # Index by DOI
    doi_index: dict[str, list] = {}
    # Index by normalized title+author+year
    key_index: dict[str, list] = {}

    for item in content_items:
        data = item['data']
        doi = get_doi(data)
        if doi:
            doi_index.setdefault(doi, []).append(item)

        title = normalize_title(data.get('title', ''))
        author = get_first_author_last(data.get('creators', []))
        year = data.get('date', '')[:4]
        if title:
            key = f"{title}|{author}|{year}"
            key_index.setdefault(key, []).append(item)

    tier1 = []
    tier2 = []
    tier3 = []
    seen_keys = set()  # Track items already matched to avoid double-counting

    # Tier 1: DOI matches
    for doi, group in doi_index.items():
        if len(group) < 2:
            continue
        # Sort by dateAdded — earliest is the keeper
        group.sort(key=lambda x: x['data'].get('dateAdded', ''))
        keeper = group[0]
        for dup in group[1:]:
            pair_key = tuple(sorted([keeper['key'], dup['key']]))
            if pair_key not in seen_keys:
                seen_keys.add(pair_key)
                tier1.append((keeper, dup))
                if verbose:
                    print(f"    T1 DOI: {doi[:50]} — keep {keeper['key']}, trash {dup['key']}")

    # Tier 2: Exact normalized title+author+year
    for key, group in key_index.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x['data'].get('dateAdded', ''))
        keeper = group[0]
        for dup in group[1:]:
            pair_key = tuple(sorted([keeper['key'], dup['key']]))
            if pair_key not in seen_keys:
                seen_keys.add(pair_key)
                tier2.append((keeper, dup))
                if verbose:
                    title = keeper['data'].get('title', '')[:60]
                    print(f"    T2 Key: {title}... — keep {keeper['key']}, trash {dup['key']}")

    # Tier 3: Fuzzy title matching (only for items not already matched)
    matched_keys = set()
    for keeper, dup in tier1 + tier2:
        matched_keys.add(keeper['key'])
        matched_keys.add(dup['key'])

    unmatched = [i for i in content_items if i['key'] not in matched_keys]
    # Compare all unmatched pairs (O(n^2) but n should be small after T1+T2)
    for i, item_a in enumerate(unmatched):
        title_a = normalize_title(item_a['data'].get('title', ''))
        if not title_a:
            continue
        for item_b in unmatched[i+1:]:
            title_b = normalize_title(item_b['data'].get('title', ''))
            if not title_b:
                continue
            sim = simple_similarity(title_a, title_b)
            if sim >= FUZZY_THRESHOLD:
                # Sort by dateAdded
                pair = sorted([item_a, item_b], key=lambda x: x['data'].get('dateAdded', ''))
                pair_key = tuple(sorted([pair[0]['key'], pair[1]['key']]))
                if pair_key not in seen_keys:
                    seen_keys.add(pair_key)
                    tier3.append((pair[0], pair[1], sim))
                    if verbose:
                        print(f"    T3 Fuzzy ({sim:.0%}): {pair[0]['data'].get('title', '')[:50]}...")

    return {'tier1': tier1, 'tier2': tier2, 'tier3': tier3}


def merge_and_trash(zot: zotero.Zotero, keeper: dict, duplicate: dict,
                    dry_run: bool = True, verbose: bool = False) -> bool:
    """
    Merge metadata from duplicate into keeper, then trash the duplicate.

    Merges: tags, collections. Does NOT move child items (attachments stay
    with their parent; trashed parent keeps children accessible in trash).

    Returns True if successful.
    """
    keeper_data = keeper['data']
    dup_data = duplicate['data']

    keeper_key = keeper['key']
    dup_key = duplicate['key']

    # Merge tags
    keeper_tags = {t['tag'] for t in keeper_data.get('tags', [])}
    dup_tags = {t['tag'] for t in dup_data.get('tags', [])}
    new_tags = dup_tags - keeper_tags

    # Merge collections
    keeper_colls = set(keeper_data.get('collections', []))
    dup_colls = set(dup_data.get('collections', []))
    new_colls = dup_colls - keeper_colls

    if verbose:
        if new_tags:
            print(f"      Merge tags: {new_tags}")
        if new_colls:
            print(f"      Merge collections: {new_colls}")

    if dry_run:
        return True

    updated = False

    # Update keeper with merged tags/collections
    if new_tags or new_colls:
        all_tags = [{'tag': t} for t in keeper_tags | new_tags]
        all_colls = list(keeper_colls | new_colls)

        keeper_data['tags'] = all_tags
        keeper_data['collections'] = all_colls

        try:
            zot.update_item(keeper)
            updated = True
            time.sleep(RATE_LIMIT_DELAY)
        except HTTPError as e:
            print(f"      ERROR updating keeper {keeper_key}: {e}")
            return False

    # Trash the duplicate (delete_item sends to Zotero trash, not permanent)
    try:
        zot.delete_item(duplicate)
        time.sleep(RATE_LIMIT_DELAY)
    except HTTPError as e:
        print(f"      ERROR trashing duplicate {dup_key}: {e}")
        return False

    return True


def print_report(results: dict, verbose: bool = False) -> None:
    """Print a summary report of duplicate findings."""
    tier1 = results['tier1']
    tier2 = results['tier2']
    tier3 = results['tier3']

    total_auto = len(tier1) + len(tier2)
    total_review = len(tier3)

    print("\n" + "=" * 70)
    print("DUPLICATE DETECTION REPORT")
    print("=" * 70)

    print(f"\n  Tier 1 (DOI match — auto-merge):        {len(tier1)}")
    print(f"  Tier 2 (title+author+year — auto-merge): {len(tier2)}")
    print(f"  Tier 3 (fuzzy — manual review):          {len(tier3)}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Total auto-mergeable:                    {total_auto}")
    print(f"  Total needs review:                      {total_review}")

    if verbose and tier1:
        print(f"\n--- Tier 1 Details (DOI matches) ---")
        for keeper, dup in tier1[:10]:
            doi = get_doi(keeper['data'])
            print(f"  Keep {keeper['key']} | Trash {dup['key']} | DOI: {doi[:60]}")
        if len(tier1) > 10:
            print(f"  ... and {len(tier1) - 10} more")

    if verbose and tier2:
        print(f"\n--- Tier 2 Details (exact normalized match) ---")
        for keeper, dup in tier2[:10]:
            title = keeper['data'].get('title', '')[:60]
            print(f"  Keep {keeper['key']} | Trash {dup['key']} | {title}...")
        if len(tier2) > 10:
            print(f"  ... and {len(tier2) - 10} more")

    if tier3:
        print(f"\n--- Tier 3 (NEEDS MANUAL REVIEW) ---")
        for keeper, dup, sim in tier3:
            t1 = keeper['data'].get('title', '')[:50]
            t2 = dup['data'].get('title', '')[:50]
            print(f"  {sim:.0%} similarity:")
            print(f"    A [{keeper['key']}]: {t1}...")
            print(f"    B [{dup['key']}]: {t2}...")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate Zotero items.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python zotero_dedup.py --backup                # Full library backup
    python zotero_dedup.py --dry-run --verbose     # Preview changes
    python zotero_dedup.py --execute               # Merge + trash duplicates
        """,
    )
    parser.add_argument('--backup', action='store_true',
                        help='Export full library to JSON backup')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would happen (default, safe)')
    parser.add_argument('--execute', action='store_true',
                        help='Actually perform the merge and trash')
    parser.add_argument('--include-tier3', action='store_true',
                        help='Include Tier 3 fuzzy matches in auto-merge')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show per-item decisions')

    args = parser.parse_args()

    if not args.backup and not args.dry_run and not args.execute:
        args.dry_run = True
        print("No mode specified — defaulting to --dry-run\n")

    # Connect to Zotero
    library_id, library_type, api_key = load_credentials()
    print(f"Connecting to Zotero ({library_type} library: {library_id})...")

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print("  Connected.\n")
    except HTTPError as e:
        print(f"ERROR: Failed to connect: {e}")
        sys.exit(1)

    # Backup mode
    if args.backup:
        backup_library(zot)
        if not args.dry_run and not args.execute:
            return

    # Safety check for execute
    if args.execute:
        today = datetime.now().strftime('%Y%m%d')
        backup_file = BACKUP_DIR / f'pre-dedup-{today}.json'
        if not backup_file.exists():
            print("ERROR: No backup found for today.")
            print(f"  Expected: {backup_file}")
            print("  Run --backup first before --execute.")
            sys.exit(1)

    # Fetch all items
    print("Fetching all items...")
    items = zot.everything(zot.items())
    content_items = [
        i for i in items
        if i['data'].get('itemType') not in SKIP_ITEM_TYPES
    ]
    print(f"  Total items: {len(items)}")
    print(f"  Content items: {len(content_items)}")

    # Find duplicates
    print("\nDetecting duplicates...")
    results = find_duplicates(items, verbose=args.verbose)
    print_report(results, verbose=args.verbose)

    tier1 = results['tier1']
    tier2 = results['tier2']
    tier3 = results['tier3']
    auto_pairs = tier1 + tier2
    if args.include_tier3:
        auto_pairs += [(k, d) for k, d, _ in tier3]

    if not auto_pairs:
        print("No duplicates found to merge.")
        return

    if args.dry_run:
        print(f"[DRY RUN] Would merge+trash {len(auto_pairs)} duplicate(s)")
        if not args.include_tier3 and tier3:
            print(f"  (Tier 3 items skipped — use --include-tier3 to include)")
        print("\nTo execute: python zotero_dedup.py --execute")
        return

    if args.execute:
        print(f"Executing merge+trash for {len(auto_pairs)} duplicate(s)...")
        success = 0
        failed = 0

        for i, (keeper, dup) in enumerate(auto_pairs, 1):
            title = keeper['data'].get('title', '')[:50]
            print(f"  [{i}/{len(auto_pairs)}] {title}...")

            ok = merge_and_trash(zot, keeper, dup, dry_run=False, verbose=args.verbose)
            if ok:
                success += 1
            else:
                failed += 1

        print(f"\n{'=' * 70}")
        print(f"DEDUP COMPLETE")
        print(f"{'=' * 70}")
        print(f"  Merged + trashed: {success}")
        print(f"  Failed:           {failed}")
        if results['tier3']:
            print(f"  Skipped (review): {len(results['tier3'])}")

        # Post-dedup count
        print("\nVerifying post-dedup count...")
        time.sleep(2)  # Allow Zotero to process
        post_items = zot.everything(zot.items())
        post_content = [
            i for i in post_items
            if i['data'].get('itemType') not in SKIP_ITEM_TYPES
        ]
        print(f"  Content items remaining: {len(post_content)}")
        print(f"  Expected reduction: ~{success}")
        print(f"\nItems are in Zotero trash (30-day recovery window).")
        print("Check Zotero UI and verify before emptying trash.")


if __name__ == '__main__':
    main()
