#!/usr/bin/env python3
"""
zotero_apa7_cleanup.py

Transforms Zotero item titles to APA7 sentence case while preserving
acronyms, proper nouns, and fixing known typos.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_apa7_cleanup.py --dry-run     # Preview changes
    python zotero_apa7_cleanup.py               # Apply changes
"""

import argparse
import re
import sys
import time
from typing import Set

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

# =============================================================================
# PROTECTED TERMS - Do not lowercase these
# =============================================================================
PROTECTED_TERMS: Set[str] = {
    # Aviation acronyms
    'FAA', 'NAS', 'ASRS', 'UAS', 'sUAS', 'UAV', 'RPAS', 'UTM', 'LAANC',
    'AGL', 'MSL', 'ATC', 'ARTCC', 'TRACON', 'ATCT', 'NMAC', 'CFR', 'VMC',
    'IMC', 'VFR', 'IFR', 'NM', 'ICAO', 'EASA', 'NTSB', 'HFACS', 'UASFMs',
    'SORA', 'ATM', 'BVLOS', 'C-UAS', 'cUAS', 'DAA', 'TCAS', 'ADS-B',
    '7110.65W',  # FAA JO version designator

    # Technical/ML acronyms
    'LLM', 'LLMs', 'NLP', 'NER', 'GPT', 'BERT', 'AI', 'ML', 'API', 'JSON',
    'ROC', 'AUC', 'MAE', 'TTR', 'MATTR', 'MTLD', 'PELT', 'STL', 'ARDL',
    'VAR', 'IRF', 'ROUGE', 'KIE', 'APE', 'EDA', 'QLoRA', 'LoRA', 'CoNLL',
    'HD-D', 'vocd-D', 'lda2vec', 'LDA', 'NMF', 'KPI', 'KPIs', 'VGI', 'R',

    # Model names / statistical abbreviations with digits
    'T5', 'GPT-3', 'GPT-4', 'BERT', 'RoBERTa', 'GPT-NER', '3D',
    'AC1', 'AC2', 'F1',

    # Proper nouns - systems/methods
    'SafeAeroBERT', 'AviationGPT', 'ChatGPT', 'Claude', 'Zotero',
    'NASP-T', 'LogSyn', 'LeRAAT', 'LERCause',
    'Loess', 'Monte-Carlo', 'Monte', 'Carlo', 'Jeffreys', 'Poisson',
    'Cohen', 'Gwet', 'Granger', 'Bayesian', 'Boolean', 'Gaussian', 'Markov',
    'Firth', 'Lasso', 'Gordian', 'Johnny', 'Cox',
    # Eponymous statistical tests/measures (possessives handled by is_protected)
    'Mann', 'Kendall', 'Kruskal', 'Wallis', 'Shapiro', 'Wilk',
    'Fleiss', 'Krippendorff', 'Cronbach', 'Bonferroni', 'Tukey',
    'Fisher', 'Friedman', 'Pearson', 'Spearman', 'Wilcoxon', 'Likert', 'Sen',
    'Kaplan', 'Meier', 'Welch', 'Levene', 'Kolmogorov', 'Smirnov',

    # Proper nouns - organizations
    'NASA', 'MITRE', 'IEEE', 'ACM', 'AIAA', 'SAE', 'Routledge', 'Elsevier',
    'Springer', 'Purdue', 'USGS', 'DHS', 'NDAA', 'DoD', 'ProQuest', 'AeroScope',
    'Black', 'Vault', 'Bombardier', 'Canadair', 'Inc',

    # Software/product names (that patterns won't catch)
    'Stata', 'Power', 'Excel', 'SPSS', 'Tableau', 'tscount',

    # Proper nouns - geographic/demonyms
    'United', 'States', 'U.S.', 'US', 'UK', 'France', 'French', 'Greek',
    'Korean', 'Japanese', 'German',
    'Taiwanese', 'National', 'Federal', 'American', 'European', 'Copenhagen',
    'Oslo', 'Florida', 'Russia', 'Russian', 'X',
    'South', 'North', 'East', 'West', 'Auckland', 'Zealand', 'Australia',
    'Australian', 'Canadian', 'China', 'Chinese', 'India', 'Indian',
    'Los', 'Angeles', 'CA', 'Frankfurt',

    # Month names (proper nouns)
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',

    # Regulatory terms
    'Part', 'Remote', 'ID', 'ASSURE',
}

# Terms that are protected as multi-word phrases
PROTECTED_PHRASES = [
    'Part 107',
    'Remote ID',
    'United States',
    'Monte-Carlo',
    'Monte Carlo',
    'National Airspace System',
    'Human Factors Analysis and Classification System',
    'Federal Aviation Administration',
    'The Black Vault',
    'Aviation Safety Reporting System',
    'CoNLL-2003',
    'X Files',
    'Los Angeles',
    'Bombardier Inc',
]

