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


# CLI assembly comes in Task 4.
if __name__ == "__main__":
    pass
