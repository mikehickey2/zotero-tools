"""
Shared utilities for Zotero Tools scripts.

This module provides common functionality used across all Zotero Tools scripts,
including credential loading and API connection helpers.
"""

import hashlib
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv


def load_credentials() -> tuple[str, str, str]:
    """
    Load Zotero credentials from environment variables or .env file.

    Returns:
        Tuple of (library_id, library_type, api_key)

    Raises:
        SystemExit: If required credentials are missing
    """
    load_dotenv()

    library_id = os.getenv('ZOTERO_LIBRARY_ID')
    library_type = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')
    api_key = os.getenv('ZOTERO_API_KEY')

    missing = []
    if not library_id:
        missing.append('ZOTERO_LIBRARY_ID')
    if not api_key:
        missing.append('ZOTERO_API_KEY')

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease set these in your environment or create a .env file.")
        print("See .env.example for the expected format.")
        sys.exit(1)

    return library_id, library_type, api_key


# =============================================================================
# Attachment safety + verification (zotero_attach_with_verify)
# =============================================================================
# Background:
#   pyzotero's attachment_simple silently classifies uploads as "unchanged" when
#   Zotero's server-side md5 deduplication matches a file already in storage.
#   The server claims to auto-link the existing file, but in practice this does
#   not always propagate, leaving the attachment record without an accessible
#   file blob.
#
#   This module adds a safety + verification layer:
#     1. Pre-flight checks (dedup, annotation protection, fragment detection)
#     2. attachment_simple call
#     3. Post-upload verification with polling
#     4. Clear human-readable status
# =============================================================================


def compute_md5(file_path: str) -> str:
    """Compute md5 of a file using stream reads (safe for large files)."""
    h = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _classify_existing_attachment(zot, attachment, local_md5, local_size,
                                   local_filename, fragment_threshold):
    """
    Classify a single existing attachment against the local file.

    Returns a tuple: (label, attachment_key, reason_string)
    Labels: ANNOTATED, DUPLICATE, FILENAME_MATCH, POSSIBLE_FRAGMENT,
            DIFFERENT_LINKMODE, UNRELATED
    """
    att_key = attachment['key']
    att_data = attachment['data']
    att_md5 = att_data.get('md5')
    att_filename = att_data.get('filename', '')
    att_filesize = att_data.get('filesize')
    att_link_mode = att_data.get('linkMode', 'imported_file')

    # Annotation check: pull this attachment's children and look for annotations
    try:
        att_children = zot.children(att_key)
    except Exception:
        att_children = []
    annotations = [c for c in att_children
                   if c.get('data', {}).get('itemType') == 'annotation']

    if annotations:
        return ('ANNOTATED', att_key,
                f"{len(annotations)} annotation(s) on '{att_filename}' "
                f"(link_mode={att_link_mode})")

    # md5 match takes precedence over filename match
    if att_md5 and att_md5 == local_md5:
        return ('DUPLICATE', att_key,
                f"exact md5 match on '{att_filename}'")

    # Different link mode (e.g., linked_file or imported_url)
    if att_link_mode != 'imported_file':
        return ('DIFFERENT_LINKMODE', att_key,
                f"existing attachment uses link_mode={att_link_mode} "
                f"('{att_filename}')")

    if att_filename == local_filename:
        return ('FILENAME_MATCH', att_key,
                f"filename match but different content "
                f"(local md5={local_md5[:8]}..., "
                f"existing md5={(att_md5 or 'unknown')[:8]}...)")

    if att_filesize and att_filesize < local_size * fragment_threshold:
        return ('POSSIBLE_FRAGMENT', att_key,
                f"existing attachment is {att_filesize} bytes vs your "
                f"{local_size} bytes ({100*att_filesize/local_size:.0f}% of local; "
                f"<{int(fragment_threshold*100)}% threshold)")

    return ('UNRELATED', att_key,
            f"different file: '{att_filename}' "
            f"({att_filesize or '?'} bytes, "
            f"md5={(att_md5 or 'unknown')[:8]}...)")


def _verify_attachment_accessible(zot, attachment_key, timeout_seconds=15):
    """
    Poll fulltext_item until the attachment is accessible or timeout.

    Returns True if verified within timeout, False otherwise.
    """
    delays = [1, 2, 3, 4, 5]  # ~15 second total
    elapsed = 0
    for delay in delays:
        if elapsed >= timeout_seconds:
            break
        time.sleep(delay)
        elapsed += delay
        try:
            ft = zot.fulltext_item(attachment_key)
            # Either content present, or indexed pages reported, or even a
            # successful empty response — all indicate the file is linked
            if ft is not None:
                return True
        except Exception:
            # 404 or other; keep polling
            continue
    return False


