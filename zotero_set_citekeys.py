"""
Set and audit citation keys via Zotero's native citationKey field.

Zotero 8 introduced a native citationKey field on items. BBT reads this
field for exports. The old approach of writing 'Citation Key: <key>'
to the Extra field is no longer effective — BBT ignores it.

Features:
  - Set custom keys from a static map (legacy)
  - Audit library for oversized keys (--audit)
  - Auto-abbreviate corporate author keys (--fix)
  - Set a single key (--set ITEM_KEY newKey)
  - Validate proposed keys (--check-key "proposedKey")

Citation Key Usability Criteria:
  - <= 40 chars: OK (library median is ~35)
  - 41-50 chars: WARNING (review recommended)
  - > 50 chars: REWRITE recommended
  - Must start with a letter
  - Must end with 4-digit year
  - Alphanumeric + underscore/hyphen only

Usage:
    python zotero_set_citekeys.py --dry-run              # Apply static map (preview)
    python zotero_set_citekeys.py                        # Apply static map
    python zotero_set_citekeys.py --audit                # Scan and report long keys
    python zotero_set_citekeys.py --audit --threshold 45 # Custom threshold
    python zotero_set_citekeys.py --fix --dry-run        # Preview abbreviation rewrites
    python zotero_set_citekeys.py --fix                  # Apply abbreviation rewrites
    python zotero_set_citekeys.py --set KEY newCitekey   # Set specific key
    python zotero_set_citekeys.py --check-key "key"      # Validate a proposed key
"""

import argparse
import re
import sys
import time

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

# --- Citation Key Usability Thresholds ---
OK_THRESHOLD = 40
WARN_THRESHOLD = 50

# --- Institution Abbreviation Map ---
# Corporate author camelCase prefix -> short abbreviation
INSTITUTION_ABBREVIATIONS = {
    "nationaltransportationsafetyboard": "ntsb",
    "federalaviationadministration": "faa",
    "governmentaccountabilityoffice": "gao",
    "congressionalresearchservice": "crs",
    "transportationsafetyboardofcanada": "tsbCanada",
    "internationalatomicenergyagency": "iaea",
    "departmentoftransportation": "dot",
    "departmentofhomelandsecurity": "dhs",
    "officeoftheinspectorgeneral": "oig",
    "nationalacademiesofsciences": "nasem",
}

RATE_LIMIT_DELAY = 0.5

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
    "WISWCTT6": "sackettBiasAnalyticResearch1979",
}


def strip_extra_citekey(extra: str) -> str:
    """Remove any 'Citation Key:' lines from Extra field (legacy cleanup)."""
    if not extra:
        return ""
    lines = extra.splitlines()
    filtered = [ln for ln in lines if not ln.strip().lower().startswith("citation key:")]
    return "\n".join(filtered).strip()


def abbreviate_key(citekey: str) -> str:
    """Apply institution abbreviations to shorten a citation key."""
    lower = citekey.lower()
    for full, short in INSTITUTION_ABBREVIATIONS.items():
        if lower.startswith(full):
            remainder = citekey[len(full):]
            return short + remainder
    return citekey


def validate_key(key: str) -> list[str]:
    """Validate a citation key against usability criteria. Returns list of issues."""
    issues = []
    if not key:
        issues.append("Empty key")
        return issues

    length = len(key)
    if length > WARN_THRESHOLD:
        issues.append(f"Too long ({length} chars, max recommended {WARN_THRESHOLD})")
    elif length > OK_THRESHOLD:
        issues.append(f"Borderline ({length} chars, ideal max {OK_THRESHOLD})")

    if not re.match(r'^[a-zA-Z]', key):
        issues.append("Must start with a letter")
    if re.search(r'[^a-zA-Z0-9_-]', key):
        issues.append("Contains invalid characters (use alphanumeric, _, -)")
    if not re.search(r'\d{4}$', key):
        issues.append("Missing year suffix (should end with 4-digit year)")

    return issues


