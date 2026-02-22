"""
Set custom BBT citation keys via Zotero's Extra field.

Better BibTeX respects 'Citation Key: <key>' lines in the Extra field.
This script prepends custom citation keys to items identified by Zotero key.

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
}


def get_existing_citekey(extra: str) -> str | None:
    """Extract existing Citation Key from Extra field, if present."""
    for line in extra.splitlines():
        if line.strip().lower().startswith("citation key:"):
            return line.split(":", 1)[1].strip()
    return None


def set_citekey_in_extra(extra: str, new_key: str) -> str:
    """Set Citation Key in Extra field, replacing any existing one."""
    lines = extra.splitlines() if extra else []
    filtered = [ln for ln in lines if not ln.strip().lower().startswith("citation key:")]
    filtered.insert(0, f"Citation Key: {new_key}")
    return "\n".join(filtered)


def main():
    parser = argparse.ArgumentParser(description="Set custom BBT citation keys")
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
        extra = item["data"].get("extra", "") or ""
        existing = get_existing_citekey(extra)

        if existing == new_citekey:
            print(f"  SKIP: {zotero_key} already has key '{new_citekey}'")
            skipped += 1
            continue

        new_extra = set_citekey_in_extra(extra, new_citekey)

        if args.dry_run:
            status = f"REPLACE '{existing}'" if existing else "ADD"
            print(f"  {status}: {zotero_key} → {new_citekey}  [{title}]")
            updated += 1
        else:
            item["data"]["extra"] = new_extra
            try:
                zot.update_item(item)
                print(f"  SET: {zotero_key} → {new_citekey}  [{title}]")
                updated += 1
            except Exception as e:
                print(f"  ERROR updating {zotero_key}: {e}")
                errors += 1

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"\n{mode}: {updated} updated, {skipped} skipped, {errors} errors")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
