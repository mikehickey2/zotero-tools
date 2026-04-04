---
name: debug-zotero
description: Debug issues with Zotero scripts - API errors, incorrect formatting, missing items
---

# Debugging Zotero Scripts

Use this skill when encountering issues with any of the Zotero tools scripts.

## Common Issues

### 1. API Connection Errors

**Symptoms**: `HTTPError`, connection refused, authentication failed

**Debug steps**:
```bash
# Check credentials are set
cat .env | grep ZOTERO

# Test API connection
source venv/bin/activate
python -c "
from zotero_utils import load_credentials
from pyzotero import zotero

lib_id, lib_type, api_key = load_credentials()
print(f'Library: {lib_id} ({lib_type})')

zot = zotero.Zotero(lib_id, lib_type, api_key)
info = zot.key_info()
print(f'Connected: {info}')
"
```

### 2. Incorrect Item Counts

**Symptoms**: Too many items, annotations counted as content

**Debug steps**:
```bash
# Check what item types exist
python -c "
from zotero_utils import load_credentials
from pyzotero import zotero

lib_id, lib_type, api_key = load_credentials()
zot = zotero.Zotero(lib_id, lib_type, api_key)

items = zot.everything(zot.items())
types = {}
for item in items:
    t = item['data'].get('itemType', 'unknown')
    types[t] = types.get(t, 0) + 1

for t, count in sorted(types.items(), key=lambda x: -x[1]):
    print(f'{t}: {count}')
"
```

### 3. Term Not Being Preserved

**Symptoms**: Acronym or proper noun lowercased incorrectly

**Debug steps**:
```bash
# Test if term matches pattern
python -c "
from zotero_apa7_cleanup import matches_protected_pattern, is_protected

term = 'YourTerm'
print(f'Term: {term}')
print(f'Pattern match: {matches_protected_pattern(term)}')
print(f'Is protected: {is_protected(term)}')
"

# Test full sentence case
python -c "
from zotero_apa7_cleanup import to_sentence_case
title = 'Your Test Title Here'
print(f'Input:  {title}')
print(f'Output: {to_sentence_case(title)}')
"
```

### 4. Better BibTeX JSON Issues

**Symptoms**: Auto-tagging not finding items, BBT_JSON_PATH errors

**Debug steps**:
```bash
# Check BBT path
echo $BBT_JSON_PATH
cat .env | grep BBT

# Verify file exists and is valid JSON
python -c "
import json
import os
path = os.environ.get('BBT_JSON_PATH', '')
print(f'Path: {path}')
if path:
    with open(path) as f:
        data = json.load(f)
    print(f'Items in JSON: {len(data.get(\"items\", []))}')
"
```

## Systematic Debugging Process

1. **Read error message carefully** - Often contains the solution
2. **Check recent changes** - `git diff` to see what changed
3. **Isolate the issue** - Test individual functions
4. **Verify credentials/paths** - Most common cause of failures
5. **Run validation** - `python zotero_validate.py`

## When to Escalate

If debugging reveals:
- Architectural issues affecting multiple scripts
- API behavior changes from Zotero
- Pattern detection false positives/negatives

Create an issue or discuss before implementing fixes.