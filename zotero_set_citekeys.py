"""
Set custom citation keys via Zotero's native citationKey field.

Zotero 8 introduced a native citationKey field on items. BBT reads this
field for exports. The old approach of writing 'Citation Key: <key>'
to the Extra field is no longer effective — BBT ignores it.

This script sets the native citationKey field and cleans up any
leftover 'Citation Key:' lines from the Extra field.

Usage:
    python zotero_set_citekeys.py --dry-run    # Preview changes
    python zotero_set_citekeys.py              # Apply changes
"""

import argparse
import sys

from pyzotero import zotero
from zotero_utils import load_credentials

CITEKEY_MAP = {
    "F7I5EVPU": "oigFAABarriers2014",
    "E4ZU4ZWE": "gaoSmallUAS2018",
    "XV47WV6C": "gaoUASCompliance2019",
    "74SN89ZG": "oigCounterUAS2022",
    "RIHUJ8FW": "eliasCRS2016",
    "KPC43VR4": "whitlockWaPo2014",
    "F53WDTZK": "amaAnalysis2015",
    "ZKBZEJ7S": "amaAnalysis2016a",
    "56KF3TCQ": "amaAnalysis2016b",
    "I4SM8TVZ": "uastSightings2018",
    "GZ2IKU58": "faaUASLostLink2016",
    "TBSBBMR5": "faaAirTrafficControl2016",
    "USXDG9JH": "howardFAASighting2023",
    "UQKHKANJ": "DroneSightingsAirports",
    "7VLH3GJK": "whitlockFAARecordsDetail2015",
    "4JHDZBQ5": "gettingerDroneSightings2015",
}


def strip_extra_citekey(extra: str) -> str:
    """Remove any 'Citation Key:' lines from Extra field (legacy cleanup)."""
    if not extra:
        return ""
    lines = extra.splitlines()
    filtered = [ln for ln in lines if not ln.strip().lower().startswith("citation key:")]
    return "\n".join(filtered).strip()


def main():
    parser = argparse.ArgumentParser(description="Set custom citation keys (Zotero 8 native field)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)

    updated = 0
    skipped = 0
    errors = 0

    for zotero_key, new_citekey in CITEKEY_MAP.items():
        try:
            item = zot.item(zotero_key)
        except Exception as e:
            print(f"  ERROR: Could not fetch {zotero_key}: {e}")
            errors += 1
            continue

        title = item["data"].get("title", "(no title)")[:60]
        current_native = item["data"].get("citationKey", "")
        extra = item["data"].get("extra", "") or ""

        if current_native == new_citekey:
            print(f"  SKIP: {zotero_key} already has native key '{new_citekey}'")
            skipped += 1
            # Still clean up Extra if needed
            cleaned_extra = strip_extra_citekey(extra)
            if cleaned_extra != extra:
                if not args.dry_run:
                    item["data"]["extra"] = cleaned_extra
                    zot.update_item(item)
                    print(f"    CLEANED Extra field (removed legacy Citation Key line)")
            continue

        if args.dry_run:
            old_display = f"'{current_native}'" if current_native else "(empty)"
            print(f"  SET: {zotero_key}  {old_display} → '{new_citekey}'  [{title}]")
            has_extra_key = "citation key:" in extra.lower()
            if has_extra_key:
                print(f"    CLEAN: Will remove 'Citation Key:' from Extra field")
            updated += 1
        else:
            item["data"]["citationKey"] = new_citekey
            cleaned_extra = strip_extra_citekey(extra)
            if cleaned_extra != extra:
                item["data"]["extra"] = cleaned_extra
            try:
                zot.update_item(item)
                print(f"  SET: {zotero_key} → '{new_citekey}'  [{title}]")
                if cleaned_extra != extra:
                    print(f"    CLEANED Extra field")
                updated += 1
            except Exception as e:
                print(f"  ERROR updating {zotero_key}: {e}")
                errors += 1

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"\n{mode}: {updated} updated, {skipped} skipped, {errors} errors")

    if not args.dry_run and updated > 0:
        print("\nNext steps:")
        print("  1. Open Zotero and wait for sync")
        print("  2. BBT will re-export references.bib on idle")
        print("  3. Verify: grep for new keys in references.bib")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
