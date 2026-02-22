# Zotero Tools

A Python toolkit for automating Zotero library management, citation formatting, and research organization workflows.

## Features

- **APA7 Title Formatting**: Convert titles to sentence case while preserving acronyms and proper nouns
- **BibTeX Cleanup**: Remove `{{ }}` brace artifacts from Better BibTeX exports and fix common typos
- **Automated Tagging**: Apply tags to items based on citation key patterns using regex matching
- **Tag Migration**: Migrate tags between schemas using JSON mapping files with rollback safety
- **Collection Management**: Create collection hierarchies and move items between collections
- **Library Validation**: Run quality checks on your library for formatting consistency
- **Powerful Search**: Multi-strategy search with keyword, tag, collection, and recency filters
- **Obsidian Integration**: Sync Zotero items with your Obsidian vault for literature notes

## Who Is This For?

Researchers and academics who:
- Use Zotero for reference management
- Need consistent APA7 formatting across their library
- Want to automate literature organization with custom tagging rules
- Integrate Zotero with note-taking tools like Obsidian
- Work with Better BibTeX for LaTeX/BibTeX workflows

## Installation

### Prerequisites

- Python 3.8+
- A Zotero account with API access
- (Optional) Better BibTeX Zotero plugin for auto-tagging features

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/zotero-tools.git
cd zotero-tools

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Zotero credentials (see Configuration below)
```

## Configuration

Create a `.env` file with your Zotero credentials:

```bash
# Your Zotero library ID
# For user libraries: your user ID (found at https://www.zotero.org/settings/keys)
# For group libraries: the group ID (from the group URL)
ZOTERO_LIBRARY_ID=YOUR_LIBRARY_ID

# Library type: 'user' for personal library, 'group' for group libraries
ZOTERO_LIBRARY_TYPE=group

# Your Zotero API key (create at https://www.zotero.org/settings/keys/new)
# Ensure the key has read/write access to the library
ZOTERO_API_KEY=YOUR_API_KEY

# Path to Better BibTeX JSON export file (required for auto-tagging)
BBT_JSON_PATH=/path/to/your/export.json
```

## Scripts Overview

| Script | Purpose | Modifies Library |
|--------|---------|------------------|
| `zotero_apa7_cleanup.py` | Convert titles to APA7 sentence case | Yes |
| `zotero_brace_cleanup.py` | Remove BibTeX braces, fix typos | Yes |
| `zotero_organize.py` | Auto-tag items by citation key patterns | Yes |
| `zotero_tag_migrate.py` | Migrate tags between schemas via JSON mapping | Yes |
| `zotero_collection_migrate.py` | Create collections and move items | Yes |
| `zotero_validate.py` | Validate library formatting | No |
| `zotero_search.py` | Search library, browse collections | No |
| `zotero_multi_search.py` | Multi-strategy search with ranking | No |
| `zotero_set_citekeys.py` | Set custom citation keys (Zotero 8 native field) | Yes |
| `zotero_vault_sync.py` | Sync literature notes to Obsidian | Creates files |

## Usage

### Important: Always Use Dry Run First

All scripts that modify your library support `--dry-run` mode. **Always preview changes before applying them:**

```bash
python zotero_apa7_cleanup.py --dry-run    # Preview what would change
python zotero_apa7_cleanup.py              # Apply changes
```

### APA7 Title Cleanup

Convert titles to APA7 sentence case while preserving acronyms and proper nouns:

```bash
# Preview changes
python zotero_apa7_cleanup.py --dry-run

# Apply to entire library
python zotero_apa7_cleanup.py

# Apply to specific collection only
python zotero_apa7_cleanup.py --collection "Literature Review"
```

### Brace and Typo Cleanup

Remove `{{ }}` artifacts from Better BibTeX and fix common typos:

```bash
python zotero_brace_cleanup.py --dry-run   # Preview
python zotero_brace_cleanup.py             # Apply
```

### Auto-Tagging

Apply tags based on citation key patterns (requires Better BibTeX JSON export):

```bash
# Preview tag assignments
python zotero_organize.py --dry-run

# Show tag breakdown summary
python zotero_organize.py --summary

# Display citation keys for pattern debugging
python zotero_organize.py --show-keys

# Apply tags
python zotero_organize.py
```

### Custom Citation Keys

Set short, readable citation keys for items with unwieldy auto-generated keys (common with grey literature, government reports, and organizational authors):

```bash
# Preview changes
python zotero_set_citekeys.py --dry-run

# Apply changes
python zotero_set_citekeys.py
```

Edit `CITEKEY_MAP` in the script to define Zotero item key → desired citation key mappings:

```python
CITEKEY_MAP = {
    "F7I5EVPU": "oigFAABarriers2014",   # was: departmentoftransportation...
    "E4ZU4ZWE": "gaoSmallUAS2018",       # was: governmentaccountability...
}
```

The script also cleans up legacy `Citation Key:` lines from the Extra field (see Zotero 8 migration notes below).

> **Important:** After running, open Zotero and wait for sync. BBT will re-export `references.bib` on idle. Verify with `grep` before rendering.

### Library Validation

Run quality checks on your library:

```bash
python zotero_validate.py
```

### Search

Search and browse your library:

```bash
# Keyword search
python zotero_search.py --query "machine learning"

