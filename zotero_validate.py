#!/usr/bin/env python3
"""
zotero_validate.py

Validates Zotero library for proper formatting:
- No BetterBibTeX brace artifacts
- No known typos
- Proper sentence case
- Preserved acronyms and proper nouns

Usage:
    python zotero_validate.py
"""

import os
import random
import re
import sys

from dotenv import load_dotenv
from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

# Validation checks
BRACE_PATTERN = re.compile(r'\{\{|\}\}')
TYPOS = ['Flordia', 'Inititative']
ACRONYMS = ['UAS', 'FAA', 'LLM', 'ASRS', 'NLP', 'BERT', 'GPT', 'ICAO', 'NTSB']
PROPER_NOUNS = ['SafeAeroBERT', 'Monte-Carlo', 'Firth', 'Bayesian', 'Gaussian', 'Markov', 'Cohen']


def load_credentials():
    load_dotenv()
    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')
    api_key = os.getenv('ZOTERO_API_KEY')
    if not library_id or not api_key:
        print("ERROR: Missing ZOTERO_LIBRARY_ID or ZOTERO_API_KEY")
        sys.exit(1)
    return library_id, library_type, api_key


def check_braces(items):
    """Check for {{ }} brace artifacts."""
    issues = []
    for item in items:
        title = item['data'].get('title', '')
        if BRACE_PATTERN.search(title):
            issues.append({'key': item['key'], 'title': title})
    return issues


def check_typos(items):
    """Check for known typos."""
    issues = []
    for item in items:
        for field in ['title', 'shortTitle', 'institution', 'publicationTitle']:
            text = item['data'].get(field, '')
            for typo in TYPOS:
                if typo in text:
                    issues.append({'key': item['key'], 'field': field, 'typo': typo, 'text': text})
    return issues


def check_acronyms(items):
    """Verify acronyms are properly capitalized."""
    preserved = []
    issues = []

    for item in items:
        title = item['data'].get('title', '')
        for acronym in ACRONYMS:
            # Check if acronym appears in any case
            pattern = re.compile(rf'\b{acronym}\b', re.IGNORECASE)
            match = pattern.search(title)
            if match:
                found = match.group()
                if found == acronym:
                    preserved.append({'key': item['key'], 'acronym': acronym, 'title': title[:60]})
                else:
                    issues.append({'key': item['key'], 'expected': acronym, 'found': found, 'title': title[:60]})

    return preserved, issues


def check_proper_nouns(items):
    """Verify proper nouns are preserved."""
    preserved = []
    issues = []

    for item in items:
        title = item['data'].get('title', '')
        for noun in PROPER_NOUNS:
            pattern = re.compile(rf'\b{noun}\b', re.IGNORECASE)
            match = pattern.search(title)
            if match:
                found = match.group()
                if found == noun:
                    preserved.append({'key': item['key'], 'noun': noun, 'title': title[:60]})
                else:
                    issues.append({'key': item['key'], 'expected': noun, 'found': found, 'title': title[:60]})

    return preserved, issues


def spot_check_sentence_case(items, count=10):
    """Randomly sample entries and display for manual review."""
    # Filter to only items with titles
    titled_items = [i for i in items if i['data'].get('title') and i['data'].get('itemType') not in ['attachment', 'note']]

    if len(titled_items) < count:
        sample = titled_items
    else:
        sample = random.sample(titled_items, count)

    return sample


