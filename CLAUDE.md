# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Research organization toolkit for managing Zotero citations. Primary use: dissertation research (aviation/UAS safety). Also used for comp exam projects. Uses the Zotero API and Better BibTeX exports to automate title formatting, metadata cleanup, and intelligent tagging.

## Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install pyzotero python-dotenv
```

## Commands

```bash
# Always activate venv first
source venv/bin/activate

# APA7 title cleanup
python zotero_apa7_cleanup.py --dry-run           # Preview changes
python zotero_apa7_cleanup.py                     # Apply changes
python zotero_apa7_cleanup.py --collection "Name" # Target specific collection

# Brace/typo cleanup
python zotero_brace_cleanup.py --dry-run          # Preview brace removal & typo fixes
python zotero_brace_cleanup.py                    # Apply changes

# Auto-tagging based on citation keys
python zotero_organize.py --dry-run      # Preview tag assignments
python zotero_organize.py --summary      # Show tag breakdown
python zotero_organize.py --show-keys    # Display citation keys
python zotero_organize.py                # Apply tags

# Validation
python zotero_validate.py                         # Run all validation checks

# Search
python zotero_search.py --query "LLM"             # Keyword search
python zotero_search.py --collection "Methods"    # Browse collection
python zotero_search.py --recent 7                # Recent items (last 7 days)
python zotero_search.py --tag "#A1-02a-LLM"       # Filter by tag
python zotero_search.py --list-tags               # Show all tags
python zotero_search.py --list-collections        # Show all collections
python zotero_search.py --query "LLM" --include-annotations  # Include PDF highlights

# Multi-strategy search (combines keyword + tag, deduplicates, ranks)
python zotero_multi_search.py --query "aviation safety" -v    # Verbose with scores
python zotero_multi_search.py --query "ASRS" --expand-tags    # Include tag matching
python zotero_multi_search.py --query "LLM" --format json     # JSON output
python zotero_multi_search.py --query "prompt" --limit 10     # Limit results

# Tag management (direct API, more reliable than MCP batch)
python zotero_set_tags.py --add "#Sec-LitReview" "#RQ-General" --items KEY1 KEY2 --dry-run
python zotero_set_tags.py --add "#Sec-LitReview" "#RQ-General" --items KEY1 KEY2 --verify
python zotero_set_tags.py --remove "#Status-Unread" --items KEY1

# Vault sync
python zotero_vault_sync.py --vault "/path/to/vault" --verbose

# File attachment with safety + verification (handles attachment_simple bug)
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --dry-run
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --verbose
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --force-add
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --force-upload
python zotero_attach_with_verify.py --batch attachments.json
```

## Architecture

### Scripts

| Script | Purpose |
|--------|---------|
| `zotero_apa7_cleanup.py` | Convert titles to APA7 sentence case |
| `zotero_brace_cleanup.py` | Remove `{{ }}` artifacts, fix typos |
| `zotero_organize.py` | Auto-tag items by citation key patterns |
| `zotero_validate.py` | Validate library formatting |
| `zotero_search.py` | Search library, browse collections, recent items |
| `zotero_multi_search.py` | Multi-strategy search with dedup & ranking |
| `zotero_import_items.py` | Import new items from JSON (any item type, APA7 metadata) |
| `zotero_govinfo_import.py` | Fetch government publications (GAO, CRS, Congressional) via GovInfo API |
| `zotero_vault_sync.py` | Sync literature notes to Obsidian vault |
| `zotero_tag_patterns.py` | Reference for all tag regex patterns |
| `zotero_set_tags.py` | Add/remove tags on specific items by key |
| `zotero_set_citekeys.py` | Audit, abbreviate, and set citation keys (--audit, --fix, --set) |
| `zotero_attach_with_verify.py` | Attach files to items with dedup safety + post-upload verification (workaround for `attachment_simple` silent-failure bug) |
| `zotero_edit_note.py` | Edit existing Zotero notes via batched patches with annotation-span safeguards |
| `zotero_delete_annotation_block.py` | Delete annotation reference blocks safely (companion to `zotero_edit_note.py`) |
| `zotero_add_item.py` | Create Zotero items from NTSB CAROL JSON data |
| `zotero_govinfo_import.py` | Search GovInfo API and produce Zotero-ready JSON (GAO, CRS, Congressional) |
| `zotero_copy_items.py` | Copy items between libraries (metadata only) |
| `zotero_dedup.py` | Find and merge duplicates by DOI or normalized title+author+year |
| `zotero_inbox_fix.py` | Batch APA 7 metadata corrections for inbox items. Supports `_creators` (creator list replacement) and `_itemType` (full itemType conversion with automatic invalid-field cleanup, per the item-type-change pattern documented below). |
| `zotero_tag_migrate.py` | Migrate tags between schemas via JSON map |
| `zotero_collection_migrate.py` | Create collection hierarchies; move items with copy-then-remove safety |
| `zotero_utils.py` | Shared module — `load_credentials()`, `compute_md5()`, `attach_with_safety()` |

### Key Design Patterns

**Protected Terms System** (`zotero_apa7_cleanup.py`):
- `matches_protected_pattern()`: Auto-detects acronyms (2+ caps), Roman numerals, CamelCase
- `PROTECTED_TERMS` set: Edge cases patterns miss (Stata, Power, Auckland, etc.)
- `PROTECTED_PHRASES` list: Multi-word phrases (Part 107, Monte Carlo, etc.)
- `TYPO_CORRECTIONS` dict: Known typos auto-corrected

**Typo Fixes** (`zotero_brace_cleanup.py`):
- `TYPO_FIXES` dict: Flordia→Florida, Inititative→Initiative
- Checks: title, shortTitle, institution, publicationTitle fields

**Regex Tag Mapping** (`zotero_organize.py`):
- `TAG_MAPPING` dict: 60+ regex patterns matched against citation keys
- Pattern format: `r'^authorname.*(keyword1|keyword2).*'`
- Tags: `#A1-*` (dissertation) and `#NonDiss-*` (non-dissertation)