# Browse a collection
python zotero_search.py --collection "Methods"

# Recent items (last 7 days)
python zotero_search.py --recent 7

# Filter by tag
python zotero_search.py --tag "#MyTag"

# List all tags or collections
python zotero_search.py --list-tags
python zotero_search.py --list-collections

# Include PDF annotations in search results (excluded by default)
python zotero_search.py --query "LLM" --include-annotations
```

> **Note:** PDF annotations (highlights, comments) are excluded from search results by default. Use `--include-annotations` when you want to search your reading notes.

### Multi-Strategy Search

Combine multiple search strategies with deduplication and relevance ranking:

```bash
# Verbose search with scores
python zotero_multi_search.py --query "aviation safety" -v

# Expand search to include tag matching
python zotero_multi_search.py --query "LLM" --expand-tags

# JSON output for processing
python zotero_multi_search.py --query "prompt" --format json

# Limit results
python zotero_multi_search.py --query "safety" --limit 10
```

### Tag Migration

Migrate tags between schemas using a JSON mapping file. Removes old tags and adds new ones in a single pass, preserving all unmapped tags:

```bash
# Create a migration map (JSON)
cat > migration.json << 'EOF'
{
  "mappings": [
    {"old_tag": "#A1-01a-Prior", "new_tags": ["#Sec-LitReview"]},
    {"old_tag": "#A1-02b-LLM-Methods", "new_tags": ["#Sec-Methods", "#RQ1"]}
  ],
  "delete_patterns": ["#NonDiss-*", "cs\\..*"]
}
EOF

# Preview changes (always do this first)
python zotero_tag_migrate.py --map migration.json --dry-run

# Migrate tags in a specific collection
python zotero_tag_migrate.py --map migration.json --collection "Methods" --dry-run

# Apply with audit log
python zotero_tag_migrate.py --map migration.json --audit-log changes.json

# Delete tags matching a pattern (in addition to map patterns)
python zotero_tag_migrate.py --map migration.json --delete-pattern "#Old-*" --dry-run

# Migrate specific items by key
python zotero_tag_migrate.py --map migration.json --items ABC123 DEF456 --dry-run
```

### Collection Management

Create collection hierarchies and move items between collections with copy-then-remove safety:

```bash
# Create a collection spec (JSON)
cat > collections.json << 'EOF'
[
  {"name": "00-Inbox"},
  {"name": "01-Alerts"},
  {
    "name": "04-Literature-Review",
    "children": [
      {"name": "Prior-Studies"},
      {"name": "LLM-Applications"}
    ]
  }
]
EOF

# Preview collection creation
python zotero_collection_migrate.py --create-collections collections.json --dry-run

# Create collections
python zotero_collection_migrate.py --create-collections collections.json

# Create a move mapping (JSON)
cat > moves.json << 'EOF'
[
  {
    "item_key": "ABC12345",
    "from_collection": "OLD_KEY",
    "to_collection": "NEW_KEY",
    "title": "Optional label"
  }
]
EOF

# Preview item moves
python zotero_collection_migrate.py --move-items moves.json --dry-run

