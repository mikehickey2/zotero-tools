---
name: cleanup
description: Guide through the Zotero library cleanup workflow - dry-run, review, apply, validate
---

# Zotero Library Cleanup Workflow

Use this skill when performing library maintenance or after adding new items.

## Workflow Steps

### Step 1: Activate Environment
```bash
source venv/bin/activate
```

### Step 2: Brace Cleanup (if using Better BibTeX)
```bash
# Preview
python zotero_brace_cleanup.py --dry-run

# If changes needed, apply
python zotero_brace_cleanup.py
```

### Step 3: APA7 Title Formatting
```bash
# Preview changes
python zotero_apa7_cleanup.py --dry-run

# Review the output carefully:
# - Check that acronyms are preserved (UAV, LLM, FAA)
# - Check that proper nouns are preserved (Stata, YouTube)
# - Check that Roman numerals are preserved (Part I, Chapter III)

# If changes look correct, apply
python zotero_apa7_cleanup.py
```

### Step 4: Auto-Tagging (if using Better BibTeX)
```bash
# Preview tag assignments
python zotero_organize.py --dry-run --summary

# If tags look correct, apply
python zotero_organize.py
```

### Step 5: Validation
```bash
python zotero_validate.py
```

## Important Notes

- **Always run dry-run first** - Review changes before applying
- **Rate limiting** - Scripts include delays to respect Zotero API limits
- **Sync after changes** - Click sync in Zotero desktop to see updates

## If Something Goes Wrong

1. Check the error message carefully
2. Verify `.env` credentials are correct
3. Check Zotero API key has read/write permissions
4. Review recent commits for any breaking changes