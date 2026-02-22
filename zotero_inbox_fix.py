#!/usr/bin/env python3
"""
zotero_inbox_fix.py — One-time APA 7 metadata corrections for 00-Inbox items.

Fixes titles (sentence case), author formatting, missing fields, and
publisher normalization for 13 items imported 2026-02-12.

Usage:
    python zotero_inbox_fix.py --dry-run     # Preview all changes
    python zotero_inbox_fix.py               # Apply changes
"""

import argparse
import sys
import time

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

RATE_LIMIT_DELAY = 0.5

# Each entry: item_key -> dict of field corrections.
# Only fields listed here are modified; all others are left untouched.
FIXES = {
    # ── IAEA (2025) — Book ──────────────────────────────────────────
    "MWIT3LDB": {
        "title": (
            "Considerations for deploying artificial intelligence "
            "applications in the nuclear power industry"
        ),
        "publisher": "International Atomic Energy Agency",
        "series": "IAEA Nuclear Energy Series",
        # Creator fix handled separately (corporate author, all-caps → proper case)
        "_creators": [
            {"creatorType": "author", "name": "International Atomic Energy Agency"}
        ],
    },
    # ── Reeves et al. (2024) — Report / Poster ──────────────────────
    "7GVIY7K9": {
        "title": (
            "Improving reliability of large language models for "
            "nuclear power plant diagnostics [Poster]"
        ),
        "institution": "Idaho National Laboratory",
    },
    # ── Fayyaz et al. (2025) — Journal Article ──────────────────────
    "2IF594TV": {
        "title": (
            "Natural language processing in the nuclear industry: "
            "Opportunities and challenges"
        ),
    },
    # ── Kim et al. (2024) — Journal Article ─────────────────────────
    # Title is already correct (Korean Triage and Acuity Scale = proper noun).
    # Only fixing journal name casing.
    "ZTBEZM32": {
        "publicationTitle": "Digital Health",
    },
    # ── Soroush et al. (2024) — Journal Article ─────────────────────
    "IYLFK76G": {
        "title": (
            "Large language models are poor medical coders — "
            "Benchmarking of medical code querying"
        ),
    },
    # ── Nielsen et al. (2024) — Conference Paper ─────────────────────
    "839R2S28": {
        "title": (
            "Towards an aviation large language model by "
            "fine-tuning and evaluating transformers"
        ),
        "conferenceName": (
            "2024 AIAA DATC/IEEE 43rd Digital Avionics "
            "Systems Conference (DASC)"
        ),
        "proceedingsTitle": (
            "2024 AIAA DATC/IEEE 43rd Digital Avionics "
            "Systems Conference (DASC)"
        ),
    },
    # ── Dokas (2026) — Journal Article ───────────────────────────────
    "GW2KPELK": {
        "title": (
            "From hallucinations to hazards: Benchmarking LLMs for "
            "hazard analysis in safety-critical systems"
        ),
    },
    # ── Carletta (1996) — Journal Article ────────────────────────────
    # Remove erroneous co-author (Hirschberg). Sole author confirmed via ACL Anthology.
    "JDU7ZXLU": {
        "title": "Assessing agreement on classification tasks: The kappa statistic",
        "_creators": [
            {"creatorType": "author", "firstName": "Jean", "lastName": "Carletta"}
        ],
    },
    # ── Park & Jung (2003) — Conference Paper ────────────────────────
    # Fix author name format + add conference metadata.
    "HZX5FG84": {
        "_creators": [
            {"creatorType": "author", "firstName": "Hyung-Min", "lastName": "Park"},
            {"creatorType": "author", "firstName": "Ho-Won", "lastName": "Jung"},
        ],
        "conferenceName": (
            "Third International Conference on Quality Software, "
            "2003. Proceedings"
        ),
        "proceedingsTitle": (
            "Third International Conference on Quality Software, "
            "2003. Proceedings"
        ),
    },
    # ── Krippendorff (2019) — Book ──────────────────────────────────
    "WHQ9BNGB": {
        "title": "Content analysis: An introduction to its methodology",
        "publisher": "SAGE Publications",
        "edition": "4",
        "ISBN": "978-1-5063-9566-1",
    },
    # ── Zhao et al. (2013) — Journal Article ─────────────────────────
    "XY66W24Z": {
        "title": "Assumptions behind intercoder reliability indices",
    },
    # ── Scott (1955) — Journal Article ───────────────────────────────
    # Date "23/1955" is malformed; pages incomplete.
    "Z73U75BG": {
        "title": "Reliability of content analysis: The case of nominal scale coding",
        "date": "1955",
        "pages": "321\u2013325",
    },
    # ── Yang (2026) — Preprint ───────────────────────────────────────
    # No changes needed. Already APA 7 compliant.
}