TYPO_CORRECTIONS = {
    'Flordia': 'Florida',
    'unmaned': 'unmanned',
    'aircaft': 'aircraft',
    r'\(SORA\)approach': '(SORA) approach',
    r'\(sora\)approach': '(SORA) approach',
}

# Rate limiting
RATE_LIMIT_DELAY = 0.5


def remove_bibtex_braces(text: str) -> str:
    """Remove BetterBibTeX brace protection {{ }} from text."""
    text = re.sub(r'\{\{', '', text)
    text = re.sub(r'\}\}', '', text)
    text = re.sub(r'\{', '', text)
    text = re.sub(r'\}', '', text)
    return text


def fix_typos(text: str) -> str:
    """Fix known typos in text."""
    for wrong, correct in TYPO_CORRECTIONS.items():
        # Check if the pattern is a regex (starts with special chars)
        if wrong.startswith(r'\('):
            text = re.sub(wrong, correct, text, flags=re.IGNORECASE)
        else:
            text = re.sub(rf'\b{wrong}\b', correct, text, flags=re.IGNORECASE)
    return text


def matches_protected_pattern(word: str) -> bool:
    """
    Check if word matches patterns that should be preserved.

    Patterns detected:
    - All-caps acronyms (2+ letters): UAV, UAVs, GA, LLM, BI
    - Roman numerals: I, II, III, IV, V, VI, VII, VIII, IX, X
    - CamelCase product names: YouTube, PowerBI, iPhone
    """
    if not word:
        return False

    # All-caps acronyms (2+ letters, optionally ending in lowercase 's' for plurals)
    # e.g., UAV, UAVs, GA, LLM, NLP, BI
    if re.match(r'^[A-Z]{2,}s?$', word):
        return True

    # Roman numerals (standalone, up to 4 characters to avoid false positives)
    # e.g., I, II, III, IV, V, VI, VII, VIII, IX, X, XI, XII
    if re.match(r'^[IVXLCDM]+$', word) and len(word) <= 4:
        return True

    # CamelCase / mixed case product names
    # e.g., YouTube, PowerBI, iPhone, macOS
    if re.match(r'^[a-z]+[A-Z]', word):  # starts lowercase, has uppercase (iPhone, macOS)
        return True
    if re.match(r'^[A-Z][a-z]+[A-Z]', word):  # YouTuBe, PowerBI pattern
        return True

    return False


def is_protected(word: str) -> bool:
    """Check if a word should be protected from lowercasing."""
    # Strip punctuation (including parentheses) for comparison
    clean_word = re.sub(r'[^\w\-/.]', '', word)
    # Also try without periods for U.S. vs US matching
    clean_word_no_dots = clean_word.replace('.', '')
    # Strip possessive suffix: "Cohens" -> "Cohen", "Gwets" -> "Gwet"
    clean_word_base = re.sub(r's$', '', clean_word) if clean_word.endswith('s') else clean_word

    # Check pattern-based rules first (acronyms, Roman numerals, CamelCase)
    if matches_protected_pattern(clean_word):
        return True

    # Check exact match in PROTECTED_TERMS (word, without dots, or base form)
    for candidate in (clean_word, clean_word_no_dots, clean_word_base):
        if candidate in PROTECTED_TERMS:
            return True

    # Check case-insensitive match for terms in PROTECTED_TERMS
    for candidate in (clean_word, clean_word_no_dots, clean_word_base):
        if candidate.upper() in PROTECTED_TERMS:
            return True

    return False


def process_compound_word(word: str) -> str:
    """Process hyphenated or slashed compound words, preserving protected parts."""
    # Handle words with hyphens or slashes
    if '-' in word or '/' in word:
        # Split by hyphen or slash, preserving the delimiter
        parts = re.split(r'([-/])', word)
        result_parts = []
        for part in parts:
            if part in ['-', '/']:
                result_parts.append(part)
            elif matches_protected_pattern(part):
                # Pattern match (acronym, Roman numeral, CamelCase) - preserve original
                result_parts.append(part)
            elif part.upper() in PROTECTED_TERMS or part in PROTECTED_TERMS:
                # Find the correct casing from PROTECTED_TERMS
                for term in PROTECTED_TERMS:
                    if part.lower() == term.lower():
                        result_parts.append(term)
                        break
                else:
                    result_parts.append(part)
            else:
                result_parts.append(part.lower())
        return ''.join(result_parts)
    return word