def attach_with_safety(zot, parent_key, file_path, *,
                       force_add=False,
                       force_upload=False,
                       skip_annotated=False,
                       dry_run=False,
                       fragment_threshold=0.7,
                       verify_timeout=15,
                       verbose=False):
    """
    Attach a file to a Zotero parent item, with deduplication and annotation
    safety, plus post-upload verification.

    Args:
        zot: pyzotero.zotero.Zotero instance (already authenticated)
        parent_key: Zotero item key of the parent (e.g., 'JAXTF3DF')
        file_path: absolute path to the local file to attach
        force_add: proceed even when warnings would normally block (filename
                   match, fragment suspicion, annotations present). New
                   attachment is added alongside; existing attachments are
                   never modified or deleted.
        force_upload: if attachment_simple returns 'unchanged' and verification
                      fails, mutate the file's md5 (append a single null byte
                      to a copy in /tmp) and retry. Useful when Zotero's
                      server-side dedup is preventing actual upload.
        skip_annotated: skip silently if any existing attachment has
                        annotations (default: block + report)
        dry_run: run all checks; report decisions; do NOT call attachment_simple
        fragment_threshold: existing attachment <70% of local file size = suspect
        verify_timeout: seconds to poll fulltext_item after upload
        verbose: print every check and decision

    Returns:
        dict with keys:
            status: 'attached' | 'skipped_duplicate' | 'blocked_annotations' |
                    'blocked_warning' | 'verified' | 'unverified' |
                    'aborted_dry_run' | 'error'
            message: human-readable summary
            decisions: list of (label, key, reason) for each existing attachment
            attachment_key: new attachment key if created
            verification: 'verified' | 'unverified' | 'skipped' | 'na'
    """
    file_path = str(Path(file_path).expanduser().resolve())
    if not os.path.isfile(file_path):
        return {
            'status': 'error',
            'message': f'File not found: {file_path}',
            'decisions': [],
            'attachment_key': None,
            'verification': 'na',
        }

    # 1. Compute local file properties
    local_md5 = compute_md5(file_path)
    local_size = os.path.getsize(file_path)
    local_filename = os.path.basename(file_path)

    if verbose:
        print(f"[local]  {local_filename} ({local_size} bytes, md5={local_md5})")
        print(f"[parent] {parent_key}")

    # 2. Inspect existing attachments on the parent
    try:
        children = zot.children(parent_key)
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Could not fetch parent children: {e}',
            'decisions': [],
            'attachment_key': None,
            'verification': 'na',
        }

    attachments = [c for c in children
                   if c.get('data', {}).get('itemType') == 'attachment']

    if verbose:
        print(f"[parent] {len(attachments)} existing attachment(s)")

    decisions = []
    for att in attachments:
        decision = _classify_existing_attachment(
            zot, att, local_md5, local_size, local_filename, fragment_threshold)
        decisions.append(decision)
        if verbose:
            print(f"  - [{decision[0]}] {decision[1]}: {decision[2]}")

    has_annotations = any(d[0] == 'ANNOTATED' for d in decisions)
    has_duplicate = any(d[0] == 'DUPLICATE' for d in decisions)
    has_warning = any(d[0] in ('FILENAME_MATCH', 'POSSIBLE_FRAGMENT')
                      for d in decisions)

    # 3. Safety gates
    if has_duplicate and not force_add:
        dup = next(d for d in decisions if d[0] == 'DUPLICATE')
        return {
            'status': 'skipped_duplicate',
            'message': f"Already attached: {dup[2]}",
            'decisions': decisions,
            'attachment_key': dup[1],
            'verification': 'na',
        }

    if has_annotations:
        if skip_annotated:
            return {
                'status': 'blocked_annotations',
                'message': 'Skipped: existing attachment has annotations '
                           '(--skip-annotated set)',
                'decisions': decisions,
                'attachment_key': None,
                'verification': 'na',
            }
        if not force_add:
            return {
                'status': 'blocked_annotations',
                'message': ('Annotated attachment exists; refused for safety. '
                            'Use --force-add to proceed (annotations are never '
                            'modified; new attachment is added alongside).'),
                'decisions': decisions,
                'attachment_key': None,
                'verification': 'na',
            }

    if has_warning and not force_add:
        warning_decisions = [d for d in decisions
                             if d[0] in ('FILENAME_MATCH', 'POSSIBLE_FRAGMENT')]
        return {
            'status': 'blocked_warning',
            'message': ('Possible duplicate or fragment relationship detected; '
                        'refused for safety. Use --force-add to proceed. '
                        f'Warnings: {[d[2] for d in warning_decisions]}'),
            'decisions': decisions,
            'attachment_key': None,
            'verification': 'na',
        }

    # 4. Dry-run exit
    if dry_run:
        return {
            'status': 'aborted_dry_run',
            'message': ('Dry run complete; no upload attempted. Would proceed '
                        'with attachment_simple.'),
            'decisions': decisions,
            'attachment_key': None,
            'verification': 'na',
        }

    # 5. Upload
    if verbose:
        print(f"[upload] calling attachment_simple([{file_path}], {parent_key})")
    try:
        result = zot.attachment_simple([file_path], parent_key)
    except Exception as e:
        return {
            'status': 'error',
            'message': f'attachment_simple raised: {e}',
            'decisions': decisions,
            'attachment_key': None,
            'verification': 'na',
        }

    success_items = result.get('success', [])
    failure_items = result.get('failure', [])
    unchanged_items = result.get('unchanged', [])

    if verbose:
        print(f"[upload] result: success={len(success_items)} "
              f"failure={len(failure_items)} unchanged={len(unchanged_items)}")

    if failure_items:
        return {
            'status': 'error',
            'message': f'attachment_simple reported failure: {failure_items}',
            'decisions': decisions,
            'attachment_key': None,
            'verification': 'na',
        }

    # 6. Identify the new attachment key
    new_key = None
    if success_items:
        new_key = success_items[0].get('key')
    elif unchanged_items:
        new_key = unchanged_items[0].get('key')

    # 7. Verify
    if success_items and not unchanged_items:
        # Pure success path; minimal poll to be safe
        verified = _verify_attachment_accessible(zot, new_key, timeout_seconds=5)
        if verified:
            return {
                'status': 'attached',
                'message': f'Uploaded and verified: {local_filename}',
                'decisions': decisions,
                'attachment_key': new_key,
                'verification': 'verified',
            }
        return {
            'status': 'attached',
            'message': (f'Uploaded {local_filename}; fulltext indexing pending. '
                        'Attachment record exists.'),
            'decisions': decisions,
            'attachment_key': new_key,
            'verification': 'unverified',
        }

    # Unchanged path (server-side dedup) — verify with longer poll
    verified = _verify_attachment_accessible(zot, new_key,
                                             timeout_seconds=verify_timeout)
    if verified:
        return {
            'status': 'verified',
            'message': (f'Server-side dedup hit (md5 already in Zotero storage); '
                        f'attachment linked and verified accessible.'),
            'decisions': decisions,
            'attachment_key': new_key,
            'verification': 'verified',
        }

    # Unchanged + verification failed — the bug case
    if force_upload:
        # Mutate md5 by copying file to /tmp with a single trailing byte appended
        import shutil
        mutated_path = f'/tmp/{local_filename}.attach_force'
        shutil.copy(file_path, mutated_path)
        with open(mutated_path, 'ab') as f:
            f.write(b'\x00')
        if verbose:
            print(f"[force]  retrying with mutated copy at {mutated_path}")
        try:
            result2 = zot.attachment_simple([mutated_path], parent_key)
            success_items2 = result2.get('success', [])
            if success_items2:
                new_key2 = success_items2[0].get('key')
                verified2 = _verify_attachment_accessible(zot, new_key2,
                                                          timeout_seconds=5)
                os.remove(mutated_path)
                return {
                    'status': 'attached',
                    'message': (f'Force-upload succeeded with md5-mutated copy. '
                                f'Original file at {file_path} unchanged.'),
                    'decisions': decisions,
                    'attachment_key': new_key2,
                    'verification': 'verified' if verified2 else 'unverified',
                }
        except Exception as e:
            if os.path.exists(mutated_path):
                os.remove(mutated_path)
            return {
                'status': 'error',
                'message': f'Force-upload failed: {e}',
                'decisions': decisions,
                'attachment_key': new_key,
                'verification': 'unverified',
            }

    return {
        'status': 'unverified',
        'message': (f'Server returned unchanged but verification failed within '
                    f'{verify_timeout}s. Manual drag-drop required, OR retry '
                    f'with --force-upload to bypass server-side dedup. '
                    f'Attachment metadata stub key: {new_key}'),
        'decisions': decisions,
        'attachment_key': new_key,
        'verification': 'unverified',
    }