def main():
    library_id, library_type, api_key = load_credentials()

    print("=" * 70)
    print("ZOTERO LIBRARY VALIDATION")
    print("=" * 70)

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print(f"Connected to Zotero API (library: {library_id})")
    except HTTPError as e:
        print(f"ERROR: Failed to connect: {e}")
        sys.exit(1)

    print("\nFetching all items...")
    items = zot.everything(zot.items())
    content_items = [i for i in items if i['data'].get('itemType') not in ['attachment', 'note']]
    print(f"Found {len(content_items)} content items (excluding attachments/notes)")

    all_passed = True

    # 1. Check for braces
    print("\n" + "-" * 70)
    print("CHECK 1: BetterBibTeX Brace Artifacts ({{ }})")
    print("-" * 70)
    brace_issues = check_braces(content_items)
    if brace_issues:
        all_passed = False
        print(f"FAIL: Found {len(brace_issues)} items with braces:")
        for issue in brace_issues:
            print(f"  - {issue['key']}: {issue['title'][:50]}...")
    else:
        print("PASS: No brace artifacts found")

    # 2. Check for typos
    print("\n" + "-" * 70)
    print("CHECK 2: Known Typos (Flordia, Inititative)")
    print("-" * 70)
    typo_issues = check_typos(content_items)
    if typo_issues:
        all_passed = False
        print(f"FAIL: Found {len(typo_issues)} typo occurrences:")
        for issue in typo_issues:
            print(f"  - {issue['key']} [{issue['field']}]: '{issue['typo']}' in {issue['text'][:40]}...")
    else:
        print("PASS: No known typos found")

    # 3. Check acronyms
    print("\n" + "-" * 70)
    print("CHECK 3: Acronym Preservation (UAS, FAA, LLM, ASRS, etc.)")
    print("-" * 70)
    acronym_preserved, acronym_issues = check_acronyms(content_items)
    if acronym_issues:
        all_passed = False
        print(f"FAIL: Found {len(acronym_issues)} incorrectly cased acronyms:")
        for issue in acronym_issues:
            print(f"  - {issue['key']}: expected '{issue['expected']}', found '{issue['found']}'")
    else:
        print(f"PASS: All acronyms properly capitalized")
    print(f"  Found {len(acronym_preserved)} correctly preserved acronym instances")

    # Show some examples
    if acronym_preserved:
        print("  Examples:")
        for ex in acronym_preserved[:5]:
            print(f"    - {ex['acronym']}: {ex['title']}...")

    # 4. Check proper nouns
    print("\n" + "-" * 70)
    print("CHECK 4: Proper Noun Preservation (SafeAeroBERT, Monte-Carlo, etc.)")
    print("-" * 70)
    noun_preserved, noun_issues = check_proper_nouns(content_items)
    if noun_issues:
        all_passed = False
        print(f"FAIL: Found {len(noun_issues)} incorrectly cased proper nouns:")
        for issue in noun_issues:
            print(f"  - {issue['key']}: expected '{issue['expected']}', found '{issue['found']}'")
    else:
        print(f"PASS: All proper nouns preserved")
    if noun_preserved:
        print(f"  Found {len(noun_preserved)} correctly preserved proper noun instances:")
        for ex in noun_preserved:
            print(f"    - {ex['noun']}: {ex['title']}...")

    # 5. Spot check sentence case
    print("\n" + "-" * 70)
    print("CHECK 5: Sentence Case Spot Check (10 Random Entries)")
    print("-" * 70)
    print("Manual review - verify first word and post-colon words are capitalized,")
    print("other words lowercase except acronyms/proper nouns:\n")

    samples = spot_check_sentence_case(content_items, 10)
    for i, item in enumerate(samples, 1):
        title = item['data'].get('title', '')
        print(f"  {i:2}. [{item['key']}]")
        print(f"      {title}")
        print()

    # Summary
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    checks = [
        ("Brace artifacts", len(brace_issues) == 0),
        ("Known typos", len(typo_issues) == 0),
        ("Acronym capitalization", len(acronym_issues) == 0),
        ("Proper noun preservation", len(noun_issues) == 0),
    ]

    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    print(f"\nSentence case: Manual review required (10 samples shown above)")

    if all_passed:
        print("\n✓ All automated checks passed!")
    else:
        print("\n✗ Some checks failed - review issues above")
        sys.exit(1)


if __name__ == '__main__':
    main()
