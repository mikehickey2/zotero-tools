---
name: add-term
description: Add new protected terms or phrases to the APA7 cleanup script
---

# Adding Protected Terms

Use this skill when you find a term that should be preserved during APA7 sentence case conversion.

## Before Adding: Check if Pattern Handles It

The script automatically detects:
- **All-caps acronyms (2+ letters)**: UAV, LLM, GA, BI, NLP
- **Roman numerals**: I, II, III, IV, V, VI, VII, VIII, IX, X
- **CamelCase**: YouTube, iPhone, macOS, PowerBI

**Only add to PROTECTED_TERMS if patterns don't catch it.**

## Adding a Single Word Term

Edit `zotero_apa7_cleanup.py` and add to the appropriate section of `PROTECTED_TERMS`:

```python
PROTECTED_TERMS: Set[str] = {
    # ... existing terms ...

    # Add your term to the appropriate category:
    # - Aviation acronyms
    # - Technical/ML acronyms
    # - Model names
    # - Proper nouns - systems/methods
    # - Proper nouns - organizations
    # - Software/product names
    # - Proper nouns - geographic
    # - Month names
    # - Regulatory terms

    'YourNewTerm',  # Add with brief comment if needed
}
```

## Adding a Multi-Word Phrase

Edit `PROTECTED_PHRASES` list:

```python
PROTECTED_PHRASES = [
    # ... existing phrases ...
    'Your New Phrase',
]
```

## Testing the Change

```bash
source venv/bin/activate

# Test with a sample title
python -c "
from zotero_apa7_cleanup import to_sentence_case
test = 'Analysis of YourNewTerm in Aviation'
print(f'Input:  {test}')
print(f'Output: {to_sentence_case(test)}')
"

# Run dry-run to verify no regressions
python zotero_apa7_cleanup.py --dry-run
```

## Common Categories

| Category | Examples | When to Use |
|----------|----------|-------------|
| Software names | Stata, Power, Excel | Single-word product names not CamelCase |
| Geographic | Auckland, Zealand | City/region names |
| Organizations | MITRE, Purdue | Institution names |
| Methods | Loess, Bayesian | Statistical/research methods |