# Move items with verification (default)
python zotero_collection_migrate.py --move-items moves.json --verify
```

> **Safety:** Item moves use a copy-then-remove pattern. Items are added to the new collection first, verified to be present, then removed from the old collection. If verification fails, the item stays in the old collection.

### Obsidian Vault Sync

Sync Zotero items to Obsidian literature notes:

```bash
python zotero_vault_sync.py --vault "/path/to/vault" --verbose
```

## Customization

### Protected Terms (APA7 Cleanup)

The APA7 cleanup script uses **pattern-based detection** to automatically preserve:

| Pattern | Examples | Detection Method |
|---------|----------|------------------|
| All-caps acronyms (2+ letters) | UAV, UAVs, GA, LLM, BI | Auto-detected |
| Roman numerals | I, II, III, IV, V, VI, VII, VIII, IX, X | Auto-detected |
| CamelCase product names | YouTube, iPhone, macOS, PowerBI | Auto-detected |
| Software/geographic names | Stata, Power, Auckland, Zealand | `PROTECTED_TERMS` list |
| Multi-word phrases | Monte Carlo, Part 107 | `PROTECTED_PHRASES` list |

**Most acronyms are detected automatically.** Only add terms to `PROTECTED_TERMS` for edge cases that patterns can't catch (e.g., single-word product names like `Stata`):

```python
PROTECTED_TERMS = {
    'Stata', 'Power', 'Excel',  # Software names
    'Auckland', 'Zealand',       # Geographic terms
}
```

For multi-word phrases, edit `PROTECTED_PHRASES`:

```python
PROTECTED_PHRASES = [
    'Monte Carlo', 'Part 107',  # Add your phrases
]
```

### Tag Patterns (Auto-Tagging)

Tag patterns in `zotero_organize.py` use regex matching against Better BibTeX citation keys:

```python
TAG_MAPPING = {
    r'^smith.*(methodology|methods).*': '#Methods',
    r'^jones.*(results|findings).*': '#Results',
}
```

See `zotero_tag_patterns.py` for a complete example of tag pattern configuration.

## Architecture

### Design Patterns

- **Dry Run Safety**: All write operations support `--dry-run` mode
- **Rate Limiting**: API calls include delays (0.5-1.0s) to respect Zotero rate limits
- **Pattern-Based Term Detection**: Automatically preserves acronyms, Roman numerals, and CamelCase without manual configuration
- **Protected Terms**: Configurable lists for edge cases that patterns can't catch
- **Regex Tag Mapping**: Flexible pattern matching for automated tagging
- **JSON-Driven Migration**: Externalized tag mappings and collection specs for version control and review
- **Copy-Then-Remove Safety**: Item collection moves verify placement before removing from source
- **Content Item Filtering**: Automatically excludes attachments, notes, and PDF annotations from item counts (annotations can be included via `--include-annotations` flag in search)

### Rate Limiting

Scripts include built-in delays to avoid hitting Zotero API rate limits:
- APA7 cleanup: 0.5s between updates
- Brace cleanup: 0.5s between updates
- Auto-tagging: 1.0s between updates
- Tag migration: 1.0s between updates (configurable via `--rate-limit`)
- Collection migration: 0.5s between operations

## Zotero 8 and Better BibTeX: Citation Key Changes

Zotero 8 introduced a **native citation key field** on items, replacing Better BibTeX's proprietary storage. This is a breaking change that affects how custom citation keys are set and read.

### What Changed

| Aspect | Zotero 7 + BBT | Zotero 8 + BBT |
|--------|----------------|-----------------|
| Key storage | BBT internal database | Zotero native `citationKey` field |
| Custom key method | Add `Citation Key: mykey` to Extra field | Set the Citation Key field in item info pane (or `citationKey` via API) |
| Pinning | Explicit pin/unpin distinction | All keys are always "pinned" |
| Sync | BBT-only (local) | Syncs natively through Zotero |
| UI location | Top of item pane | Middle of item pane (may require scrolling) |

### Migration

When you upgrade to Zotero 8, BBT will migrate existing keys from its internal storage to the native field. However:

- If you set custom keys via `Citation Key:` in the Extra field **after** migration, Zotero 8 ignores them. BBT reads from the native field, not Extra.
- The `zotero_set_citekeys.py` script handles this correctly by setting `item['data']['citationKey']` directly via the Zotero API and cleaning up stale Extra field entries.

### How to Verify

Check which field BBT is using for a specific item:

```python
from pyzotero import zotero
zot = zotero.Zotero(library_id, library_type, api_key)
item = zot.item('YOUR_ITEM_KEY')
print(f"Native field: {item['data'].get('citationKey', '')}")
print(f"Extra field: {item['data'].get('extra', '')}")
```

If the native `citationKey` field has the old auto-generated key and Extra has your custom key, the custom key is being ignored. Run `zotero_set_citekeys.py` to fix this.

### References

- [Citation Keys :: Better BibTeX for Zotero](https://retorque.re/zotero-better-bibtex/citing/) — BBT citation key documentation
- [Zotero Citation Key Generation - Zotero Forums](https://forums.zotero.org/discussion/129826/zotero-citation-key-generation) — Zotero 8 native citation key field discussion
- [Citation Key Field Missing from Info Pane - Zotero Forums](https://forums.zotero.org/discussion/129821/citation-key-field-missing-from-the-info-pane) — UI changes in Zotero 8
- [BetterBibTeX Citation Key via Server API - Zotero Forums](https://forums.zotero.org/discussion/82437/betterbibtex-citation-key-when-accessing-group-library-via-server-api-pyzotero) — API access patterns for citation keys

### Impact on Workflows

- **Auto-export (`references.bib`):** BBT uses the native `citationKey` field for export. If your custom keys are only in Extra, the bib file will contain the old auto-generated keys.
- **Quarto/Pandoc rendering:** Citation keys in your `.qmd` files must match what's in the exported `.bib`. A mismatch means unresolved references.
- **Obsidian Citations plugin:** Same dependency on the exported bib file.

## Troubleshooting

### API Connection Issues

1. Verify your `.env` file has correct credentials
2. Ensure your API key has read/write permissions
3. Check that `ZOTERO_LIBRARY_TYPE` matches your library (user vs group)

### Better BibTeX JSON Not Found

1. Install the Better BibTeX plugin in Zotero
2. Export your library as Better BibTeX JSON
3. Set `BBT_JSON_PATH` in your `.env` file to the export location

### Changes Not Appearing in Zotero

1. Wait a few moments for sync to complete
2. Click the sync button in Zotero desktop
3. Check the script output for any error messages

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [pyzotero](https://github.com/urschrei/pyzotero) - Python wrapper for the Zotero API
- [Better BibTeX](https://retorque.re/zotero-better-bibtex/) - Citation key generation for Zotero