def get_protected_form(word: str) -> str:
    """Get the correct protected form of a word."""
    clean_word = re.sub(r'[^\w\-.]', '', word)
    clean_word_no_dots = clean_word.replace('.', '')

    # Find leading and trailing punctuation
    punct_before = ''
    punct_after = ''
    i = 0
    while i < len(word) and not word[i].isalnum():
        punct_before += word[i]
        i += 1
    j = len(word) - 1
    while j >= 0 and not word[j].isalnum():
        punct_after = word[j] + punct_after
        j -= 1

    # If matches a pattern (acronym, Roman numeral, CamelCase), preserve original case
    if matches_protected_pattern(clean_word):
        return word  # Keep original exactly

    # Find matching protected term in PROTECTED_TERMS
    for term in PROTECTED_TERMS:
        if clean_word.lower() == term.lower():
            # Exact match including dots - use term's casing from PROTECTED_TERMS
            return punct_before + term + punct_after
        if clean_word_no_dots.lower() == term.lower():
            # Match without dots - preserve original word's dot pattern with term's casing
            # e.g., "U.S." matches "US" -> return "U.S." with correct casing
            result = ''
            term_idx = 0
            for char in clean_word:
                if char == '.':
                    result += '.'
                elif term_idx < len(term):
                    result += term[term_idx]
                    term_idx += 1
            return punct_before + result + punct_after

    return word


def to_sentence_case(title: str) -> str:
    """
    Convert title to APA7 sentence case.
    - First word capitalized
    - First word after colon/em-dash capitalized
    - Protected terms preserved
    - Everything else lowercase
    """
    if not title:
        return title

    # Step 1: Remove BibTeX braces
    title = remove_bibtex_braces(title)

    # Step 2: Fix typos
    title = fix_typos(title)

    # Step 3: Protect multi-word phrases by replacing spaces with placeholders
    phrase_map = {}
    for i, phrase in enumerate(PROTECTED_PHRASES):
        placeholder = f"__PHRASE_{i}__"
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(title):
            phrase_map[placeholder] = phrase
            title = pattern.sub(placeholder, title)

    # Step 4: Split into words
    words = title.split()
    result = []

    # Track if next word should be capitalized (start of sentence or after colon)
    capitalize_next = True

    for i, word in enumerate(words):
        # Check if this word ends with colon, em-dash, or question mark (capitalize next word)
        ends_with_colon = word.endswith(':') or word.endswith('—') or word.endswith('–') or word.endswith('?')

        # Get the word without trailing punctuation for checking
        word_base = word.rstrip(':—–,;.!?')
        trailing_punct = word[len(word_base):] if len(word_base) < len(word) else ''

        if capitalize_next:
            if is_protected(word_base):
                # Protected term - use correct form
                result.append(get_protected_form(word_base) + trailing_punct)
            elif '-' in word_base or '/' in word_base:
                # Compound word - process parts, capitalize first letter
                processed = process_compound_word(word_base)
                if len(processed) > 0:
                    processed = processed[0].upper() + processed[1:]
                result.append(processed + trailing_punct)
            else:
                # Capitalize first letter only
                if len(word_base) > 1:
                    result.append(word_base[0].upper() + word_base[1:].lower() + trailing_punct)
                else:
                    result.append(word_base.upper() + trailing_punct)
            capitalize_next = False
        elif is_protected(word_base):
            # Protected term - use correct form
            result.append(get_protected_form(word_base) + trailing_punct)
        elif '-' in word_base or '/' in word_base:
            # Compound word - process parts
            result.append(process_compound_word(word_base) + trailing_punct)
        else:
            # Regular word - lowercase
            result.append(word.lower())

        # Set flag for next word if this one ends with colon
        if ends_with_colon:
            capitalize_next = True

    title = ' '.join(result)

    # Step 5: Restore protected phrases
    for placeholder, phrase in phrase_map.items():
        title = title.replace(placeholder.lower(), phrase)
        title = title.replace(placeholder, phrase)

    return title


def get_collection_key(zot, collection_name: str) -> str:
    """Find collection key by name."""
    collections = zot.collections()
    for coll in collections:
        if coll['data'].get('name', '').lower() == collection_name.lower():
            return coll['key']

    # List available collections
    print(f"\nCollection '{collection_name}' not found. Available collections:")
    for coll in collections:
        print(f"  - {coll['data'].get('name')}")
    raise ValueError(f"Collection '{collection_name}' not found")


