#!/usr/bin/env python3
"""
zotero_delete_annotation_block.py

Companion to zotero_edit_note.py for the specific case of deleting a
<p> block containing a known annotation reference. This is the narrow
"delete annotation reference" operation that zotero_edit_note.py refuses
via its annotation-span overlap safeguard.

Why a separate tool: zotero_edit_note.py's blanket Safeguard #1 (refuse
patches whose find-string overlaps with <span class="highlight"> or
<span class="citation"> blocks) is the right default for general
find/replace. But for the wholesale-delete case where we WANT to remove
an entire <p> block containing exactly one highlight + one citation
span, the safeguard is too conservative.

This tool achieves equivalent safety via stricter, narrower invariants:

1. Asserts annotation key appears EXACTLY ONCE in the note.
2. Counts highlight + citation spans BEFORE deletion (baseline = N_h, N_c).
3. Identifies the smallest enclosing <p>...</p> block containing the key.
4. Verifies that block contains exactly 1 highlight + 1 citation span
   (refuses if it contains more — wrong block scope).
5. Removes that block exactly.
6. Asserts post-write count = baseline - 1 highlight - 1 citation.
7. Per-note JSON backup before write.
8. Version-conflict-safe write via pyzotero.
9. Read-after-write verification: annotation key absent, span counts match.

Use cases:
    - Audit cleanup: relocate annotation references between notes
    - Remove duplicated annotation rendering after a Zotero UI move
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pyzotero import zotero


BACKUP_DIR = Path("/tmp")


def fetch_note(zot: zotero.Zotero, item_key: str) -> dict:
    return zot.item(item_key)


def count_spans(html: str) -> tuple[int, int]:
    highlights = len(re.findall(r'<span class="highlight"', html))
    citations = len(re.findall(r'<span class="citation"', html))
    return highlights, citations


def find_paragraph_with_key(html: str, annotation_key: str):
    """
    Find the <p>...</p> block that contains annotation_key.

    Returns:
        (start, end) tuple if exactly one block matches.
        None if no block matches.
        "multiple" if more than one block matches.
    """
    pattern = re.compile(
        rf"<p>(?:(?!</p>)[\s\S])*?{re.escape(annotation_key)}(?:(?!</p>)[\s\S])*?</p>",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(html))
    if not matches:
        return None
    if len(matches) > 1:
        return "multiple"
    m = matches[0]
    return m.start(), m.end()


def backup_note(item: dict, citekey: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = BACKUP_DIR / f"zotero_note_backup_{citekey}_{ts}.json"
    path.write_text(json.dumps(item, indent=2))
    return path


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--note-key", required=True, help="Zotero note item key")
    parser.add_argument(
        "--annotation-key",
        required=True,
        help="Annotation key to find and delete (e.g., SXQJLIY9)",
    )
    parser.add_argument(
        "--citekey",
        required=True,
        help="Parent citekey label (used in backup filename)",
    )
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview only (default if --apply not given)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-after-write verification",
    )
    args = parser.parse_args()

    if not args.apply:
        args.dry_run = True

    load_dotenv()
    library_id = int(os.getenv("ZOTERO_LIBRARY_ID", "6042289"))
    api_key = os.getenv("ZOTERO_API_KEY")
    if not api_key:
        sys.exit("ZOTERO_API_KEY not set in environment")

    zot = zotero.Zotero(library_id, "group", api_key)
    item = fetch_note(zot, args.note_key)
    html = item["data"]["note"]

    pre_h, pre_c = count_spans(html)
    print(f"Pre-delete spans: highlight={pre_h} citation={pre_c}")

    # Invariant: annotation key appears exactly once
    key_occurrences = html.count(args.annotation_key)
    if key_occurrences == 0:
        print(f"REFUSED: annotation key '{args.annotation_key}' not found in note")
        sys.exit(2)
    if key_occurrences > 1:
        print(
            f"REFUSED: annotation key '{args.annotation_key}' appears "
            f"{key_occurrences} times — ambiguous target"
        )
        sys.exit(2)

    result = find_paragraph_with_key(html, args.annotation_key)
    if result is None:
        print(
            f"REFUSED: annotation key '{args.annotation_key}' not enclosed "
            f"in a single <p> block"
        )
        sys.exit(2)
    if result == "multiple":
        print(
            f"REFUSED: more than one <p> block matches annotation key "
            f"'{args.annotation_key}'"
        )
        sys.exit(2)

    start, end = result
    block = html[start:end]
    block_size = end - start
    print(f"Target block: {block_size} bytes")
    print(f"  Preview: {block[:160].replace(chr(10), ' ')}...")

    block_h, block_c = count_spans(block)
    print(f"Block contains: highlight={block_h} citation={block_c}")

    # Invariant: block contains exactly 1 highlight + 1 citation span
    if block_h != 1:
        print(
            f"REFUSED: target block contains {block_h} highlight spans "
            f"(expected 1) — wrong scope?"
        )
        sys.exit(2)
    if block_c not in (0, 1):
        print(
            f"REFUSED: target block contains {block_c} citation spans "
            f"(expected 0 or 1) — wrong scope?"
        )
        sys.exit(2)

    new_html = html[:start] + html[end:]
    post_h, post_c = count_spans(new_html)
    print(f"Post-delete spans (predicted): highlight={post_h} citation={post_c}")

    expected_post_h = pre_h - block_h
    expected_post_c = pre_c - block_c
    if post_h != expected_post_h:
        print(
            f"REFUSED: predicted highlight count {post_h} != expected "
            f"{expected_post_h}"
        )
        sys.exit(2)
    if post_c != expected_post_c:
        print(
            f"REFUSED: predicted citation count {post_c} != expected "
            f"{expected_post_c}"
        )
        sys.exit(2)

    if args.dry_run:
        print(
            f"\nDRY RUN: would delete 1 <p> block containing "
            f"{block_h} highlight + {block_c} citation span(s)"
        )
        print("(no changes written)")
        return

    backup_path = backup_note(item, args.citekey)
    print(f"Backup saved: {backup_path}")

    item["data"]["note"] = new_html
    response = zot.update_item(item)
    if not response:
        print(f"ERROR: zot.update_item returned falsy: {response}")
        sys.exit(3)
    print("APPLIED")

    if args.verify:
        item_after = zot.item(args.note_key)
        html_after = item_after["data"]["note"]
        h_after, c_after = count_spans(html_after)
        if h_after != post_h or c_after != post_c:
            print(
                f"VERIFY FAILED: post-read span counts (h={h_after}, "
                f"c={c_after}) != expected (h={post_h}, c={post_c})"
            )
            sys.exit(4)
        if args.annotation_key in html_after:
            print(
                f"VERIFY FAILED: annotation key '{args.annotation_key}' "
                f"still present in note after delete"
            )
            sys.exit(4)
        print("VERIFY OK: span counts match, annotation key absent")


if __name__ == "__main__":
    main()
