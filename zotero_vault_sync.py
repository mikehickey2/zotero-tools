#!/usr/bin/env python3
"""
zotero_vault_sync.py

Compare Zotero library against an Obsidian vault's literature notes.

Requirements:
    pip install pyzotero python-dotenv pyyaml

Usage:
    python zotero_vault_sync.py --vault /path/to/vault     # Check sync status
    python zotero_vault_sync.py --vault /path/to/vault --fix  # Generate stubs for missing
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class SyncStats:
    """Track sync comparison statistics."""
    zotero_items: int = 0
    vault_notes: int = 0
    matched: int = 0
    missing_from_vault: list = field(default_factory=list)
    orphaned_in_vault: list = field(default_factory=list)
    naming_issues: list = field(default_factory=list)


def get_zotero_items(zot: zotero.Zotero) -> list[dict]:
    """Get all items from Zotero library (excluding attachments/notes)."""
    items = zot.everything(zot.items())

    result = []
    for item in items:
        item_type = item['data'].get('itemType', '')
        if item_type in ['attachment', 'note']:
            continue

        data = item['data']
        creators = data.get('creators', [])

        # Get first author last name
        if creators:
            first = creators[0]
            first_author = first.get('lastName', first.get('name', 'Unknown'))
        else:
            first_author = 'Unknown'

        # Get year
        date = data.get('date', '')
        year = date[:4] if date else 'n.d.'

        # Generate expected filename
        if len(creators) > 1:
            expected_name = f"{first_author} et al._{year}.md"
        else:
            expected_name = f"{first_author}_{year}.md"

        result.append({
            'key': item['key'],
            'title': data.get('title', ''),
            'first_author': first_author,
            'year': year,
            'creators': creators,
            'expected_filename': expected_name,
            'citekey': extract_citekey(data),
            'zotero_link': f"zotero://select/library/items/{item['key']}",
            'data': data,
        })

    return result


def extract_citekey(data: dict) -> str:
    """Extract citation key from item's extra field."""
    extra = data.get('extra', '')
    if 'Citation Key:' in extra:
        return extra.split('Citation Key:')[1].split('\n')[0].strip()
    return ''


def get_vault_literature_notes(vault_path: Path) -> list[dict]:
    """Get all literature notes from vault's 01_literature/ directory."""
    lit_dir = vault_path / '01_literature'

    if not lit_dir.exists():
        print(f"WARNING: Literature directory not found: {lit_dir}")
        return []

    notes = []
    for note_path in lit_dir.glob('*.md'):
        note_info = {
            'path': note_path,
            'filename': note_path.name,
            'zotero_key': None,
            'citekey': None,
        }

        # Try to extract Zotero info from frontmatter
        try:
            content = note_path.read_text(encoding='utf-8')

            # Parse YAML frontmatter
            if content.startswith('---'):
                end = content.find('---', 3)
                if end > 0:
                    frontmatter = content[3:end].strip()
                    if HAS_YAML:
                        fm_data = yaml.safe_load(frontmatter)
                        if fm_data:
                            # Extract Zotero link
                            zotero_link = fm_data.get('zotero', '')
                            if zotero_link and 'items/' in zotero_link:
                                key = zotero_link.split('items/')[-1]
                                note_info['zotero_key'] = key

                            # Extract citekey
                            note_info['citekey'] = fm_data.get('citekey', '')
                    else:
                        # Basic parsing without yaml
                        for line in frontmatter.split('\n'):
                            if line.startswith('zotero:'):
                                link = line.split(':', 1)[1].strip().strip("'\"")
                                if 'items/' in link:
                                    note_info['zotero_key'] = link.split('items/')[-1]
                            elif line.startswith('citekey:'):
                                note_info['citekey'] = line.split(':', 1)[1].strip().strip("'\"")

        except Exception as e:
            print(f"WARNING: Could not parse {note_path.name}: {e}")

        notes.append(note_info)

    return notes


def normalize_filename(name: str) -> str:
    """Normalize filename for comparison."""
    # Remove invisible unicode characters
    name = ''.join(c for c in name if c.isprintable() or c in ' -_.')
    # Remove extension
    name = re.sub(r'\.md$', '', name, flags=re.IGNORECASE)
    # Lowercase for comparison
    return name.lower().strip()


def compare_library_and_vault(zotero_items: list, vault_notes: list) -> SyncStats:
    """Compare Zotero items against vault notes."""
    stats = SyncStats()
    stats.zotero_items = len(zotero_items)
    stats.vault_notes = len(vault_notes)

    # Build lookup maps
    vault_by_key = {}
    vault_by_citekey = {}
    vault_by_normalized_name = {}

    for note in vault_notes:
        if note['zotero_key']:
            vault_by_key[note['zotero_key']] = note
        if note['citekey']:
            vault_by_citekey[note['citekey'].lower()] = note

        normalized = normalize_filename(note['filename'])
        vault_by_normalized_name[normalized] = note

    # Track which vault notes are matched
    matched_vault_notes = set()

    # Check each Zotero item
    for item in zotero_items:
        matched = False

        # Match by Zotero key
        if item['key'] in vault_by_key:
            matched = True
            matched_vault_notes.add(vault_by_key[item['key']]['filename'])

        # Match by citekey
        elif item['citekey'] and item['citekey'].lower() in vault_by_citekey:
            matched = True
            matched_vault_notes.add(vault_by_citekey[item['citekey'].lower()]['filename'])

        # Match by expected filename
        else:
            expected_norm = normalize_filename(item['expected_filename'])
            if expected_norm in vault_by_normalized_name:
                matched = True
                matched_vault_notes.add(vault_by_normalized_name[expected_norm]['filename'])

        if matched:
            stats.matched += 1
        else:
            stats.missing_from_vault.append(item)

    # Find orphaned vault notes
    for note in vault_notes:
        if note['filename'] not in matched_vault_notes:
            stats.orphaned_in_vault.append(note)

    return stats


