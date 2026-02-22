---
name: orient
description: Build project context at session start - reviews docs, Python scripts, environment health, git state, and available tools
allowed-tools: Bash(git:*), Read, Glob
---

# Orient

Build comprehensive project context for the zotero-tools project.

Run this command at the start of each Claude Code session to establish context.

## Step 1: Load Project Documentation

@CLAUDE.md
@README.md

Read `CONTRIBUTING.md` only if this session involves creating commits or pull requests.

## Step 2: Review Python Scripts

### Known Scripts

**Formatting:**
| Script | Purpose |
|--------|---------|
| `zotero_apa7_cleanup.py` | Convert titles to APA7 sentence case with protected terms |
| `zotero_brace_cleanup.py` | Remove `{{ }}` BibTeX artifacts and fix common typos |

**Organization:**
| Script | Purpose |
|--------|---------|
| `zotero_organize.py` | Auto-tag items by citation key regex patterns |
| `zotero_tag_migrate.py` | Migrate tags between schemas via JSON mapping |
| `zotero_collection_migrate.py` | Create collection hierarchies and move items |

**Search:**
| Script | Purpose |
|--------|---------|
| `zotero_search.py` | Keyword, collection, tag, and recency search |
| `zotero_multi_search.py` | Multi-strategy search with dedup and ranking |

**Validation:**
| Script | Purpose |
|--------|---------|
| `zotero_validate.py` | Library quality and formatting checks |
| `zotero_dedup.py` | Duplicate detection by title, DOI, or report number |

**Import / Export:**
| Script | Purpose |
|--------|---------|
| `zotero_add_item.py` | Create single items (e.g., from NTSB CAROL data) |
| `zotero_import_items.py` | Batch import items from JSON |
| `zotero_set_citekeys.py` | Set custom BBT citation keys via Extra field |

**Integration:**
| Script | Purpose |
|--------|---------|
| `zotero_vault_sync.py` | Sync Zotero items to Obsidian literature notes |

**Shared / Reference:**
| Script | Purpose |
|--------|---------|
| `zotero_utils.py` | Shared credential loading (`load_credentials()`) |
| `zotero_tag_patterns.py` | Reference for all tag regex patterns |
| `zotero_inbox_fix.py` | One-time metadata corrections for inbox items |

### Discover New Scripts

Use Glob to find all `*.py` files in the project root directory. Compare results against the known scripts listed above. If any scripts are found that are NOT in the known list, flag them as:

> **New script detected**: `[filename]` — read its docstring (first 15 lines) to understand its purpose and report it in the summary.

This keeps the orient current as new tools are added to the project.

## Step 3: Environment Health Check

Verify the Python environment is ready. Check for the existence of each item and report as PASS or WARN:

1. **Virtual environment**: Does `venv/` directory exist in the project root?
2. **Credentials**: Does `.env` file exist in the project root? (Required for all API operations)
3. **Dependencies**: Does `requirements.txt` exist? (Core deps: pyzotero, python-dotenv)
4. **BBT JSON path**: Is `BBT_JSON_PATH` referenced in `.env.example`? (Required for auto-tagging and citation key scripts)

**IMPORTANT**: Do NOT read `.env` contents — credentials must stay private. Only check for the file's existence.

## Step 4: Git Status and History

Current branch:
!`git branch --show-current`

Last 8 commits:
!`git log -8 --oneline`

Uncommitted changes:
!`git status --short`

## Step 5: Critical Rules and Available Tools

Before generating the summary, confirm awareness of these project-specific requirements.

### Non-Negotiable Rules

1. **NEVER fabricate academic identifiers** — No invented DOIs, ISBNs, PMIDs, arXiv IDs, or URLs. If a lookup returns no results, say "not found" and explain the gap. A fabricated identifier imported into Zotero corrupts the research record.
2. **`--dry-run` before all write operations** — Every script that modifies the Zotero library supports `--dry-run`. Always preview changes first.
3. **Rate limiting on API writes** — 0.5s delay (APA7, brace cleanup, collection migrate), 1.0s delay (organize, tag migrate). Never remove or reduce these delays.
4. **Content item filtering** — Exclude `attachment`, `note`, and `annotation` itemTypes from item counts. PDF annotations are Zotero's highlight/comment objects, not citable items.
5. **Try-catch requires approval** — Do not add exception handling without explicit request. Let errors propagate and fail loudly.
6. **No unrequested features** — Do not refactor, abstract, add docstrings, or introduce features that were not asked for.

### Key Design Patterns

- **Protected terms system** (`zotero_apa7_cleanup.py`): `matches_protected_pattern()` auto-detects acronyms (2+ caps), Roman numerals, CamelCase. `PROTECTED_TERMS` set and `PROTECTED_PHRASES` list handle edge cases. `TYPO_CORRECTIONS` dict fixes known misspellings.
- **Regex tag mapping** (`zotero_organize.py`): `TAG_MAPPING` dict with 60+ patterns matched against Better BibTeX citation keys. Tags use `#A1-*` (dissertation) and `#NonDiss-*` (non-dissertation) prefixes.
- **Shared utilities** (`zotero_utils.py`): All scripts use `load_credentials()` for API connection. Credentials come from `.env` via python-dotenv.
- **Copy-then-remove safety** (`zotero_collection_migrate.py`): Item moves verify placement in new collection before removing from old.

### Coding Standards

- Python 3.10+ with type hints, argparse, pathlib, python-dotenv
- Small functions (< 80 lines), small files (< 300 lines)
- Single Responsibility Principle — one function, one job
- Return early to reduce nesting
- Names reveal intent; comments explain *why*, not *what*
- Explicit imports only — no meta-packages
- Validate inputs early; meaningful error messages
- Never hardcode secrets — environment variables only

### Available Custom Skills

| Skill | Command | When to Use |
|-------|---------|-------------|
| validate | `/validate` | Run full validation suite (validate.py, APA7 dry-run, brace dry-run) |
| cleanup | `/cleanup` | Complete cleanup workflow: dry-run → review → apply → validate |
| add-term | `/add-term` | Add protected terms or phrases to APA7 script |
| debug-zotero | `/debug-zotero` | Debug API errors, incorrect counts, term preservation issues |

### MCP Tools Available

- **Zotero MCP**: Use for literature searches, metadata retrieval, annotations, fulltext access. Prefer this over web search for literature already in the library. Read/search operations are pre-approved.
- **Context7 MCP**: Auto-invoked for library/API documentation needs. Use for pyzotero docs, Python standard library references, etc.

## Step 6: Generate Summary Report

Provide a structured summary with these sections:

### Project State
- Total Python scripts found and their categories
- Any new/unrecognized scripts detected (not in the known list)
- Current branch and recent git activity

### Environment Status

| Check | Status |
|-------|--------|
| `venv/` directory | PASS / WARN |
| `.env` file | PASS / WARN |
| `requirements.txt` | PASS / WARN |
| BBT JSON path configured | PASS / WARN / N/A |

### Blocking Issues

List anything preventing normal operation:
- Missing `.env` file (no API access possible)
- Missing `venv/` directory (dependencies not installed)
- Uncommitted changes that need attention
- Any merge conflicts or diverged branches

### Ready for Work

Confirm understanding of:
- Non-negotiable rules from Step 5 (especially: no fabricated identifiers, --dry-run first)
- Available custom skills (`/validate`, `/cleanup`, `/add-term`, `/debug-zotero`)
- Key design patterns (protected terms, tag mapping, content filtering)
- MCP tools available for this session