**Naming Convention** (all scripts):
- Pattern: `zotero_[qualifier_]<action_or_role>.py`
- All scripts must start with `zotero_` prefix
- Action verbs for executables, nouns for modules
- See CONTRIBUTING.md for full specification

**Content Item Filtering** (all scripts):
- Excludes `attachment`, `note`, and `annotation` item types from counts
- PDF annotations are Zotero's highlight/comment objects (not citable items)
- Use `--include-annotations` flag in `zotero_search.py` to search highlights

### Rate Limiting
- `zotero_apa7_cleanup.py`: 0.5s delay
- `zotero_brace_cleanup.py`: 0.5s delay
- `zotero_organize.py`: 1.0s delay
- `zotero_set_tags.py`: 0.5s delay

## Zotero 8 + BBT 8+ Citation Keys (IMPORTANT)

**Verified from BBT v8.0.0 changelog (GitHub):** Zotero 8 introduced a native `citationKey` field on all item types. BBT migrated its key storage to this field — BBT's old separate storage is gone. BBT still generates keys via formula patterns and "fills" them into Zotero's native field (`fillKeyAfter` pref, default 2 seconds). The old "pinning" concept was replaced by "filling" — keys are always persistent in the native field.

**For Claude:** Keys appear within seconds of item creation via pyzotero API. Do NOT say "waiting for BBT sync" — the fill is nearly immediate. BBT's role is now key generation + `.bib` export, not key storage.

**Note:** `zotero_search.py` extracts citation keys from the `extra` field (`Citation Key:` text pattern) as a legacy fallback. Zotero 8 stores keys in the native `citationKey` field, which pyzotero exposes via `item['data'].get('citationKey')`. The `extra` field extraction should be updated to check `citationKey` first.

## Import Workflow (Adding Items to Library)

**Claude MUST use `zotero_import_items.py` to add items — NEVER tell the user to create items manually.**

1. **Verify identifier** — Run `/identifier-lookup` for DOI/ISBN/PMID before import. If found, user can use Zotero's "Add by Identifier" (faster). For grey literature without identifiers, proceed to step 2.
2. **Create JSON** — Write APA7-compliant metadata to `/tmp/` (sentence-case title, split first/last names, ISO date, institution, place, URL)
3. **Dry-run** — `python zotero_import_items.py --input /tmp/file.json --collection "00-Inbox" --dry-run --verbose`
4. **Import** — Remove `--dry-run`
5. **Tag** — `python zotero_set_tags.py --add "#Sec-X" "#RQ-X" "#Status-Unread" --items ITEMKEY --verify`
6. **Verify** — Confirm via MCP; notify user to attach PDF

