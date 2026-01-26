---
name: validate
description: Run the full Zotero library validation suite to check formatting, braces, acronyms, and item counts
---

# Zotero Library Validation

Run this skill to validate the Zotero library for formatting issues.

## Validation Steps

Execute these commands in sequence:

```bash
source venv/bin/activate

# 1. Run full validation checks
python zotero_validate.py

# 2. Check for any remaining APA7 issues
python zotero_apa7_cleanup.py --dry-run

# 3. Check for brace artifacts
python zotero_brace_cleanup.py --dry-run

# 4. Verify vault sync status (if vault path configured)
# python zotero_vault_sync.py --vault "/path/to/vault"
```

## Expected Results

All checks should pass with:
- 0 brace artifacts
- 0 typos detected
- 0 acronym capitalization issues
- 0 items to change in APA7 cleanup

## If Issues Found

1. Review the dry-run output to understand what would change
2. If changes look correct, run without `--dry-run` to apply
3. Re-run validation to confirm fixes

## Reporting

After validation, summarize:
- Total content items checked
- Any issues found
- Recommended actions