def apply_fixes(zot, dry_run=True):
    """Fetch each item, apply fixes, and update via API."""
    success = 0
    errors = 0
    skipped = 0
    total = len(FIXES)

    for i, (item_key, corrections) in enumerate(FIXES.items(), 1):
        try:
            item = zot.item(item_key)
        except HTTPError as e:
            print(f"  [{i}/{total}] ERROR fetching {item_key}: {e}")
            errors += 1
            continue

        data = item["data"]
        current_title = data.get("title", "")
        changes = []

        # Apply field-level corrections
        for field, new_value in corrections.items():
            if field == "_creators":
                continue  # handled below
            old_value = data.get(field, "")
            if old_value != new_value:
                changes.append((field, old_value, new_value))
                if not dry_run:
                    data[field] = new_value

        # Apply creator corrections
        if "_creators" in corrections:
            new_creators = corrections["_creators"]
            old_creators = data.get("creators", [])
            old_summary = "; ".join(
                c.get("name", f"{c.get('lastName', '?')}, {c.get('firstName', '?')}")
                for c in old_creators
            )
            new_summary = "; ".join(
                c.get("name", f"{c.get('lastName', '?')}, {c.get('firstName', '?')}")
                for c in new_creators
            )
            if old_summary != new_summary:
                changes.append(("creators", old_summary, new_summary))
                if not dry_run:
                    data["creators"] = new_creators

        # Report
        prefix = "[DRY RUN] " if dry_run else ""
        if changes:
            print(f"\n{prefix}[{i}/{total}] {item_key} — {current_title[:60]}...")
            for field, old, new in changes:
                old_display = old if old else "(empty)"
                print(f"  {field}:")
                print(f"    FROM: {old_display}")
                print(f"    TO:   {new}")
        else:
            skipped += 1
            continue

        # Apply update
        if not dry_run:
            try:
                zot.update_item(item)
                print(f"  ✅ Updated")
                success += 1
                if i < total:
                    time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"  ❌ ERROR: {e}")
                errors += 1
        else:
            success += 1  # count as "would succeed" for dry run

    print(f"\n{'='*70}")
    print(f"Items processed: {total}")
    print(f"Items with changes: {success}")
    print(f"Items unchanged: {skipped}")
    print(f"Errors: {errors}")
    print(f"{'='*70}")

    if dry_run and success > 0:
        print("\n[DRY RUN] No changes applied. Remove --dry-run to apply.")


def main():
    parser = argparse.ArgumentParser(
        description="Apply APA 7 metadata fixes to 00-Inbox items."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )
    args = parser.parse_args()

    library_id, library_type, api_key = load_credentials()

    print("Inbox Metadata Fix — APA 7 Compliance")
    print("=" * 70)
    print(f"Library: {library_id} ({library_type})")
    print(f"Dry Run: {args.dry_run}")
    print(f"Items to process: {len(FIXES)}")
    print("=" * 70)

    zot = zotero.Zotero(library_id, library_type, api_key)

    apply_fixes(zot, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
