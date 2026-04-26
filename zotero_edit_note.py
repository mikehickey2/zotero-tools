#!/usr/bin/env python3
"""
Edit existing Zotero child notes and parent item metadata via batched patches.

Narrow-scope tool for applying audit-driven corrections to Zotero notes while
preserving PDF annotation metadata. Uses direct pyzotero API calls
(zot.item -> modify -> zot.update_item) with the same fetch->modify->update->verify
pattern as zotero_set_tags.py.

HARD-CODED SAFEGUARDS:
  1. Annotation-span protection. The script refuses any patch whose find-string
     overlaps with a <span class="highlight"> or <span class="citation"> block.
  2. Raw Annotations section protection. The script refuses any patch whose
     find-string lands at or after the "Raw Annotations" heading (h2) in the note.
  3. Read-after-write verification. Confirms replacement text is present AND the
     count of highlight/citation spans is unchanged from the pre-edit baseline.
  4. Per-note JSON backup before any write. Stored in /tmp/ with timestamp,
     enables --rollback.
  5. Dry-run by default. --apply flag is required to actually write.
  6. Version-conflict safe. pyzotero uses If-Unmodified-Since-Version; aborts
     with clear message on 412.

Supports:
  - Simple text find/replace on the note body (HTML).
  - Parent-item metadata updates (e.g., date field) via --metadata-patches.

Does NOT support (out of scope):
  - Cross-note content moves (must be done manually in Zotero UI).
  - Whole-note replacement.
  - Patches that touch annotation metadata.
  - Markdown->HTML conversion (patches must use plain-text strings that match
    the note HTML as stored; ASCII text without special chars is typically safe).

Usage:
    # Dry-run over all patches in a file, write diffs.md:
    python zotero_edit_note.py --patches /tmp/audit_patches_20260423.json \\
        --dry-run --output /tmp/audit_diffs_20260423.md

    # Apply Howard only (test case):
    python zotero_edit_note.py --patches /tmp/audit_patches_20260423.json \\
        --apply --only howardFAASighting2023 --verify

    # Apply all patches with verification:
    python zotero_edit_note.py --patches /tmp/audit_patches_20260423.json \\
        --apply --verify

    # Rollback a single note from backup:
    python zotero_edit_note.py --rollback /tmp/zotero_note_backup_<citekey>_<ts>.json

Patches JSON schema:
    {
      "audit_date": "2026-04-23",
      "audit_reference": "00_inbox/lit-note_audit/audit_batch_review_20260421.md",
      "patches": [
        {
          "citekey": "pitcherAnalysisUnmannedAircraft2022",
          "note_item_key": "3HXMHD7Q",
          "parent_item_key": "NN435K2K",
          "note_patches": [
            {
              "id": "pitcher-finding-1",
              "find": "qualitative examination of regulations, census demographics,",
              "replace": "qualitative examination of regulations,",
              "reason": "Census demographics moved to quantitative per Finding #1",
              "expected_occurrences": 1
            }
          ],
          "metadata_patches": []
        }
      ]
    }
"""

import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

RATE_LIMIT = 0.5
BACKUP_DIR = Path("/tmp")
RAW_ANNOTATIONS_RE = re.compile(
    r"<h[1-6][^>]*>\s*(?:Raw\s+)?Annotations\b[^<]*</h[1-6]>",
    re.IGNORECASE,
)


