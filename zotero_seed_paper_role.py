#!/usr/bin/env python3
"""
Seed Zotero Extra-field `paper_role` from the master reading plan markdown,
plus apply `#NeedsDeeperRead` tag to brief-notes items.

One-shot ETL. After this runs successfully, the master reading plan markdown
is archived; Zotero becomes the canonical source for paper_role.

Mapping rules (in priority order):
  1. Items under "Must-Read" section header     → must-read
  2. Items under "Should-Read" section header   → should-read
  3. Items with "CORNERSTONE" marker in role    → cornerstone (overrides any tier)
  4. Items in "Brief Vault Notes Needing Deeper Reading" → preserve role, also tag NeedsDeeperRead
  5. Items in "Archived Items" section          → archived
  6. Items in 06-Statistical-Foundations        → methodological
  7. Items in 02-News-and-Web                   → reference-only
  8. Default for Tier 1 items                   → supporting

Usage:
    python zotero_seed_paper_role.py --reading-plan PATH --dry-run --verbose
    python zotero_seed_paper_role.py --reading-plan PATH --verify
"""
import argparse
import re
import sys
import time
from collections import Counter
from typing import Dict, List, Tuple

# Section header regex — accepts ## or ### markdown headers
SECTION_RE = re.compile(r"^#{2,4}\s+(.+)$", re.MULTILINE)

# Citekey extractor — matches backtick-wrapped Zotero item keys (8 alphanumeric chars uppercase)
CITEKEY_RE = re.compile(r"`([A-Z0-9]{8})`")

# Cornerstone marker in role text
CORNERSTONE_RE = re.compile(r"\bCORNERSTONE\b", re.IGNORECASE)

# Brief-notes marker
NEEDS_DEEPER_RE = re.compile(r"needs deeper reading", re.IGNORECASE)

# Collection markers
COLLECTION_RE = re.compile(r"Collection:\s*([^\s|]+)", re.IGNORECASE)


def parse_reading_plan(path: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Parse the master reading plan markdown.

    Returns:
        (mapping, needs_deeper_list) where:
          mapping = {citekey: paper_role}
          needs_deeper_list = [citekey, ...] for items flagged "needs deeper reading"
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    mapping: Dict[str, str] = {}
    needs_deeper: List[str] = []

    # Walk top-level sections by scanning headers and tracking current section context
    lines = text.split("\n")
    current_h2 = ""  # Tier or other top-level
    current_h3 = ""  # Subsection (Must-Read, Should-Read, collection name, etc.)

    # Use list as mutable container so closure can update it
    state = {"current_item_lines": [], "current_item_citekey": None}

    def flush_item():
        """Resolve role for the accumulated item lines and store it."""
        if state["current_item_citekey"] is None:
            return
        item_text = "\n".join(state["current_item_lines"])
        role = resolve_role(item_text, current_h2, current_h3)
        if role is not None:
            mapping[state["current_item_citekey"]] = role
        if NEEDS_DEEPER_RE.search(item_text):
            needs_deeper.append(state["current_item_citekey"])

    for raw in lines:
        line = raw.rstrip()

        # Header detection
        m = re.match(r"^(#{2,4})\s+(.+)$", line)
        if m:
            flush_item()
            state["current_item_citekey"] = None
            state["current_item_lines"] = []
            depth = len(m.group(1))
            text_h = m.group(2).strip()
            if depth == 2:
                current_h2 = text_h
                current_h3 = ""
            elif depth >= 3:
                current_h3 = text_h
            continue

        # Item start: a bullet/numbered line containing a citekey
        m_key = CITEKEY_RE.search(line)
        if m_key and (line.lstrip().startswith("-") or re.match(r"^\s*\d+\.\s", line)):
            flush_item()
            state["current_item_citekey"] = m_key.group(1)
            state["current_item_lines"] = [line]
            continue

        # Continuation of current item (indented sub-bullet)
        if state["current_item_citekey"] is not None and (line.startswith("  ") or line.startswith("\t")):
            state["current_item_lines"].append(line)
            continue

        # Blank line / unrelated content — flush
        if not line.strip():
            flush_item()
            state["current_item_citekey"] = None
            state["current_item_lines"] = []

    flush_item()  # final item
    return mapping, needs_deeper


def resolve_role(item_text: str, h2: str, h3: str):
    """Apply the mapping rules to a single item's accumulated text + section context.

    Returns paper_role string or None if no rule matches.
    """
    # Rule 3: Cornerstone marker wins over everything
    if CORNERSTONE_RE.search(item_text):
        return "cornerstone"

    # Rule 1: Must-Read section
    if "Must-Read" in h3:
        return "must-read"

    # Rule 2: Should-Read section
    if "Should-Read" in h3:
        return "should-read"

    # Rule 5: Archived
    if "Archived Items" in h3 or "08-Archive" in h3:
        return "archived"

    # Rule 6: Statistical
    if "Statistical-Foundations" in h3 or "06-Statistical" in h3:
        return "methodological"

    # Rule 7: News and Web
    if "Non-Academic" in h3 or "News-and-Web" in h3:
        return "reference-only"

    # Inline collection marker (subsection's text mentions it)
    coll_match = COLLECTION_RE.search(item_text)
    if coll_match:
        coll = coll_match.group(1)
        if "Statistical" in coll:
            return "methodological"
        if "News-and-Web" in coll:
            return "reference-only"

    # Rule 8: Tier 1 default
    if "Tier 1" in h2 or "04/" in h3 or "05/" in h3:
        return "supporting"

    # Tier 2 default
    if "Tier 2" in h2 or "07-Background" in h3:
        return "supporting"

    # Fall-through: don't write anything for this item
    return None


# ─── Zotero write layer ─────────────────────────────────────────────

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError
from zotero_utils import load_credentials

SKIP_ITEM_TYPES = {"attachment", "annotation", "note"}
RATE_LIMIT = 0.5
EXTRA_KEY = "paper_role"
NEEDS_DEEPER_TAG = "NeedsDeeperRead"


def extract_extra_key(extra_text, key):
    pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE)
    m = pattern.search(extra_text or "")
    return m.group(1).strip() if m else None


