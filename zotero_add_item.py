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


def get_collection_key(zot: zotero.Zotero, collection_name: str) -> str | None:
    """Find collection key by name (case-insensitive)."""
    collections = zot.collections()
    for coll in collections:
        if coll['data'].get('name', '').lower() == collection_name.lower():
            return coll['key']
    return None


def carol_to_zotero(case: dict) -> dict:
    """Convert NTSB CAROL case to Zotero report template."""
    # Extract key fields
    ntsb_num = case.get('cm_ntsbNum', 'Unknown')
    event_date = case.get('cm_eventDate', '')[:10]  # YYYY-MM-DD
    city = case.get('cm_city', '')
    state = case.get('cm_state', '')

    # Build location string
    location = f"{city}, {state}" if city and state else city or state or ''

    # Extract aircraft info for title
    vehicles = case.get('cm_vehicles', [])
    aircraft_descriptions = []
    for v in vehicles:
        make = v.get('make', 'Unknown')
        model = v.get('model', 'Unknown')
        category = v.get('aircraftCategory', '')
        if category == 'UNMANNED':
            aircraft_descriptions.append('unmanned aircraft')
        else:
            aircraft_descriptions.append(f"{make} {model}".strip())

    # Build title
    if len(aircraft_descriptions) >= 2:
        title = f"NTSB investigation of collision: {aircraft_descriptions[0]} and {aircraft_descriptions[1]}, {location}, {event_date}"
    else:
        title = f"NTSB investigation: {ntsb_num}, {location}, {event_date}"

    # Build abstract from narrative fields
    abstract_parts = []
    if case.get('cm_probableCause'):
        abstract_parts.append(f"Probable Cause: {case['cm_probableCause']}")
    if case.get('analysisNarrative'):
        abstract_parts.append(f"Analysis: {case['analysisNarrative']}")
    if case.get('factualNarrative'):
        abstract_parts.append(f"Facts: {case['factualNarrative']}")
    abstract = '\n\n'.join(abstract_parts) if abstract_parts else ''

    # Build Zotero item dict
    return {
        'itemType': 'report',
        'title': title,
        'creators': [{'creatorType': 'author', 'name': 'National Transportation Safety Board'}],
        'date': event_date,
        'reportNumber': ntsb_num,
        'institution': 'National Transportation Safety Board',
        'place': 'Washington, DC',
        'url': f"https://data.ntsb.gov/carol-main-public/basic-search?q={ntsb_num}",
        'abstractNote': abstract,
        'extra': f"Event Type: {case.get('cm_eventType', '')}\nHighest Injury: {case.get('cm_highestInjury', '')}",
    }


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

    # Convert cases to Zotero items
    zotero_items = []
    for case in cases:
        item = carol_to_zotero(case)
        zotero_items.append(item)

        if args.verbose or args.dry_run:
            print(f"\n{'='*60}")
            print(f"Title: {item['title']}")
            print(f"Report #: {item['reportNumber']}")
            print(f"Date: {item['date']}")
            print(f"Institution: {item['institution']}")
            print(f"URL: {item['url']}")
            if item['abstractNote']:
                print(f"Abstract: {item['abstractNote'][:200]}...")

    if args.dry_run:
        print(f"\n[DRY RUN] Would create {len(zotero_items)} item(s)")
        return

    # Connect to Zotero API
    library_id, library_type, api_key = load_credentials()

    if args.verbose:
        print(f"\nConnecting to Zotero ({library_type} library: {library_id})...")

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Resolve collection if specified
    collection_key = None
    if args.collection:
        collection_key = get_collection_key(zot, args.collection)
        if not collection_key:
            print(f"ERROR: Collection '{args.collection}' not found")
            # List available collections
            print("\nAvailable collections:")
            for c in zot.collections():
                print(f"  - {c['data']['name']}")
            sys.exit(1)
        if args.verbose:
            print(f"Target collection: {args.collection} (key: {collection_key})")

    # Create items via API
    print(f"\nCreating {len(zotero_items)} item(s)...")

    for item in zotero_items:
        try:
            # Get fresh template and merge our data
            template = zot.item_template('report')
            for key, value in item.items():
                if key in template:
                    template[key] = value

            # Create item
            resp = zot.create_items([template])

            if resp.get('success'):
                item_key = list(resp['success'].values())[0]
                print(f"  Created: {item['reportNumber']} -> {item_key}")

                # Add to collection if specified
                if collection_key:
                    created_item = zot.item(item_key)
                    zot.addto_collection(collection_key, created_item)
                    print(f"    Added to collection: {args.collection}")
            else:
                print(f"  FAILED: {item['reportNumber']}")
                if resp.get('failed'):
                    print(f"    Error: {resp['failed']}")

        except HTTPError as e:
            print(f"  ERROR creating {item['reportNumber']}: {e}")

    print("\nDone!")


if __name__ == '__main__':
    main()
