#!/usr/bin/env python3
"""
zotero_attach_with_verify.py

Attach a file to a Zotero parent item with deduplication safety, annotation
protection, and post-upload verification.

Background:
    pyzotero's attachment_simple silently classifies uploads as "unchanged"
    when Zotero's server-side md5 deduplication matches a file already in
    storage. The server claims to auto-link the existing file, but this
    sometimes fails to propagate, leaving an empty attachment record.

This wrapper:
    1. Inspects existing attachments on the parent item
    2. Blocks upload if it would overlap with annotated content
    3. Skips silently if exact md5 duplicate already attached
    4. Warns on filename match or fragment-size suspicion
    5. Polls fulltext_item after upload to verify the file is accessible
    6. Falls back to md5-mutation force-upload if dedup blocks the file

Usage:
    # Single file
    python zotero_attach_with_verify.py PARENT_KEY FILE_PATH

    # Dry run (all checks, no upload)
    python zotero_attach_with_verify.py PARENT_KEY FILE_PATH --dry-run

    # Verbose output
    python zotero_attach_with_verify.py PARENT_KEY FILE_PATH --verbose

    # Proceed past warnings (filename match, fragment suspicion, annotations)
    python zotero_attach_with_verify.py PARENT_KEY FILE_PATH --force-add

    # Bypass server-side dedup if attachment_simple unchanged + verify failed
    python zotero_attach_with_verify.py PARENT_KEY FILE_PATH --force-upload

    # Batch mode (JSON input: {"PARENT_KEY": ["path1.pdf", "path2.pdf"]})
    python zotero_attach_with_verify.py --batch attachments.json

Exit codes:
    0  = uploaded or skipped (already attached); no user action needed
    1  = blocked by safety check; user must review
    2  = upload reported unchanged but verification failed; manual drag-drop or
         --force-upload required
    3  = unexpected error
"""

import argparse
import json
import sys
from pathlib import Path

from pyzotero import zotero

from zotero_utils import attach_with_safety, load_credentials


STATUS_EXIT = {
    'attached': 0,
    'verified': 0,
    'skipped_duplicate': 0,
    'aborted_dry_run': 0,
    'blocked_annotations': 1,
    'blocked_warning': 1,
    'unverified': 2,
    'error': 3,
}


def _print_decisions(decisions):
    if not decisions:
        print("  (no existing attachments)")
        return
    for label, key, reason in decisions:
        print(f"  [{label}] {key}: {reason}")


def _print_result(file_path, parent_key, result):
    print(f"\n=== {Path(file_path).name} -> {parent_key} ===")
    print(f"Status:       {result['status']}")
    print(f"Message:      {result['message']}")
    print(f"Verification: {result['verification']}")
    if result.get('attachment_key'):
        print(f"Attachment:   {result['attachment_key']}")
    print("Pre-flight decisions:")
    _print_decisions(result['decisions'])


def _connect():
    library_id, library_type, api_key = load_credentials()
    print(f"Connecting to Zotero (library_id={library_id}, "
          f"library_type={library_type})...")
    return zotero.Zotero(library_id, library_type, api_key)


def _process_one(zot, parent_key, file_path, args):
    result = attach_with_safety(
        zot, parent_key, file_path,
        force_add=args.force_add,
        force_upload=args.force_upload,
        skip_annotated=args.skip_annotated,
        dry_run=args.dry_run,
        fragment_threshold=args.fragment_threshold,
        verify_timeout=args.verify_timeout,
        verbose=args.verbose,
    )
    _print_result(file_path, parent_key, result)
    return STATUS_EXIT.get(result['status'], 3)


def _process_batch(zot, batch_path, args):
    path = Path(batch_path)
    if not path.exists():
        print(f"ERROR: batch file not found: {batch_path}", file=sys.stderr)
        return 3
    with open(path) as f:
        batch = json.load(f)
    if not isinstance(batch, dict):
        print("ERROR: batch JSON must be {parent_key: [file1, file2, ...]}",
              file=sys.stderr)
        return 3

    worst_exit = 0
    for parent_key, files in batch.items():
        if not isinstance(files, list):
            print(f"ERROR: '{parent_key}' value must be a list of file paths",
                  file=sys.stderr)
            worst_exit = max(worst_exit, 3)
            continue
        for file_path in files:
            exit_code = _process_one(zot, parent_key, file_path, args)
            worst_exit = max(worst_exit, exit_code)
    return worst_exit


def main():
    parser = argparse.ArgumentParser(
        description="Attach a file to a Zotero item with safety + verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('parent_key', nargs='?',
                        help='Zotero parent item key (e.g., JAXTF3DF)')
    parser.add_argument('file_path', nargs='?',
                        help='Path to local file to attach')
    parser.add_argument('--batch',
                        help='Path to JSON file: {parent_key: [files]}')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run all safety checks; do not upload')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print every check and decision')
    parser.add_argument('--force-add', action='store_true',
                        help='Proceed past warnings (filename match, fragment '
                             'suspicion, annotations). New attachment is '
                             'added alongside; existing attachments are never '
                             'modified or deleted.')
    parser.add_argument('--force-upload', action='store_true',
                        help='If attachment_simple returns unchanged and '
                             'verification fails, retry with md5-mutated copy '
                             'to bypass server-side dedup.')
    parser.add_argument('--skip-annotated', action='store_true',
                        help='Skip silently if existing attachment has '
                             'annotations (default: block + report).')
    parser.add_argument('--fragment-threshold', type=float, default=0.7,
                        help='Existing attachment <X%% of local file size = '
                             'fragment suspicion (default: 0.7)')
    parser.add_argument('--verify-timeout', type=int, default=15,
                        help='Seconds to poll fulltext_item after upload '
                             '(default: 15)')

    args = parser.parse_args()

    if args.batch:
        zot = _connect()
        sys.exit(_process_batch(zot, args.batch, args))

    if not args.parent_key or not args.file_path:
        parser.error('parent_key and file_path required (or use --batch)')

    zot = _connect()
    sys.exit(_process_one(zot, args.parent_key, args.file_path, args))


if __name__ == '__main__':
    main()
