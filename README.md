# Zotero Tools

A Python toolkit for automating Zotero library management, citation formatting, and research organization workflows.

## Features

- **APA7 Title Formatting**: Convert titles to sentence case while preserving acronyms and proper nouns
- **BibTeX Cleanup**: Remove `{{ }}` brace artifacts from Better BibTeX exports and fix common typos
- **Automated Tagging**: Apply tags to items based on citation key patterns using regex matching
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
| `zotero_validate.py` | Validate library formatting | No |
| `zotero_search.py` | Search library, browse collections | No |
| `zotero_multi_search.py` | Multi-strategy search with ranking | No |
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

### Obsidian Vault Sync

Sync Zotero items to Obsidian literature notes:

```bash
python zotero_vault_sync.py --vault "/path/to/vault" --verbose
```

## Customization

### Protected Terms (APA7 Cleanup)

The APA7 cleanup script preserves certain acronyms and terms. To customize for your research domain, edit the `PROTECTED_TERMS` set in `zotero_apa7_cleanup.py`:

```python
PROTECTED_TERMS = {
    'FAA', 'NASA', 'LLM', 'BERT',  # Add your acronyms
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

See `supplementary_tag_mapping.py` for a complete example of tag pattern configuration.

## Architecture

### Design Patterns

- **Dry Run Safety**: All write operations support `--dry-run` mode
- **Rate Limiting**: API calls include delays (0.5-1.0s) to respect Zotero rate limits
- **Protected Terms**: Configurable lists of terms preserved during case conversion
- **Regex Tag Mapping**: Flexible pattern matching for automated tagging
- **Content Item Filtering**: Automatically excludes attachments, notes, and PDF annotations from item counts (annotations can be included via `--include-annotations` flag in search)

### Rate Limiting

Scripts include built-in delays to avoid hitting Zotero API rate limits:
- APA7 cleanup: 0.5s between updates
- Brace cleanup: 0.5s between updates
- Auto-tagging: 1.0s between updates

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