**APA7 metadata is mandatory** for all imports: sentence-case titles, proper creator types, ISO dates, institutional place.

## Configuration

Credentials via `.env` file (see `.env.example`):
- `ZOTERO_LIBRARY_ID`: Group or user library ID
- `ZOTERO_LIBRARY_TYPE`: 'group' or 'user'
- `ZOTERO_API_KEY`: API key with read/write access
- `BBT_JSON_PATH`: Path to Better BibTeX JSON export

### Multi-Library Support

The `.env` file defaults to the dissertation library (`uas-sightings`, ID 6042289). To target a different library (e.g., comp exams), override `ZOTERO_LIBRARY_ID` via environment variable. `os.getenv()` checks env vars before `.env`, so the override takes precedence without modifying `.env`.

```bash
# Target comp-exam library (ID 6448487) for any script
ZOTERO_LIBRARY_ID=6448487 python zotero_apa7_cleanup.py --dry-run

# Same pattern works for all scripts
ZOTERO_LIBRARY_ID=6448487 python zotero_brace_cleanup.py --dry-run
ZOTERO_LIBRARY_ID=6448487 python zotero_set_tags.py --add "verified" --items KEY1 KEY2
```

**Known libraries:**

| Library | ID | Purpose |
|---------|-----|---------|
| `uas-sightings` | 6042289 | Dissertation (default in `.env`) |
| `comp-exam` | 6448487 | Comprehensive exams |

**Item type changes via pyzotero:** When changing `itemType` (e.g., webpage → report), you must delete fields that are invalid for the new type before calling `zot.update_item()`. Use `zot.item_template('newType')` to get valid fields, then remove any current fields not in that set. Example pattern:

```python
item = zot.item('ITEMKEY')
template = zot.item_template('report')
valid_fields = set(template.keys())
meta_fields = {'key', 'version', 'dateAdded', 'dateModified', 'relations', 'collections', 'tags'}
for field in set(item['data'].keys()) - valid_fields - meta_fields:
    del item['data'][field]
item['data']['itemType'] = 'report'
# set other fields...
zot.update_item(item)
```

## Comp Exam Research Pipeline

Repeatable template for comp exam source management. Tested on AVIT 521 (ethics exam, Session 29).

### Pipeline Steps

```
1. Source Collection    → Web search, Google Scholar, identify 8-10 sources
2. Identifier Lookup    → Crossref/OpenLibrary API for DOIs and ISBNs
3. Zotero Import        → Batch paste identifiers into "Add by Identifier"
4. Metadata Fixes       → pyzotero for item type changes, missing fields
5. APA 7 Cleanup        → ZOTERO_LIBRARY_ID=6448487 python zotero_apa7_cleanup.py
6. Brace Cleanup        → ZOTERO_LIBRARY_ID=6448487 python zotero_brace_cleanup.py
7. Full-Text Pull       → Zotero local API (localhost:23119) for PDF content
8. Research Briefing    → Executive dossier (landscape → frameworks → profiles → synthesis)
9. Outline              → Claim-evidence-critique structure with source mapping
```

### Research Briefing Template

The briefing document follows this structure for each exam:

```markdown
# [Topic] Research Briefing

## Part 1: [Domain] Landscape (~2-3 pages)
- History, scale, key players, regulatory picture, core debate

## Part 2: The Analytical Frameworks (~2 pages)
- Framework descriptions, why each fits, how they connect/diverge

## Part 3: Source Profiles (~1-1.5 pages each)
For each source:
### [Author(s) (Year)] — "[Title]"
- Journal/Publisher, Authors + affiliations
- Research Gap, Methods, Key Findings, Conclusions
- Relevance to exam, Key extractable claims
- Peer-reviewed status, Citation count

## Part 4: Synthesis (~1-2 pages)
- Agreement/disagreement, convergence, gaps, "so what"
```

### Outline Template

Each exam outline uses claim-evidence-critique per section:

```markdown
## Section (~N words)
**Claim 1:** [assertion]
- **Support:** [source + data]
- **Critique/So what:** [analysis]

**Claim 2:** ...

**Sources:** [assigned sources for this section]
```

## Custom Skills

Project-specific skills are available in `.claude/skills/`:

