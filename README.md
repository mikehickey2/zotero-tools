# Zotero Tools

Automation scripts for managing Zotero citations in dissertation research.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install pyzotero python-dotenv
cp .env.example .env  # Edit with your credentials
```

## Scripts

| Script | Purpose |
|--------|---------|
| `zotero_apa7_cleanup.py` | APA7 sentence case formatting |
| `zotero_brace_cleanup.py` | Remove BibTeX braces, fix typos |
| `zotero_organize_article1.py` | Auto-tag by citation key patterns |
| `zotero_validate.py` | Validate library formatting |
| `zotero_search.py` | Search library, browse collections, recent items |
| `zotero_multi_search.py` | Multi-strategy search with dedup & ranking |
| `zotero_vault_sync.py` | Sync literature notes to Obsidian vault |

## Quick Reference

```bash
# Always use --dry-run first for write operations
python zotero_apa7_cleanup.py --dry-run
python zotero_brace_cleanup.py --dry-run
python zotero_organize_article1.py --dry-run --summary

# Validate library
python zotero_validate.py

# Search & browse (read-only)
python zotero_search.py --query "LLM"
python zotero_search.py --recent 7
python zotero_search.py --collection "Methods"
python zotero_search.py --list-tags

# Multi-strategy search (read-only)
python zotero_multi_search.py --query "aviation safety" -v
python zotero_multi_search.py --query "ASRS" --expand-tags

# Vault sync
python zotero_vault_sync.py --vault "/path/to/vault" --verbose
```

## Configuration

Create `.env` from `.env.example`:
- `ZOTERO_LIBRARY_ID` - Your library ID
- `ZOTERO_API_KEY` - API key with read/write access
- `ZOTERO_LIBRARY_TYPE` - 'group' or 'user'
- `BBT_JSON_PATH` - Path to Better BibTeX export