def process_collection(zot, collection_key: str, dry_run: bool = True):
    """Process all items in a collection."""
    print(f"\nFetching items from collection...")
    items = zot.everything(zot.collection_items(collection_key))
    print(f"Found {len(items)} items")

    changes = []
    skipped = 0

    for item in items:
        if item['data'].get('itemType') in ['attachment', 'note', 'annotation']:
            skipped += 1
            continue

        item_key = item['key']
        original_title = item['data'].get('title', '')

        if not original_title:
            continue

        new_title = to_sentence_case(original_title)

        if original_title != new_title:
            changes.append({
                'key': item_key,
                'original': original_title,
                'new': new_title,
                'item': item
            })
            mode_str = "[DRY RUN] " if dry_run else ""
            print(f"\n{mode_str}[CHANGE] {item_key}")
            print(f"  FROM: {original_title}")
            print(f"  TO:   {new_title}")

    print(f"\n{'='*70}")
    print(f"Total items reviewed: {len(items)}")
    print(f"Attachments/notes skipped: {skipped}")
    print(f"Items to change: {len(changes)}")
    print(f"Items unchanged: {len(items) - skipped - len(changes)}")
    print(f"{'='*70}")

    if not dry_run and changes:
        print("\nApplying changes...")
        success = 0
        errors = 0

        for i, change in enumerate(changes, 1):
            item = change['item']
            item['data']['title'] = change['new']

            # Also update shortTitle if it exists
            if item['data'].get('shortTitle'):
                item['data']['shortTitle'] = to_sentence_case(item['data']['shortTitle'])

            try:
                zot.update_item(item)
                print(f"  [{i}/{len(changes)}] Updated: {change['key']}")
                success += 1

                if i < len(changes):
                    time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"  [{i}/{len(changes)}] ERROR: {change['key']} - {e}")
                errors += 1

        print(f"\nDone! {success} items updated, {errors} errors.")
    elif dry_run and changes:
        print("\n[DRY RUN] No changes applied. Remove --dry-run to apply.")

    return changes


def process_library(zot, dry_run: bool = True):
    """Process all items in the library."""
    print(f"\nFetching all items from library...")
    items = zot.everything(zot.items())
    print(f"Found {len(items)} items")

    changes = []
    skipped = 0

    for item in items:
        if item['data'].get('itemType') in ['attachment', 'note', 'annotation']:
            skipped += 1
            continue

        item_key = item['key']
        original_title = item['data'].get('title', '')

        if not original_title:
            continue

        new_title = to_sentence_case(original_title)

        if original_title != new_title:
            changes.append({
                'key': item_key,
                'original': original_title,
                'new': new_title,
                'item': item
            })
            mode_str = "[DRY RUN] " if dry_run else ""
            print(f"\n{mode_str}[CHANGE] {item_key}")
            print(f"  FROM: {original_title}")
            print(f"  TO:   {new_title}")

    print(f"\n{'='*70}")
    print(f"Total items reviewed: {len(items)}")
    print(f"Attachments/notes skipped: {skipped}")
    print(f"Items to change: {len(changes)}")
    print(f"Items unchanged: {len(items) - skipped - len(changes)}")
    print(f"{'='*70}")

    if not dry_run and changes:
        print("\nApplying changes...")
        success = 0
        errors = 0

        for i, change in enumerate(changes, 1):
            item = change['item']
            item['data']['title'] = change['new']

            # Also update shortTitle if it exists
            if item['data'].get('shortTitle'):
                item['data']['shortTitle'] = to_sentence_case(item['data']['shortTitle'])

            try:
                zot.update_item(item)
                print(f"  [{i}/{len(changes)}] Updated: {change['key']}")
                success += 1

                if i < len(changes):
                    time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"  [{i}/{len(changes)}] ERROR: {change['key']} - {e}")
                errors += 1

        print(f"\nDone! {success} items updated, {errors} errors.")
    elif dry_run and changes:
        print("\n[DRY RUN] No changes applied. Remove --dry-run to apply.")

    return changes


def main():
    parser = argparse.ArgumentParser(
        description="Transform Zotero titles to APA7 sentence case.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run              Preview changes
  %(prog)s                        Apply changes
  %(prog)s --collection "My Refs" Use different collection
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying'
    )
    parser.add_argument(
        '--collection', '-c',
        default=None,
        help='Collection name (default: process entire library)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Process all items in the library (default behavior)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Load credentials
    library_id, library_type, api_key = load_credentials()

    print("Zotero APA7 Title Cleanup Script")
    print("=" * 70)
    print(f"Library ID: {library_id}")
    print(f"Library Type: {library_type}")
    print(f"Scope: {args.collection if args.collection else 'Entire library'}")
    print(f"Dry Run: {args.dry_run}")
    print("=" * 70)

    # Connect to Zotero
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print("Connected to Zotero API")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Process items - either from collection or entire library
    if args.collection:
        try:
            collection_key = get_collection_key(zot, args.collection)
            print(f"Found collection key: {collection_key}")
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        process_collection(zot, collection_key, dry_run=args.dry_run)
    else:
        process_library(zot, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
