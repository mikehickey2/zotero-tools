# Contributing to Zotero Tools

Thank you for your interest in contributing to Zotero Tools! This document provides guidelines for contributing to the project.

## Reporting Issues

When reporting issues, please include:

1. **Python version** (`python --version`)
2. **Operating system** (macOS, Windows, Linux)
3. **Steps to reproduce** the issue
4. **Expected behavior** vs. **actual behavior**
5. **Error messages** (if any)

For API-related issues, please confirm:
- Your `.env` file is properly configured
- Your Zotero API key has read/write permissions

## Pull Request Guidelines

### Before Submitting

1. **Test your changes** with `--dry-run` mode before submitting
2. **Ensure backwards compatibility** - changes should not break existing workflows
3. **Follow existing code style** - match the patterns in existing scripts
4. **Update documentation** if adding new features or flags

### File Naming Convention

All Python scripts follow the pattern: **`zotero_[qualifier_]<action_or_role>.py`**

| Component | Required | Description | Examples |
|-----------|----------|-------------|----------|
| `zotero_` | Yes | Project prefix — all scripts start with this | — |
| `qualifier_` | Optional | Narrows scope when action alone is ambiguous | `apa7_`, `brace_`, `multi_`, `tag_`, `collection_`, `vault_` |
| `<action_or_role>` | Yes | What the script does (verb) or its role (noun) | `cleanup`, `search`, `migrate`, `utils`, `tag_patterns` |

Rules:
- Use snake_case throughout
- Prefer action verbs for executable scripts (`validate`, `search`, `migrate`)
- Use nouns for non-executable modules (`utils`, `tag_patterns`)
- Singular nouns for single-item operations (`add_item`), plural for batch (`import_items`)
- Keep names under 30 characters (excluding `.py`)

### Code Style

- Use descriptive variable names
- Add docstrings to new functions
- Include `--dry-run` support for any write operations
- Implement rate limiting for API calls (0.5-1.0s delay)
- Use `argparse` for CLI arguments with helpful descriptions

### Commit Messages

- Use clear, descriptive commit messages
- Reference issue numbers when applicable (e.g., "Fixes #12")

## Adding Custom Terms or Patterns

### Protected Terms (for APA7 cleanup)

To add protected terms for your research domain, modify the `PROTECTED_TERMS` set in `zotero_apa7_cleanup.py`:

```python
PROTECTED_TERMS = {
    # Existing terms...
    'YOUR_ACRONYM',
    'ANOTHER_TERM',
}
```

For multi-word phrases, add to `PROTECTED_PHRASES`:

```python
PROTECTED_PHRASES = [
    # Existing phrases...
    'Your Multi-Word Phrase',
]
```

### Tag Mappings (for auto-tagging)

Tag patterns in `zotero_organize.py` use regex matching against citation keys:

```python
TAG_MAPPING = {
    r'^pattern.*keyword.*': '#Your-Tag',
}
```

**Tips for patterns:**
- Use `^` to anchor at the start of the citation key
- Use `.*` for flexible matching
- Test with `--dry-run --verbose` before applying

## Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/zotero-tools.git
cd zotero-tools

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure credentials
cp .env.example .env
# Edit .env with your Zotero credentials
```

## Questions?

Feel free to open an issue for questions or discussions about potential contributions.
