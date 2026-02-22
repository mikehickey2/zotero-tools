# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dissertation research organization toolkit for managing Zotero citations focused on aviation/UAS safety research. Uses the Zotero API and Better BibTeX exports to automate title formatting and intelligent tagging.

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

# Vault sync
python zotero_vault_sync.py --vault "/path/to/vault" --verbose
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
| `zotero_vault_sync.py` | Sync literature notes to Obsidian vault |
| `zotero_tag_patterns.py` | Reference for all tag regex patterns |

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

## Configuration

Credentials via `.env` file (see `.env.example`):
- `ZOTERO_LIBRARY_ID`: Group or user library ID
- `ZOTERO_LIBRARY_TYPE`: 'group' or 'user'
- `ZOTERO_API_KEY`: API key with read/write access
- `BBT_JSON_PATH`: Path to Better BibTeX JSON export

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