class SpanRangeFinder(HTMLParser):
    """
    Parse HTML and record byte ranges for <span class="highlight"> and
    <span class="citation"> elements, with correct nesting handling.
    """

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        # Precompute line-start byte offsets so we can convert (line, col) -> offset.
        # html.parser reports positions as 1-based line, 0-based column.
        self.line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.stack: list[tuple[str, int]] = []  # (class_name, start_offset)
        self.ranges: list[tuple[int, int]] = []
        self.feed(text)

    def _offset(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        if tag == "span":
            attrs_dict = dict(attrs)
            cls = attrs_dict.get("class", "")
            self.stack.append((cls, self._offset()))

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.stack:
            cls, start = self.stack.pop()
            end = self._offset() + len("</span>")
            if cls in ("highlight", "citation"):
                self.ranges.append((start, end))


def find_annotation_ranges(html_text: str) -> list[tuple[int, int]]:
    """Return list of (start, end) byte offsets for highlight/citation spans."""
    finder = SpanRangeFinder(html_text)
    return finder.ranges


def find_raw_annotations_boundary(html_text: str) -> int:
    """Return byte offset of the 'Raw Annotations' heading, or -1 if not present."""
    match = RAW_ANNOTATIONS_RE.search(html_text)
    return match.start() if match else -1


def count_annotation_spans(html_text: str) -> int:
    """Count highlight and citation spans. Used for pre/post baseline check."""
    return len(find_annotation_ranges(html_text))


def is_patch_safe(
    html_text: str,
    find_str: str,
    annotation_ranges: list[tuple[int, int]],
    raw_annotations_start: int,
) -> tuple[bool, str]:
    """
    Check that all occurrences of find_str in html_text are SAFE:
      - Not inside or overlapping any highlight/citation span
      - Not at or after the Raw Annotations heading

    Returns (True, "") if safe, else (False, reason).
    """
    if not find_str:
        return False, "Empty find string"
    occurrences = []
    start = 0
    while True:
        idx = html_text.find(find_str, start)
        if idx == -1:
            break
        occurrences.append(idx)
        start = idx + 1
    if not occurrences:
        return False, f"find string not found in note"
    end_of_find = len(find_str)
    for idx in occurrences:
        if raw_annotations_start != -1 and idx >= raw_annotations_start:
            return False, (
                f"occurrence at offset {idx} is at/after 'Raw Annotations' "
                f"section (boundary at {raw_annotations_start}); "
                f"script refuses to modify annotation metadata"
            )
        occ_end = idx + end_of_find
        for span_start, span_end in annotation_ranges:
            overlap = idx < span_end and occ_end > span_start
            if overlap:
                return False, (
                    f"occurrence at offset {idx} overlaps with annotation span "
                    f"[{span_start}, {span_end}]; "
                    f"script refuses to modify annotation content"
                )
    return True, ""


def apply_text_patch(
    html_text: str, find_str: str, replace_str: str, expected: int | None = None
) -> tuple[str, int]:
    """
    Apply a literal text find/replace. Returns (new_html, count_replaced).
    If expected is provided and count differs, raises ValueError.
    """
    count = html_text.count(find_str)
    if expected is not None and count != expected:
        raise ValueError(
            f"expected {expected} occurrence(s), found {count}"
        )
    if count == 0:
        return html_text, 0
    new_html = html_text.replace(find_str, replace_str)
    return new_html, count


def backup_note_payload(
    note_item: dict, note_patches: list[dict], metadata_patches: list[dict], citekey: str
) -> Path:
    """
    Write a JSON backup of the current note state (and any parent metadata
    being touched) to BACKUP_DIR/zotero_note_backup_<citekey>_<ts>.json.
    Returns the backup path.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_path = BACKUP_DIR / f"zotero_note_backup_{citekey}_{ts}.json"
    payload = {
        "backup_created": datetime.now().isoformat(),
        "citekey": citekey,
        "note_item_key": note_item["key"],
        "note_version": note_item["version"],
        "note_html": note_item["data"].get("note", ""),
        "note_patches_to_apply": note_patches,
        "metadata_patches_to_apply": metadata_patches,
    }
    backup_path.write_text(json.dumps(payload, indent=2))
    return backup_path


def backup_parent_metadata(
    parent_item: dict, fields: list[str], citekey: str
) -> Path:
    """Backup parent item fields being modified. Appended to the same backup file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"zotero_parent_backup_{citekey}_{ts}.json"
    payload = {
        "backup_created": datetime.now().isoformat(),
        "citekey": citekey,
        "parent_item_key": parent_item["key"],
        "parent_version": parent_item["version"],
        "fields_backed_up": {f: parent_item["data"].get(f) for f in fields},
    }
    backup_path.write_text(json.dumps(payload, indent=2))
    return backup_path


def format_unified_diff(before: str, after: str, title: str, context: int = 2) -> str:
    """Generate a unified diff string wrapped in a markdown code fence."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"{title} (before)",
            tofile=f"{title} (after)",
            n=context,
        )
    )
    if not diff_lines:
        return "_No changes (find string produced identical output)._\n"
    return "```diff\n" + "".join(diff_lines) + "\n```\n"


def process_note_patches(
    zot: zotero.Zotero,
    citekey: str,
    note_item_key: str,
    patches: list[dict],
    dry_run: bool,
    verify: bool,
) -> dict:
    """
    Apply a sequence of text find/replace patches to a single Zotero note.
    Returns a result dict with status, diff markdown, and messages.
    """
    result = {
        "citekey": citekey,
        "note_item_key": note_item_key,
        "status": "ok",
        "messages": [],
        "diffs": [],
        "patches_applied": 0,
        "patches_refused": 0,
        "backup_path": None,
    }
    try:
        item = zot.item(note_item_key)
    except Exception as e:
        result["status"] = "error"
        result["messages"].append(f"FETCH ERROR: {e}")
        return result

    if item["data"].get("itemType") != "note":
        result["status"] = "error"
        result["messages"].append(
            f"item {note_item_key} is not a note (itemType="
            f"{item['data'].get('itemType')!r}); refusing to patch"
        )
        return result

    original_html = item["data"].get("note", "")
    current_html = original_html
    pre_span_count = count_annotation_spans(original_html)
    raw_start = find_raw_annotations_boundary(original_html)
    annotation_ranges = find_annotation_ranges(original_html)

    for patch in patches:
        patch_id = patch.get("id", "(no id)")
        find_str = patch.get("find", "")
        replace_str = patch.get("replace", "")
        expected = patch.get("expected_occurrences")
        reason = patch.get("reason", "")

        # Safety check against current_html (so patches accumulate correctly)
        safe, why = is_patch_safe(
            current_html,
            find_str,
            find_annotation_ranges(current_html),
            find_raw_annotations_boundary(current_html),
        )
        if not safe:
            result["messages"].append(
                f"REFUSED patch '{patch_id}': {why}. "
                f"(reason: {reason})"
            )
            result["patches_refused"] += 1
            continue

        try:
            new_html, count = apply_text_patch(
                current_html, find_str, replace_str, expected
            )
        except ValueError as e:
            result["messages"].append(
                f"REFUSED patch '{patch_id}': {e}. (reason: {reason})"
            )
            result["patches_refused"] += 1
            continue

        # Generate diff for this single patch
        diff_title = f"{citekey} :: {patch_id}"
        diff_md = format_unified_diff(current_html, new_html, diff_title)
        result["diffs"].append(
            {
                "patch_id": patch_id,
                "reason": reason,
                "count": count,
                "diff": diff_md,
            }
        )
        result["messages"].append(
            f"OK patch '{patch_id}': {count} occurrence(s) will be replaced. "
            f"(reason: {reason})"
        )
        result["patches_applied"] += 1
        current_html = new_html

    if result["patches_applied"] == 0 or current_html == original_html:
        result["messages"].append("no effective changes")
        return result

    if dry_run:
        result["status"] = "dry-run"
        return result

    # Backup before write
    result["backup_path"] = str(
        backup_note_payload(item, patches, [], citekey)
    )

    # Annotation span count check pre-write
    new_span_count = count_annotation_spans(current_html)
    if new_span_count != pre_span_count:
        result["status"] = "error"
        result["messages"].append(
            f"SAFETY ABORT: annotation span count changed "
            f"({pre_span_count} -> {new_span_count}); refusing to write."
        )
        return result

    # Write
    item["data"]["note"] = current_html
    try:
        zot.update_item(item)
    except HTTPError as e:
        result["status"] = "error"
        result["messages"].append(f"API ERROR on write: {e}")
        return result
    except Exception as e:
        result["status"] = "error"
        result["messages"].append(f"WRITE ERROR: {e}")
        return result

    # Verify
    if verify:
        try:
            updated = zot.item(note_item_key)
            post_html = updated["data"].get("note", "")
            post_span_count = count_annotation_spans(post_html)
            verify_msgs = []
            if post_span_count != pre_span_count:
                verify_msgs.append(
                    f"span count changed ({pre_span_count} -> {post_span_count})"
                )
            for patch in patches:
                find_str = patch.get("find", "")
                replace_str = patch.get("replace", "")
                if find_str in post_html and replace_str != find_str:
                    verify_msgs.append(
                        f"old text still present for patch "
                        f"'{patch.get('id', '?')}'"
                    )
                if replace_str and replace_str not in post_html:
                    verify_msgs.append(
                        f"new text not present for patch "
                        f"'{patch.get('id', '?')}'"
                    )
            if verify_msgs:
                result["status"] = "verify-failed"
                result["messages"].append(
                    "VERIFY FAILED: " + "; ".join(verify_msgs)
                )
            else:
                result["messages"].append("verified post-write: OK")
        except Exception as e:
            result["status"] = "verify-failed"
            result["messages"].append(f"VERIFY ERROR: {e}")

    if result["status"] == "ok":
        result["status"] = "applied"
    return result


def process_metadata_patches(
    zot: zotero.Zotero,
    citekey: str,
    parent_item_key: str,
    patches: list[dict],
    dry_run: bool,
    verify: bool,
) -> dict:
    """Apply parent-item metadata field updates."""
    result = {
        "citekey": citekey,
        "parent_item_key": parent_item_key,
        "status": "ok",
        "messages": [],
        "patches_applied": 0,
        "patches_refused": 0,
        "backup_path": None,
    }
    if not patches:
        return result

    try:
        item = zot.item(parent_item_key)
    except Exception as e:
        result["status"] = "error"
        result["messages"].append(f"FETCH ERROR (parent): {e}")
        return result

    planned_changes = []
    for patch in patches:
        field = patch.get("field")
        new_value = patch.get("new_value")
        reason = patch.get("reason", "")
        if not field or new_value is None:
            result["messages"].append(
                f"REFUSED metadata patch: missing 'field' or 'new_value'"
            )
            result["patches_refused"] += 1
            continue
        current = item["data"].get(field)
        if current == new_value:
            result["messages"].append(
                f"SKIP metadata.{field}: already equals {new_value!r}"
            )
            continue
        planned_changes.append((field, current, new_value, reason))

    if not planned_changes:
        result["messages"].append("no metadata changes needed")
        return result

    for field, current, new_value, reason in planned_changes:
        result["messages"].append(
            f"metadata.{field}: {current!r} -> {new_value!r}  (reason: {reason})"
        )

    if dry_run:
        result["status"] = "dry-run"
        return result

    # Backup
    fields_to_backup = list({c[0] for c in planned_changes})
    result["backup_path"] = str(
        backup_parent_metadata(item, fields_to_backup, citekey)
    )

    # Apply
    for field, _current, new_value, _reason in planned_changes:
        item["data"][field] = new_value
        result["patches_applied"] += 1

    try:
        zot.update_item(item)
    except HTTPError as e:
        result["status"] = "error"
        result["messages"].append(f"API ERROR on metadata write: {e}")
        return result
    except Exception as e:
        result["status"] = "error"
        result["messages"].append(f"WRITE ERROR (metadata): {e}")
        return result

    if verify:
        try:
            updated = zot.item(parent_item_key)
            failures = []
            for field, _current, new_value, _reason in planned_changes:
                actual = updated["data"].get(field)
                if actual != new_value:
                    failures.append(f"{field}: expected {new_value!r}, got {actual!r}")
            if failures:
                result["status"] = "verify-failed"
                result["messages"].append(
                    "VERIFY FAILED (metadata): " + "; ".join(failures)
                )
            else:
                result["messages"].append("verified metadata post-write: OK")
        except Exception as e:
            result["status"] = "verify-failed"
            result["messages"].append(f"VERIFY ERROR (metadata): {e}")

    if result["status"] == "ok":
        result["status"] = "applied"
    return result


def rollback_from_backup(zot: zotero.Zotero, backup_path: Path) -> int:
    """Restore a note or parent item from a backup JSON. Returns exit code."""
    data = json.loads(backup_path.read_text())
    if "note_html" in data:
        # Note rollback
        note_key = data["note_item_key"]
        item = zot.item(note_key)
        item["data"]["note"] = data["note_html"]
        try:
            zot.update_item(item)
        except Exception as e:
            print(f"ROLLBACK FAILED (note {note_key}): {e}")
            return 1
        print(f"Rolled back note {note_key} to state from {data['backup_created']}")
        return 0
    elif "fields_backed_up" in data:
        # Parent metadata rollback
        parent_key = data["parent_item_key"]
        item = zot.item(parent_key)
        for field, prior_value in data["fields_backed_up"].items():
            item["data"][field] = prior_value
        try:
            zot.update_item(item)
        except Exception as e:
            print(f"ROLLBACK FAILED (parent {parent_key}): {e}")
            return 1
        print(
            f"Rolled back parent {parent_key} fields "
            f"{list(data['fields_backed_up'].keys())} "
            f"to state from {data['backup_created']}"
        )
        return 0
    else:
        print(f"Unknown backup format in {backup_path}")
        return 1


def load_patches(path: Path) -> dict:
    """Load and validate patches JSON."""
    data = json.loads(path.read_text())
    if "patches" not in data or not isinstance(data["patches"], list):
        print(f"ERROR: patches file must have a 'patches' array")
        sys.exit(1)
    return data


def write_diffs_markdown(output_path: Path, data: dict, all_results: list[dict]) -> None:
    """Write the dry-run diffs to a markdown file."""
    lines = []
    lines.append("# Audit Patches Dry-Run Diffs\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Source patches: audit_date={data.get('audit_date', 'unknown')}\n")
    lines.append(f"Total note-batches: {len(all_results)}\n\n")

    for res in all_results:
        if res.get("kind") == "metadata":
            lines.append(f"\n## (metadata) {res['citekey']}\n\n")
            lines.append(f"**Parent item key:** `{res['parent_item_key']}`\n\n")
            for m in res["messages"]:
                lines.append(f"- {m}\n")
            continue
        lines.append(f"\n## {res['citekey']}\n\n")
        lines.append(f"**Note item key:** `{res['note_item_key']}`  \n")
        lines.append(
            f"**Patches:** {res['patches_applied']} OK, "
            f"{res['patches_refused']} refused\n\n"
        )
        for msg in res["messages"]:
            lines.append(f"- {msg}\n")
        for d in res.get("diffs", []):
            lines.append(f"\n### Patch: `{d['patch_id']}`\n")
            lines.append(f"- **Reason:** {d['reason']}\n")
            lines.append(f"- **Occurrences:** {d['count']}\n\n")
            lines.append(d["diff"])
            lines.append("\n")
    output_path.write_text("".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply audit-driven patches to Zotero child notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--patches",
        type=Path,
        help="Path to patches JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (required to modify anything)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-after-write verification",
    )
    parser.add_argument(
        "--only",
        metavar="CITEKEY",
        help="Process only the specified citekey",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/audit_diffs.md"),
        help="Where to write diffs.md during dry-run (default /tmp/audit_diffs.md)",
    )
    parser.add_argument(
        "--rollback",
        type=Path,
        metavar="BACKUP_JSON",
        help="Restore a note or parent from a backup JSON file",
    )
    args = parser.parse_args()

    if args.rollback:
        library_id, library_type, api_key = load_credentials()
        zot = zotero.Zotero(library_id, library_type, api_key)
        return rollback_from_backup(zot, args.rollback)

    if not args.patches:
        parser.error("--patches is required (unless --rollback)")

    if not args.patches.exists():
        print(f"ERROR: patches file not found: {args.patches}")
        return 1

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    dry_run = not args.apply

    data = load_patches(args.patches)
    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)

    batches = data["patches"]
    if args.only:
        batches = [b for b in batches if b.get("citekey") == args.only]
        if not batches:
            print(f"ERROR: no batch matched --only {args.only!r}")
            return 1

    mode = "DRY RUN" if dry_run else "APPLY"
    print(f"\n{mode}: Processing {len(batches)} note batch(es)")
    if args.only:
        print(f"  Filter: only {args.only}")
    print()

    all_results = []
    total_errors = 0
    total_applied = 0
    total_refused = 0

    for i, batch in enumerate(batches):
        citekey = batch.get("citekey", "(missing citekey)")
        note_item_key = batch.get("note_item_key")
        parent_item_key = batch.get("parent_item_key")
        note_patches = batch.get("note_patches", [])
        metadata_patches = batch.get("metadata_patches", [])

        print(f"\n[{i + 1}/{len(batches)}] {citekey}")
        print(f"  note_item_key={note_item_key}  parent_item_key={parent_item_key}")
        print(
            f"  note_patches={len(note_patches)}  "
            f"metadata_patches={len(metadata_patches)}"
        )

        if note_patches and note_item_key:
            note_result = process_note_patches(
                zot, citekey, note_item_key, note_patches,
                dry_run=dry_run, verify=args.verify,
            )
            all_results.append(note_result)
            for msg in note_result["messages"]:
                print(f"    {msg}")
            total_applied += note_result["patches_applied"]
            total_refused += note_result["patches_refused"]
            if note_result["status"] in ("error", "verify-failed"):
                total_errors += 1

            if not dry_run and i < len(batches) - 1:
                time.sleep(RATE_LIMIT)

        if metadata_patches and parent_item_key:
            meta_result = process_metadata_patches(
                zot, citekey, parent_item_key, metadata_patches,
                dry_run=dry_run, verify=args.verify,
            )
            meta_result["kind"] = "metadata"
            all_results.append(meta_result)
            for msg in meta_result["messages"]:
                print(f"    {msg}")
            total_applied += meta_result["patches_applied"]
            total_refused += meta_result["patches_refused"]
            if meta_result["status"] in ("error", "verify-failed"):
                total_errors += 1

            if not dry_run and i < len(batches) - 1:
                time.sleep(RATE_LIMIT)

    print(
        f"\n{mode}: {total_applied} patch(es) {'will be applied' if dry_run else 'applied'}, "
        f"{total_refused} refused, {total_errors} error(s)"
    )

    if dry_run:
        write_diffs_markdown(args.output, data, all_results)
        print(f"\nDiffs written to: {args.output}")

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