| Skill | Command | Purpose |
|-------|---------|---------|
| `validate` | `/validate` | Run full validation suite (validate.py, APA7 dry-run, brace dry-run) |
| `cleanup` | `/cleanup` | Guide through complete cleanup workflow with dry-run → apply → validate |
| `add-term` | `/add-term` | Add new protected terms or phrases to APA7 script |
| `debug-zotero` | `/debug-zotero` | Debug API errors, incorrect counts, term preservation issues |

## Recommended Agents

| Agent Type | When to Use |
|------------|-------------|
| **Explore** | Understanding codebase, finding all instances of a pattern (e.g., `itemType` filtering across files) |
| **Plan** | Designing new features or major refactors before implementation |

## Recommended Skills (General)

| Skill | When to Use |
|-------|-------------|
| `superpowers:systematic-debugging` | Any bug, test failure, or unexpected behavior - trace root cause before fixing |
| `superpowers:verification-before-completion` | Before claiming work complete - run validation and tests |
| `superpowers:brainstorming` | Before implementing new features - explore requirements first |

## Known Issues

### pyzotero `attachment_simple` Silent Failure on Server-Side Dedup

`pyzotero.attachment_simple()` classifies upload results as one of `success`, `failure`, or `unchanged`. The `unchanged` classification fires when Zotero's server-side md5 deduplication matches a file already in storage from any user. Per Zotero API docs, this is supposed to auto-link the existing file to the new attachment record — but in practice the link does not always propagate, leaving an empty attachment metadata stub on the parent item. `fulltext_item(attachment_key)` returns 404 on these stubs.

This affects any file commonly uploaded to Zotero by other users — public PDFs from .gov, .mil, official journals, etc.

**Root cause** (verified against pyzotero source [`_upload.py`](https://github.com/urschrei/pyzotero/blob/main/src/pyzotero/_upload.py)): pyzotero correctly trusts the Zotero API's `{"exists": 1}` response and reports `unchanged`. The actual gap is on the Zotero server side, not pyzotero.

**Workaround:** Use `zotero_attach_with_verify.py` for all attachment operations. It calls `attachment_simple`, polls `fulltext_item` after the call to verify the file is actually accessible, and falls back to `--force-upload` (md5-mutation) when the dedup case blocks the upload. It also adds pre-flight safety checks for duplicates, fragments, and annotation protection.

```bash
# Always use the wrapper for attachments
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --verbose

# When server-side dedup is blocking actual upload
python zotero_attach_with_verify.py PARENT_KEY /path/to/file.pdf --force-upload
```

### Zotero MCP `zotero_batch_update_tags` Unreliable

The Zotero MCP server's `zotero_batch_update_tags` tool reports success but silently fails to apply tags. This has been observed across multiple Claude Code sessions. The root cause appears to be the MCP tool's query-based batch approach, which does not guarantee atomic writes to specific items.

**Workaround:** Use `zotero_set_tags.py` for all tag write operations. This script uses direct pyzotero API calls (`zot.item()` → modify → `zot.update_item()`) with optional read-after-write verification (`--verify`). This pattern is deterministic and has never failed.

**Verification pattern:**
```bash
# Always verify after tag writes
python zotero_set_tags.py --add "#Sec-LitReview" --items ITEMKEY --verify
```

## Global Skills Available

Visualization skills are available globally at `~/.claude/skills/`:
- `gemini-visualization` — AI-generated conceptual figures
- `mermaid-visualization` — Precise reproducible diagrams
- `r-visualizations` — Data-driven statistical figures
- `excalidraw-diagrams` — Wireframes, architecture sketches, brainstorming

## Future Enhancements

### Testing
- [ ] Add pytest unit tests for `to_sentence_case()` and `matches_protected_pattern()`
- [ ] Add integration tests that mock the Zotero API
- [ ] Create test fixtures with sample library data

### CI/CD
- [ ] GitHub Actions workflow to run validation on PRs
- [ ] Automated linting with flake8/black
- [ ] Pre-commit hooks for code quality

### Code Quality
- [ ] Centralized `filter_content_items()` helper shared across all scripts
- [ ] Type hints throughout codebase
- [ ] Docstring coverage for all public functions

### Features
- [ ] `--undo` flag to revert last batch of changes
- [ ] Export validation report to markdown/JSON
- [ ] Configuration file for custom protected terms (avoid editing source)
- [ ] Web UI or CLI dashboard for library status

### Documentation
- [ ] API documentation with Sphinx
- [ ] Example notebooks for common workflows
- [ ] Video walkthrough of setup and usage