def generate_stub_note(item: dict, output_dir: Path) -> Path:
    """Generate a stub literature note for a Zotero item."""
    filename = item['expected_filename']
    filepath = output_dir / filename

    # Build frontmatter
    creators = item['creators']
    if creators:
        author_list = []
        for c in creators:
            if 'lastName' in c:
                name = f"{c.get('firstName', '')} {c['lastName']}".strip()
            else:
                name = c.get('name', 'Unknown')
            author_list.append(name)
    else:
        author_list = ['Unknown']

    frontmatter = {
        'title': item['title'],
        'authors': author_list,
        'year': item['year'],
        'zotero': item['zotero_link'],
    }

    if item['citekey']:
        frontmatter['citekey'] = item['citekey']

    # Build note content
    lines = ['---']
    lines.append(f"title: '{item['title']}'")
    lines.append('authors:')
    for author in author_list:
        lines.append(f"    - '{author}'")
    lines.append(f"year: '{item['year']}'")
    lines.append(f"zotero: '{item['zotero_link']}'")
    if item['citekey']:
        lines.append(f"citekey: {item['citekey']}")
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append(f"# {item['first_author']} ({item['year']})")
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('*Add notes here...*')
    lines.append('')

    filepath.write_text('\n'.join(lines), encoding='utf-8')
    return filepath


def print_report(stats: SyncStats, verbose: bool = False):
    """Print sync comparison report."""
    print("\n" + "=" * 60)
    print("ZOTERO-VAULT SYNC REPORT")
    print("=" * 60)

    print(f"\nZotero library items:  {stats.zotero_items}")
    print(f"Vault literature notes: {stats.vault_notes}")
    print(f"Matched:               {stats.matched}")
    print(f"Missing from vault:    {len(stats.missing_from_vault)}")
    print(f"Orphaned in vault:     {len(stats.orphaned_in_vault)}")

    if stats.missing_from_vault:
        print("\n" + "-" * 60)
        print("MISSING FROM VAULT (in Zotero but no note):")
        print("-" * 60)
        for item in stats.missing_from_vault[:20]:  # Show first 20
            print(f"  [{item['year']}] {item['first_author']}: {item['title'][:50]}...")
            print(f"        -> Suggested: {item['expected_filename']}")
        if len(stats.missing_from_vault) > 20:
            print(f"  ... and {len(stats.missing_from_vault) - 20} more")

    if stats.orphaned_in_vault and verbose:
        print("\n" + "-" * 60)
        print("ORPHANED IN VAULT (note exists but not in Zotero):")
        print("-" * 60)
        for note in stats.orphaned_in_vault:
            print(f"  {note['filename']}")
            if note['zotero_key']:
                print(f"        -> Has Zotero key: {note['zotero_key']} (may be deleted?)")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Compare Zotero library against vault literature notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --vault /path/to/vault              Check sync status
  %(prog)s --vault /path/to/vault --fix        Generate stubs for missing
  %(prog)s --vault /path/to/vault --verbose    Show orphaned notes too
        """
    )

    parser.add_argument('--vault', '-d', required=True,
                        help='Path to Obsidian vault root')
    parser.add_argument('--fix', action='store_true',
                        help='Generate stub notes for items missing from vault')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output including orphaned notes')
    parser.add_argument('--limit', '-l', type=int, default=0,
                        help='Limit number of stubs to generate (0 = all)')

    args = parser.parse_args()

    vault_path = Path(args.vault).expanduser().resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    lit_dir = vault_path / '01_literature'
    if not lit_dir.exists():
        print(f"ERROR: Literature directory not found: {lit_dir}")
        sys.exit(1)

    # Load credentials and connect
    library_id, library_type, api_key = load_credentials()

    print(f"Connecting to Zotero ({library_type} library: {library_id})...")
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Get items from both sources
    print("Fetching Zotero library items...")
    zotero_items = get_zotero_items(zot)

    print(f"Scanning vault literature notes in: {lit_dir}")
    vault_notes = get_vault_literature_notes(vault_path)

    # Compare
    print("Comparing...")
    stats = compare_library_and_vault(zotero_items, vault_notes)

    # Print report
    print_report(stats, verbose=args.verbose)

    # Generate stubs if requested
    if args.fix and stats.missing_from_vault:
        print("\nGenerating stub notes...")
        items_to_fix = stats.missing_from_vault
        if args.limit > 0:
            items_to_fix = items_to_fix[:args.limit]

        created = 0
        for item in items_to_fix:
            try:
                filepath = generate_stub_note(item, lit_dir)
                print(f"  Created: {filepath.name}")
                created += 1
            except Exception as e:
                print(f"  ERROR creating {item['expected_filename']}: {e}")

        print(f"\nCreated {created} stub notes in {lit_dir}")

    # Exit with status based on sync state
    if stats.missing_from_vault:
        sys.exit(1)  # Items need attention
    sys.exit(0)


if __name__ == '__main__':
    main()
