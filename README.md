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

## Quick Reference

```bash
# Always use --dry-run first
python zotero_apa7_cleanup.py --dry-run
python zotero_brace_cleanup.py --dry-run
python zotero_organize_article1.py --dry-run --summary

# Validate library
python zotero_validate.py
```

## Configuration

Create `.env` from `.env.example`:
- `ZOTERO_LIBRARY_ID` - Your library ID
- `ZOTERO_API_KEY` - API key with read/write access
- `ZOTERO_LIBRARY_TYPE` - 'group' or 'user'
- `BBT_JSON_PATH` - Path to Better BibTeX export