def upsert_extra_key(extra_text, key, value):
    pattern = re.compile(rf"^{re.escape(key)}\s*:.*$", re.MULTILINE)
    new_line = f"{key}: {value}"
    if pattern.search(extra_text):
        return pattern.sub(new_line, extra_text, count=1)
    if extra_text and not extra_text.endswith("\n"):
        extra_text += "\n"
    return extra_text + new_line


def apply_paper_role(zot, item_key, role, *, dry_run=False, verify=False):
    """Write paper_role to a single item's Extra field. Returns (action, message)."""
    try:
        item = zot.item(item_key)
    except Exception as e:
        return "error", f"{item_key}: fetch failed: {e}"

    item_type = item["data"].get("itemType", "")
    if item_type in SKIP_ITEM_TYPES:
        return "skipped", f"{item_key}: {item_type} (skipping)"

    title = item["data"].get("title", "(no title)")[:50]
    extra = item["data"].get("extra", "") or ""
    current = extract_extra_key(extra, EXTRA_KEY)

    if current == role:
        return "skipped", f"{item_key} [{title}] already paper_role={role}"

    new_extra = upsert_extra_key(extra, EXTRA_KEY, role)
    diff = f"paper_role: {current or '(none)'} -> {role}"

    if dry_run:
        return "updated", f"{item_key} [{title}]  {diff}"

    item["data"]["extra"] = new_extra
    try:
        zot.update_item(item)
    except HTTPError as e:
        return "error", f"{item_key} [{title}]: API error: {e}"

    msg = f"{item_key} [{title}]  {diff}"
    if verify:
        time.sleep(0.1)
        try:
            fresh = zot.item(item_key)
            verified = extract_extra_key(fresh["data"].get("extra", ""), EXTRA_KEY)
            if verified != role:
                return "error", f"{msg}  VERIFY FAILED: got '{verified}'"
            msg += "  verified"
        except Exception as e:
            return "error", f"{msg}  VERIFY ERROR: {e}"

    return "updated", msg


