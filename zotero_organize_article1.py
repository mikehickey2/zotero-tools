#!/usr/bin/env python3
"""
zotero_organize_article1.py

Hybrid Zotero tagging script:
- Reads citation keys from Better BibTeX JSON export
- Pushes tags via Zotero API using item keys

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_organize_article1.py --dry-run  # Preview changes
    python zotero_organize_article1.py            # Apply changes
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError, UnsupportedParamsError

# Tag mapping: regex patterns matched against citationKey (case-insensitive)
TAG_MAPPING = {
    # =========================================================================
    # DISSERTATION-RELEVANT: Article 1 Categories
    # =========================================================================

    # 01a - Prior FAA UAS Analysis (foundational UAS sighting studies)
    r'^wang.*(characteristics|investigating|threats).*': '#A1-01a-Prior',
    r'^wang.*comparison.*airport': '#A1-01a-Prior',
    r'^howard.*faa.*unmanned': '#A1-01a-Prior',
    r'^das.*exploratory': '#A1-01a-Prior',
    r'^pitcher': '#A1-01a-Prior',
    r'^gettinger.*drone.*sightings': '#A1-01a-Prior',
    r'^akers.*drone.*sight': '#A1-01a-Prior',
    r'^sharma.*investigation.*unmanned': '#A1-01a-Prior',
    r'^greenewald.*federal.*aviation': '#A1-01a-Prior',
    r'^pascarella.*historical': '#A1-01a-Prior',
    r'^sun.*examination.*uas': '#A1-01a-Prior',
    r'^kashyap.*analyzing.*trends.*uas': '#A1-01a-Prior',

    # 01b - Aviation Safety Text Analysis
    r'^kuhn.*structural.*topic': '#A1-01b-TextAnalysis',
    r'^rose.*structural.*topic': '#A1-01b-TextAnalysis',
    r'^dou.*navigating.*massive': '#A1-01b-TextAnalysis',
    r'^darveau.*automated.*classification': '#A1-01b-TextAnalysis',
    r'^luo.*lda2vec': '#A1-01b-TextAnalysis',
    r'^paradis.*augmenting.*topic': '#A1-01b-TextAnalysis',
    r'^nanyonga.*topic.*modeling': '#A1-01b-TextAnalysis',

    # 02a - LLM Aviation Applications
    r'^tikayatray.*generative': '#A1-02a-LLM-Aviation',
    r'^basil.*large.*language': '#A1-02a-LLM-Aviation',
    r'^andrade.*safeaerobert': '#A1-02a-LLM-Aviation',
    r'^chen.*information.*extraction.*aviation': '#A1-02a-LLM-Aviation',
    r'^siddeshwar.*aviation.*safety': '#A1-02a-LLM-Aviation',
    r'^ziakkas.*artificial.*intelligence': '#A1-02a-LLM-Aviation',
    r'^liu.*large.*language.*models': '#A1-02a-LLM-Aviation',
    r'^martin-domingo.*extracting.*airline': '#A1-02a-LLM-Aviation',

    # 02b - LLM/NLP Methods (general, not aviation-specific)
    r'^agrawal.*large.*language': '#A1-02b-LLM-Methods',
    r'^xu.*large.*language': '#A1-02b-LLM-Methods',
    r'^wang.*gptner': '#A1-02b-LLM-Methods',
    r'^tjongkimsang.*conll': '#A1-02b-LLM-Methods',

    # 02c - Prompt Engineering
    r'^brown.*language.*models.*are': '#A1-02c-Prompt',
    r'^wei.*chain.*thought': '#A1-02c-Prompt',
    r'^liu.*pretrain.*prompt': '#A1-02c-Prompt',
    r'^min.*rethinking.*demonstrations': '#A1-02c-Prompt',
    r'^chen.*evaluation.*prompt': '#A1-02c-Prompt',
    r'^reynolds.*prompt.*programming': '#A1-02c-Prompt',
    r'^zamfirescu.*johnny': '#A1-02c-Prompt',

    # 03 - Fine-Tuning
    r'^howard.*universal.*language': '#A1-03-FineTune',
    r'^hu.*lora': '#A1-03-FineTune',
    r'^dettmers.*qlora': '#A1-03-FineTune',
    r'^majdik.*sample.*size': '#A1-03-FineTune',

    # 04a - Inter-Rater Reliability
    r'^gwet.*handbook': '#A1-04a-IRR',
    r'^sim.*kappa': '#A1-04a-IRR',
    r'^landis.*koch': '#A1-04a-IRR',
    r'^donner.*eliasziw': '#A1-04a-IRR',

    # 04b - Sample Size / Power Analysis
    r'^leon.*sample.*sizes': '#A1-04b-SampleSize',
    r'^gelman.*(16|sixteen)': '#A1-04b-SampleSize',

    # 04c - Statistical Foundations
    r'^firth.*bias.*reduction': '#A1-04c-Stats',
    r'^heinze.*solution.*problem.*separation': '#A1-04c-Stats',
    r'^king.*logistic.*regression.*rare': '#A1-04c-Stats',
    r'^peduzzi.*simulation': '#A1-04c-Stats',
    r'^puhr.*firth': '#A1-04c-Stats',
    r'^vittinghoff.*relaxing': '#A1-04c-Stats',
    r'^tibshirani.*regression': '#A1-04c-Stats',
    r'^snijders.*multilevel': '#A1-04c-Stats',

    # 05a - Time Series / Forecasting
    r'^cleveland.*stl.*seasonal': '#A1-05a-TimeSeries',
    r'^hyndman.*forecasting': '#A1-05a-TimeSeries',
    r'^wang.*characteristic.*based.*clustering.*time': '#A1-05a-TimeSeries',

    # 05b - Changepoint Detection
    r'^killick.*(optimal|changepoint)': '#A1-05b-Changepoint',

    # 05c - Lexical Diversity
    r'^mccarthy.*mtld': '#A1-05c-LexDiv',
    r'^covington.*gordian': '#A1-05c-LexDiv',

    # 06 - Human Factors
    r'^wiegmann.*human.*error': '#A1-06-HumanFactors',

    # 07 - Safety Context (UAS detection, pilot studies, NMAC)
    r'^wallace': '#A1-07-Safety',
    r'^loffi.*seeing.*threat': '#A1-07-Safety',
    r'^vance.*detecting.*assessing': '#A1-07-Safety',
    r'^baum.*improving.*cockpit': '#A1-07-Safety',
    r'^may.*review.*collisions.*drones': '#A1-07-Safety',
    r'^gao.*dynamics.*voluntary': '#A1-07-Safety',
    r'^kioulepoglou.*investigating.*incident': '#A1-07-Safety',

    # 08 - UAS Risk Assessment / Regulation
    r'^breunig.*modeling.*risk': '#A1-08-RiskReg',
    r'^nikodem.*(new.*specific|sora)': '#A1-08-RiskReg',
    r'^denney.*rigorous.*basis': '#A1-08-RiskReg',
    r'^schnuriger.*sora.*tool': '#A1-08-RiskReg',
    r'^hunter.*family.*based.*safety': '#A1-08-RiskReg',
    r'^mandourah.*violation.*drone': '#A1-08-RiskReg',
    r'^truong.*(enhance.*safety|machine.*learning)': '#A1-08-RiskReg',
    r'^cleland.*huang.*real.*time': '#A1-08-RiskReg',
    r'^puranik.*online.*prediction': '#A1-08-RiskReg',
    r'^rao.*state.*based': '#A1-08-RiskReg',
    r'^asghari.*uav.*operations.*safety': '#A1-08-RiskReg',
    r'^gohar.*engineering.*fair': '#A1-08-RiskReg',
    r'^wang.*(threedimensional|3d|monte.*carlo)': '#A1-08-RiskReg',

    # =========================================================================
    # NON-DISSERTATION: Filter/Move Categories
    # =========================================================================

    # Counter-UAS Technology & Systems
    r'^abdulhadi.*counter.*uas': '#NonDiss-cUAS-Tech',
    r'^gabor.*no.*drone': '#NonDiss-cUAS-Tech',
    r'^lykou.*defending.*airports': '#NonDiss-cUAS-Tech',
    r'^park.*survey.*anti.*drone': '#NonDiss-cUAS-Tech',
    r'^stary.*evaluation.*counter': '#NonDiss-cUAS-Tech',
    r'^grieco.*detection.*tracking': '#NonDiss-cUAS-Tech',
    r'^kim.*study.*development': '#NonDiss-cUAS-Tech',
    r'^pettyjohn.*countering.*swarm': '#NonDiss-cUAS-Tech',
    r'^yang.*intellectual.*structure': '#NonDiss-cUAS-Tech',

    # Dark Drones / Non-Cooperative UAS
    r'^asis.*dark.*drones': '#NonDiss-DarkDrone',
    r'^caci.*spark.*dark': '#NonDiss-DarkDrone',
    r'^defencexp.*dark.*drones': '#NonDiss-DarkDrone',
    r'^echodyne.*dark.*drone': '#NonDiss-DarkDrone',
    r'^dhs.*dark.*drone': '#NonDiss-DarkDrone',
    r'^nasa.*coop.*noncoop': '#NonDiss-DarkDrone',
    r'^epstein.*russia.*unjammable': '#NonDiss-DarkDrone',

    # DHS/Government cUAS Programs
    r'^dhs.*cuas': '#NonDiss-DHS-cUAS',
    r'^dhs.*air.*domain': '#NonDiss-DHS-cUAS',
    r'^idga.*dhs.*cuas': '#NonDiss-DHS-cUAS',
    r'^dronelife.*ndaa.*cuas': '#NonDiss-DHS-cUAS',
    r'^department.*defense.*counter': '#NonDiss-DHS-cUAS',
    r'^research.*development.*acquisition': '#NonDiss-DHS-cUAS',
    r'^usarmy.*sbir': '#NonDiss-DHS-cUAS',
    r'^how.*us.*confronting': '#NonDiss-DHS-cUAS',

    # Detection/Radar Systems (vendor/product focused)
    r'^quickset.*drone.*detection': '#NonDiss-Detection',
    r'^robinradar.*counter.*drone': '#NonDiss-Detection',
    r'^spotterglobal.*radar': '#NonDiss-Detection',

    # Regulatory Documents (FAA/CFR - reference only)
    r'^14cfrpart': '#NonDiss-Regulatory',
    r'^assure.*faa.*center': '#NonDiss-Regulatory',
    r'^drone.*sightings.*airports': '#NonDiss-Regulatory',
    r'^remote.*identification.*drones': '#NonDiss-Regulatory',

    # News/Current Events
    r'^jacobsen.*drone.*sightings.*disrupt': '#NonDiss-News',
    r'^posard.*not.*files': '#NonDiss-News',
    r'^challenges.*investigating.*mid.*air': '#NonDiss-News',

    # Urban Air Mobility / Future Concepts (not Article 1 scope)
    r'^straubinger.*overview': '#NonDiss-UAM',
    r'^oshea.*closing.*gaps': '#NonDiss-UAM',
}

# Default tag for items not matching any pattern
DEFAULT_TAG = '#Review-Uncategorized'

# Rate limiting delay between write operations (seconds)
RATE_LIMIT_DELAY = 1.0


@dataclass
class ProcessingStats:
    """Track processing statistics."""
    items_in_json: int = 0
    items_with_citekey: int = 0
    items_matched: int = 0
    items_unmatched: int = 0
    tags_added: int = 0
    items_updated: int = 0
    errors: list = field(default_factory=list)
    skipped_already_tagged: int = 0
    tag_counts: dict = field(default_factory=dict)

    def add_error(self, item_title: str, error_msg: str):
        self.errors.append(f"{item_title[:50]}: {error_msg}")

    def increment_tag(self, tag: str):
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1


def load_credentials() -> tuple[str, str, str]:
    """
    Load Zotero credentials from environment variables or .env file.

    Returns:
        Tuple of (library_id, library_type, api_key)

    Raises:
        SystemExit: If required credentials are missing
    """
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
        print("\nPlease set these in your environment or create a .env file.")
        print("See .env.example for the expected format.")
        sys.exit(1)

    return library_id, library_type, api_key


def load_bbt_json(json_path: str) -> list[dict]:
    """
    Load items from Better BibTeX JSON export.

    Args:
        json_path: Path to the BBT JSON file

    Returns:
        List of item dictionaries with citationKey and itemKey

    Raises:
        SystemExit: If file not found or invalid JSON
    """
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: JSON file not found: {json_path}")
        sys.exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {json_path}: {e}")
        sys.exit(1)

    # BBT JSON has items in the "items" array
    items = data.get('items', [])
    if not items:
        print(f"ERROR: No items found in {json_path}")
        sys.exit(1)

    print(f"Loaded {len(items)} items from {path.name}")
    return items


def get_matching_tag(citekey: str) -> Optional[str]:
    """
    Find the first matching tag for a given citation key.

    Args:
        citekey: The citation key (matched case-insensitively)

    Returns:
        The matching tag string, or None if no match found
    """
    citekey_lower = citekey.lower()

    for pattern, tag in TAG_MAPPING.items():
        try:
            if re.search(pattern, citekey_lower):
                return tag
        except re.error as e:
            print(f"WARNING: Invalid regex pattern '{pattern}': {e}")

    return None


def process_items(
    zot: zotero.Zotero,
    bbt_items: list[dict],
    dry_run: bool = False
) -> ProcessingStats:
    """
    Process BBT items and apply tags via Zotero API.

    Args:
        zot: Initialized Zotero client
        bbt_items: List of items from BBT JSON
        dry_run: If True, show what would change without modifying

    Returns:
        ProcessingStats with summary information
    """
    stats = ProcessingStats()
    items_to_update = []

    mode_str = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode_str}Processing items...")
    print("-" * 70)

    for bbt_item in bbt_items:
        stats.items_in_json += 1

        # Skip items without citation keys
        citekey = bbt_item.get('citationKey', '')
        if not citekey:
            continue

        stats.items_with_citekey += 1
        item_key = bbt_item.get('itemKey') or bbt_item.get('key')
        title = bbt_item.get('title', '(no title)')

        if not item_key:
            stats.add_error(title, "Missing itemKey")
            continue

        # Find matching tag (use DEFAULT_TAG if no match)
        matching_tag = get_matching_tag(citekey)

        if matching_tag:
            stats.items_matched += 1
        else:
            stats.items_unmatched += 1
            matching_tag = DEFAULT_TAG

        # Track tag counts
        stats.increment_tag(matching_tag)

        # Check if tag already exists
        existing_tags = [t.get('tag', '') for t in bbt_item.get('tags', [])]

        if matching_tag in existing_tags:
            stats.skipped_already_tagged += 1
            continue

        # Queue for update
        items_to_update.append({
            'item_key': item_key,
            'citekey': citekey,
            'title': title,
            'new_tag': matching_tag,
            'existing_tags': bbt_item.get('tags', [])
        })
        stats.tags_added += 1

        title_display = title[:45] + "..." if len(title) > 45 else title
        print(f"{mode_str}+ {matching_tag:<25} {citekey[:22]:<22} {title_display}")

    # Perform updates via API
    if not dry_run and items_to_update:
        print(f"\n{mode_str}Updating {len(items_to_update)} items via Zotero API...")
        stats.items_updated = update_items_via_api(zot, items_to_update, stats)
    elif dry_run and items_to_update:
        stats.items_updated = len(items_to_update)
        print(f"\n{mode_str}Would update {len(items_to_update)} items.")

    return stats


def update_items_via_api(
    zot: zotero.Zotero,
    items_to_update: list[dict],
    stats: ProcessingStats
) -> int:
    """
    Update items via Zotero API with rate limiting.

    Args:
        zot: Initialized Zotero client
        items_to_update: List of items to update
        stats: ProcessingStats to record errors

    Returns:
        Number of successfully updated items
    """
    successful_updates = 0

    for i, item_info in enumerate(items_to_update, 1):
        item_key = item_info['item_key']
        title = item_info['title']
        new_tag = item_info['new_tag']

        try:
            # Fetch current item from API to get latest version
            api_item = zot.item(item_key)

            # Add new tag to existing tags
            current_tags = api_item['data'].get('tags', [])
            current_tags.append({'tag': new_tag})
            api_item['data']['tags'] = current_tags

            # Update via API
            zot.update_item(api_item)
            successful_updates += 1

            print(f"  [{i}/{len(items_to_update)}] Updated: {title[:50]}...")

            # Rate limiting
            if i < len(items_to_update):
                time.sleep(RATE_LIMIT_DELAY)

        except HTTPError as e:
            stats.add_error(title, str(e))
            print(f"  [{i}/{len(items_to_update)}] ERROR: {title[:40]}... - {e}")

    return successful_updates


def show_citation_keys(bbt_items: list[dict], count: int = 30):
    """
    Display sample citation keys sorted alphabetically.

    Args:
        bbt_items: List of items from BBT JSON
        count: Number of citation keys to display
    """
    keys_with_titles = []
    for item in bbt_items:
        citekey = item.get('citationKey', '')
        if citekey:
            title = item.get('title', '(no title)')
            keys_with_titles.append((citekey, title))

    if not keys_with_titles:
        print("\nNo items with citation keys found.")
        return

    keys_with_titles.sort(key=lambda x: x[0].lower())

    print("\n" + "=" * 85)
    print(f"CITATION KEYS ({min(count, len(keys_with_titles))} of {len(keys_with_titles)} total)")
    print("=" * 85)
    print(f"{'Citation Key':<40} Title")
    print("-" * 85)

    for citekey, title in keys_with_titles[:count]:
        title_display = title[:42] + "..." if len(title) > 42 else title
        citekey_display = citekey[:38] + ".." if len(citekey) > 40 else citekey
        print(f"{citekey_display:<40} {title_display}")

    print("=" * 85)
    print(f"\nShowing {min(count, len(keys_with_titles))} of {len(keys_with_titles)} citation keys.")


def print_summary(stats: ProcessingStats, dry_run: bool = False):
    """Print a summary report of the processing results."""
    mode_str = "[DRY RUN] " if dry_run else ""

    print("\n" + "=" * 60)
    print(f"{mode_str}SUMMARY REPORT")
    print("=" * 60)
    print(f"Items in JSON file:          {stats.items_in_json}")
    print(f"Items with citation keys:    {stats.items_with_citekey}")
    print(f"Items matching patterns:     {stats.items_matched}")
    print(f"Already had correct tag:     {stats.skipped_already_tagged}")
    print(f"Tags to add:                 {stats.tags_added}")

    if dry_run:
        print(f"Items that would be updated: {stats.items_updated}")
    else:
        print(f"Items successfully updated:  {stats.items_updated}")

    if stats.errors:
        print(f"\nErrors encountered: {len(stats.errors)}")
        for error in stats.errors:
            print(f"  - {error}")
    else:
        print(f"\nErrors encountered:          0")

    print("=" * 60)


def print_tag_summary(stats: ProcessingStats):
    """Print a breakdown of tags by count."""
    if not stats.tag_counts:
        print("\nNo tags to summarize.")
        return

    print("\n" + "=" * 60)
    print("TAG COUNTS BY CATEGORY")
    print("=" * 60)

    # Sort tags: dissertation tags first (A1-*), then NonDiss, then default
    def tag_sort_key(item):
        tag = item[0]
        if tag.startswith('#A1-'):
            return (0, tag)
        elif tag.startswith('#NonDiss-'):
            return (1, tag)
        elif tag == DEFAULT_TAG:
            return (3, tag)
        else:
            return (2, tag)

    sorted_tags = sorted(stats.tag_counts.items(), key=tag_sort_key)

    # Group by category prefix
    current_prefix = None
    for tag, count in sorted_tags:
        # Detect category change for visual grouping
        if tag.startswith('#A1-'):
            prefix = 'Dissertation-Relevant'
        elif tag.startswith('#NonDiss-'):
            prefix = 'Non-Dissertation'
        else:
            prefix = 'Other'

        if prefix != current_prefix:
            if current_prefix is not None:
                print()  # Blank line between groups
            print(f"\n  {prefix}:")
            current_prefix = prefix

        print(f"    {tag:<30} {count:>3}")

    print("\n" + "-" * 60)
    total = sum(stats.tag_counts.values())
    print(f"  {'TOTAL':<30} {total:>3}")
    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Hybrid Zotero tagging: reads BBT JSON, pushes tags via API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run              Preview changes without modifying
  %(prog)s --dry-run --summary    Preview with tag count breakdown
  %(prog)s --show-keys            Display citation keys from JSON
  %(prog)s                        Apply tags to matching items

Environment variables (or .env file):
  ZOTERO_LIBRARY_ID     Your Zotero library ID (group or user)
  ZOTERO_LIBRARY_TYPE   'group' (default) or 'user'
  ZOTERO_API_KEY        Your Zotero API key
  BBT_JSON_PATH         Path to Better BibTeX JSON export
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making modifications'
    )
    parser.add_argument(
        '--show-keys',
        action='store_true',
        help='Display citation keys from BBT JSON for debugging'
    )
    parser.add_argument(
        '--show-keys-count',
        type=int,
        default=30,
        metavar='N',
        help='Number of citation keys to display (default: 30)'
    )
    parser.add_argument(
        '--json',
        dest='json_path',
        help='Path to BBT JSON file (overrides BBT_JSON_PATH env var)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print tag counts after processing'
    )

    args = parser.parse_args()

    # Load credentials
    library_id, library_type, api_key = load_credentials()

    # Get JSON path from args or environment
    json_path = args.json_path or os.getenv('BBT_JSON_PATH')
    if not json_path:
        # Default path
        json_path = os.path.expanduser('~/Desktop/cUAS_AD.json')

    if args.verbose:
        print(f"Library ID: {library_id}")
        print(f"Library type: {library_type}")
        print(f"API key: {'*' * 8}...{api_key[-4:]}")
        print(f"JSON path: {json_path}")

    # Load items from BBT JSON
    bbt_items = load_bbt_json(json_path)

    # Show citation keys mode
    if args.show_keys:
        show_citation_keys(bbt_items, count=args.show_keys_count)
        sys.exit(0)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("=" * 60)

    # Initialize Zotero client
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print(f"Connected to Zotero API ({library_type} library: {library_id})")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        print("Please check your credentials.")
        sys.exit(1)

    # Process items
    stats = process_items(zot, bbt_items, dry_run=args.dry_run)

    # Print summary
    print_summary(stats, dry_run=args.dry_run)

    # Print tag counts if requested
    if args.summary:
        print_tag_summary(stats)

    # Exit with error code if there were errors
    if stats.errors:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