def audit_library(zot: zotero.Zotero, threshold: int) -> list[dict]:
    """Scan library for citation keys exceeding threshold."""
    items = zot.everything(zot.items(itemType="-attachment"))
    items = [i for i in items if i["data"].get("itemType") not in ("note", "annotation")]

    flagged = []
    for item in items:
        data = item["data"]
        citekey = data.get("citationKey", "")
        if not citekey or len(citekey) <= threshold:
            continue

        suggested = abbreviate_key(citekey)
        flagged.append({
            "key": item["key"],
            "citationKey": citekey,
            "length": len(citekey),
            "title": data.get("title", "N/A")[:55],
            "suggested": suggested,
            "suggested_length": len(suggested),
            "saved": len(citekey) - len(suggested),
        })

    flagged.sort(key=lambda x: x["length"], reverse=True)
    return flagged


def fix_keys(zot: zotero.Zotero, flagged: list[dict], dry_run: bool) -> None:
    """Rewrite flagged citation keys using abbreviation table."""
    fixed = 0
    skipped = 0

    for f in flagged:
        old = f["citationKey"]
        new = f["suggested"]

        if new == old or f["saved"] <= 0:
            print(f"  SKIP: {old} (no abbreviation available)")
            skipped += 1
            continue

        if dry_run:
            print(f"  WOULD: {old} ({f['length']}) -> {new} ({f['suggested_length']}) [-{f['saved']} chars]")
            fixed += 1
        else:
            try:
                item = zot.item(f["key"])
                item["data"]["citationKey"] = new
                zot.update_item(item)
                print(f"  SET: {old} -> {new} [-{f['saved']} chars]")
                fixed += 1
                time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"  ERROR: {old} -> {e}")

    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}{fixed} rewritten, {skipped} skipped")


def main():
    parser = argparse.ArgumentParser(
        description="Set and audit Zotero citation keys (native citationKey field).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--audit", action="store_true", help="Scan library for oversized keys")
    parser.add_argument("--fix", action="store_true", help="Rewrite oversized keys using abbreviation table")
    parser.add_argument("--set", nargs=2, metavar=("ITEM_KEY", "NEW_KEY"), help="Set key on single item")
    parser.add_argument("--check-key", metavar="KEY", help="Validate a proposed citation key")
    parser.add_argument("--threshold", type=int, default=WARN_THRESHOLD, help=f"Length threshold (default: {WARN_THRESHOLD})")
    args = parser.parse_args()

    # Handle audit/fix/set/check modes (no static map needed)
    if args.check_key:
        issues = validate_key(args.check_key)
        if issues:
            print(f"Key '{args.check_key}' ({len(args.check_key)} chars):")
            for issue in issues:
                print(f"  - {issue}")
            suggested = abbreviate_key(args.check_key)
            if suggested != args.check_key:
                print(f"  Suggested: {suggested} ({len(suggested)} chars)")
        else:
            print(f"Key '{args.check_key}' ({len(args.check_key)} chars): OK")
        return

    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)

    if args.set:
        item_key, new_key = args.set
        issues = validate_key(new_key)
        if issues:
            print(f"WARNING: '{new_key}' has issues:")
            for issue in issues:
                print(f"  - {issue}")
        item = zot.item(item_key)
        old = item["data"].get("citationKey", "(empty)")
        if args.dry_run:
            print(f"WOULD SET: {old} -> {new_key}")
        else:
            item["data"]["citationKey"] = new_key
            zot.update_item(item)
            print(f"SET: {old} -> {new_key}")
        return

    if args.audit or args.fix:
        print(f"Scanning library (threshold: {args.threshold} chars)...")
        flagged = audit_library(zot, args.threshold)
        if not flagged:
            print("No citation keys exceed threshold. Library looks good.")
            return
        print(f"\nFound {len(flagged)} keys exceeding {args.threshold} chars:\n")
        print(f"{'Len':>4} {'Save':>5} | {'Current Key':<60} | {'Suggested'}")
        print("-" * 120)
        for f in flagged:
            marker = " *" if f["saved"] > 0 else ""
            print(f"{f['length']:>4} {f['saved']:>+5} | {f['citationKey']:<60} | {f['suggested']}{marker}")
        if args.fix:
            print()
            fix_keys(zot, flagged, args.dry_run)
        return

    # Default: apply static CITEKEY_MAP
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