def apply_needs_deeper_tag(zot, item_key, *, dry_run=False, verify=False):
    """Add #NeedsDeeperRead tag to a single item. Returns (action, message)."""
    try:
        item = zot.item(item_key)
    except Exception as e:
        return "error", f"{item_key}: fetch failed: {e}"

    item_type = item["data"].get("itemType", "")
    if item_type in SKIP_ITEM_TYPES:
        return "skipped", f"{item_key}: {item_type} (skipping)"

    title = item["data"].get("title", "(no title)")[:50]
    current_tags = {t["tag"] for t in item["data"].get("tags", [])}

    if NEEDS_DEEPER_TAG in current_tags:
        return "skipped", f"{item_key} [{title}] already tagged"

    new_tags = current_tags | {NEEDS_DEEPER_TAG}

    if dry_run:
        return "updated", f"{item_key} [{title}]  +{NEEDS_DEEPER_TAG}"

    item["data"]["tags"] = [{"tag": t} for t in sorted(new_tags)]
    try:
        zot.update_item(item)
    except HTTPError as e:
        return "error", f"{item_key} [{title}]: API error: {e}"

    msg = f"{item_key} [{title}]  +{NEEDS_DEEPER_TAG}"
    if verify:
        time.sleep(0.1)
        try:
            fresh = zot.item(item_key)
            actual = {t["tag"] for t in fresh["data"].get("tags", [])}
            if NEEDS_DEEPER_TAG not in actual:
                return "error", f"{msg}  VERIFY FAILED: tag not present"
            msg += "  verified"
        except Exception as e:
            return "error", f"{msg}  VERIFY ERROR: {e}"

    return "updated", msg


def main():
    parser = argparse.ArgumentParser(
        description="Seed paper_role from master reading plan into Zotero Extra field.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--reading-plan", required=True,
                        help="Path to master reading plan markdown")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only; no writes")
    parser.add_argument("--verify", action="store_true",
                        help="Read-after-write confirmation")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each action")
    parser.add_argument("--skip-needs-deeper", action="store_true",
                        help="Only write paper_role; skip NeedsDeeperRead tagging")
    args = parser.parse_args()

    print(f"Parsing reading plan: {args.reading_plan}")
    mapping, needs_deeper = parse_reading_plan(args.reading_plan)
    print(f"  {len(mapping)} citekey->role mappings found")
    print(f"  {len(needs_deeper)} items flagged needs-deeper-read")
    if args.verbose:
        role_counts = Counter(mapping.values())
        for role, n in sorted(role_counts.items(), key=lambda x: -x[1]):
            print(f"    {role:18} {n}")
    print()

    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)
    print(f"Library: {library_type}/{library_id}")
    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"Mode: {mode}\n")

    counts = Counter()
    items_list = list(mapping.items())
    for i, (citekey, role) in enumerate(items_list):
        action, msg = apply_paper_role(zot, citekey, role,
                                         dry_run=args.dry_run, verify=args.verify)
        counts[action] += 1
        if args.verbose or action in ("error",):
            prefix = {"updated": "->", "skipped": "  ", "error": "X "}.get(action, "? ")
            print(f"  {prefix} {msg}")
        if not args.dry_run and action == "updated" and i < len(items_list) - 1:
            time.sleep(RATE_LIMIT)

    if not args.skip_needs_deeper:
        print("\nApplying #NeedsDeeperRead tags...")
        for i, citekey in enumerate(needs_deeper):
            action, msg = apply_needs_deeper_tag(zot, citekey,
                                                  dry_run=args.dry_run, verify=args.verify)
            counts[f"tag_{action}"] += 1
            if args.verbose or action in ("error",):
                prefix = {"updated": "->", "skipped": "  ", "error": "X "}.get(action, "? ")
                print(f"  {prefix} {msg}")
            if not args.dry_run and action == "updated" and i < len(needs_deeper) - 1:
                time.sleep(RATE_LIMIT)

    print("\n" + "=" * 60)
    print("Summary:")
    for action in sorted(counts.keys()):
        if counts[action]:
            print(f"  {action:18} {counts[action]}")
    if args.dry_run:
        print("\n[DRY RUN] No changes written. Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
