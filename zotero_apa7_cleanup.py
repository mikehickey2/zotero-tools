#!/usr/bin/env python3
"""
zotero_apa7_cleanup.py

Transforms Zotero item titles to APA7 sentence case while preserving
acronyms, proper nouns, and fixing known typos.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_apa7_cleanup.py --dry-run     # Preview changes
    python zotero_apa7_cleanup.py               # Apply changes
"""

import argparse
import re
import sys
import time
from typing import Set

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

# =============================================================================
# PROTECTED TERMS - Do not lowercase these
# =============================================================================
PROTECTED_TERMS: Set[str] = {
    # Aviation acronyms
    'FAA', 'NAS', 'ASRS', 'UAS', 'sUAS', 'UAV', 'RPAS', 'UTM', 'LAANC',
    'AGL', 'MSL', 'ATC', 'ARTCC', 'TRACON', 'ATCT', 'NMAC', 'CFR', 'VMC',
    'IMC', 'VFR', 'IFR', 'NM', 'ICAO', 'EASA', 'NTSB', 'HFACS', 'UASFMs',
    'SORA', 'ATM', 'BVLOS', 'C-UAS', 'cUAS', 'DAA', 'TCAS', 'ADS-B',
    '7110.65W',  # FAA JO version designator

    # Technical/ML acronyms
    'LLM', 'LLMs', 'NLP', 'NER', 'GPT', 'BERT', 'AI', 'ML', 'API', 'JSON',
    'ROC', 'AUC', 'MAE', 'TTR', 'MATTR', 'MTLD', 'PELT', 'STL', 'ARDL',
    'VAR', 'IRF', 'ROUGE', 'KIE', 'APE', 'EDA', 'QLoRA', 'LoRA', 'CoNLL',
    'HD-D', 'vocd-D', 'lda2vec', 'LDA', 'NMF', 'KPI', 'KPIs', 'VGI', 'R',

    # Model names / statistical abbreviations with digits
    'T5', 'GPT-3', 'GPT-4', 'BERT', 'RoBERTa', 'GPT-NER', '3D',
    'AC1', 'AC2', 'F1',

    # Proper nouns - systems/methods
    'SafeAeroBERT', 'AviationGPT', 'ChatGPT', 'Claude', 'Zotero',
    'NASP-T', 'LogSyn', 'LeRAAT', 'LERCause',
    'Loess', 'Monte-Carlo', 'Monte', 'Carlo', 'Jeffreys', 'Poisson',
    'Cohen', 'Gwet', 'Granger', 'Bayesian', 'Boolean', 'Gaussian', 'Markov',
    'Firth', 'Lasso', 'Gordian', 'Johnny', 'Cox',
    # Eponymous statistical tests/measures (possessives handled by is_protected)
    'Mann', 'Kendall', 'Kruskal', 'Wallis', 'Shapiro', 'Wilk',
    'Fleiss', 'Krippendorff', 'Cronbach', 'Bonferroni', 'Tukey',
    'Fisher', 'Friedman', 'Pearson', 'Spearman', 'Wilcoxon', 'Likert', 'Sen',
    'Kaplan', 'Meier', 'Welch', 'Levene', 'Kolmogorov', 'Smirnov',

    # Proper nouns - organizations
    'NASA', 'MITRE', 'IEEE', 'ACM', 'AIAA', 'SAE', 'Routledge', 'Elsevier',
    'Springer', 'Purdue', 'USGS', 'DHS', 'NDAA', 'DoD', 'ProQuest', 'AeroScope',
    'Black', 'Vault', 'Bombardier', 'Canadair', 'Inc',

    # Software/product names (that patterns won't catch)
    'Stata', 'Power', 'Excel', 'SPSS', 'Tableau', 'tscount',

    # Proper nouns - geographic/demonyms
    'United', 'States', 'U.S.', 'US', 'UK', 'France', 'French', 'Greek',
    'Korean', 'Japanese', 'German',
    'Taiwanese', 'National', 'Federal', 'American', 'European', 'Copenhagen',
    'Oslo', 'Florida', 'Russia', 'Russian', 'X',
    'South', 'North', 'East', 'West', 'Auckland', 'Zealand', 'Australia',
    'Australian', 'Canadian', 'China', 'Chinese', 'India', 'Indian',
    'Los', 'Angeles', 'CA', 'Frankfurt',

    # Month names (proper nouns)
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',

    # Regulatory terms
    'Part', 'Remote', 'ID', 'ASSURE',

    # --- Added 2026-07-30 after a dry run proposed corrupting NTSB titles ---
    # Aircraft / UAS product lines and manufacturers
    'DJI', 'Phantom', 'Mavic', 'Inspire', 'Matrice', 'Airbus', 'Boeing',
    'Sikorsky', 'Cessna', 'Piper', 'Bell', 'Robinson', 'Hawk', 'Blackhawk',
    'Zoom',  # "Mavic 2 Zoom" product variant, not the verb
    # Military services and components
    'Army', 'Navy', 'Air', 'Force', 'Marine', 'Corps', 'Guard', 'Coast',
    # US place names appearing in NTSB accident titles
    'Staten', 'Island', 'New', 'York', 'Johnson', 'Valley', 'California',
    'Texas', 'Nevada', 'Arizona', 'Alaska', 'Colorado', 'Virginia',
    'Washington', 'Oregon', 'Utah', 'Georgia', 'Carolina', 'Dakota',
    # Benchmark and evaluation product names
    'Bench', 'Arena', 'Chatbot', 'HumanEval', 'SimpleQA', 'ArenaHard',
    'LiveBench', 'IFEval', 'PhiBench', 'MMLU', 'GPQA', 'DROP', 'MGSM',
}

# Ordinary vocabulary that legitimately lowercases in sentence case. Used ONLY by
# detect_review_risks() to decide whether a Capitalized -> lowercase transform is
# routine or suspicious. Not exhaustive by design: anything missing gets flagged
# for human review rather than silently changed, which is the safe direction.
COMMON_TITLE_WORDS: Set[str] = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'between', 'beyond',
    'but', 'by', 'can', 'do', 'does', 'for', 'from', 'how', 'in', 'into',
    'is', 'it', 'its', 'not', 'of', 'on', 'or', 'the', 'their', 'this',
    'through', 'to', 'toward', 'towards', 'under', 'using', 'via', 'was',
    'were', 'what', 'when', 'where', 'which', 'who', 'why', 'with', 'within',
    'without',
    'analysis', 'analytics', 'application', 'applications', 'approach',
    'approaches', 'assessment', 'automated', 'automation', 'aviation',
    'based', 'capabilities', 'capability', 'case', 'challenges', 'class',
    'classification', 'clinical', 'coding', 'collision', 'comparative',
    'comparison', 'computational', 'concerns', 'construction', 'content',
    'context', 'control', 'critical', 'data', 'dataset', 'decision',
    'deep', 'design', 'detection', 'development', 'differences', 'different',
    'digital', 'discovery', 'document', 'documents', 'domain', 'drone',
    'drones', 'effectiveness', 'efficient', 'empirical', 'engineering',
    'evaluating', 'evaluation', 'evidence', 'experience', 'exploratory',
    'extraction', 'factors', 'field', 'framework', 'future', 'general',
    'generation', 'generative', 'health', 'human', 'identification',
    'impact', 'implementation', 'incident', 'incidents', 'inference',
    'information', 'infrastructure', 'inputs', 'intelligence', 'interaction',
    'judging', 'knowledge', 'language', 'large', 'learning', 'level',
    'literature', 'machine', 'management', 'measurement', 'method',
    'methods', 'methodology', 'model', 'models', 'modeling', 'multi',
    'narrative', 'narratives', 'natural', 'network', 'networks', 'new',
    'operations', 'optimization', 'performance', 'perspective', 'pipeline',
    'practice', 'prediction', 'preliminary', 'processing', 'production',
    'quality', 'quantitative', 'qualitative', 'reasoning', 'reliability',
    'report', 'reports', 'research', 'results', 'retention', 'review',
    'risk', 'rules', 'safety', 'scientific', 'settings', 'small',
    'structured', 'study', 'summarization', 'survey', 'system', 'systems',
    'technical', 'text', 'threats', 'tools', 'training', 'transformer',
    'understanding', 'unmanned', 'validation', 'evolving', 'customized',
    'develop', 'umbrella', 'aircraft', 'helicopter', 'agent', 'agents',
    'agentic', 'offshore', 'drilling', 'coherence', 'care',
    'addressing', 'agreement', 'airspace', 'behavioral', 'causal', 'chains',
    'challenge', 'clinical', 'coefficient', 'events', 'existing', 'extract',
    'handling', 'issues', 'kidney', 'lung', 'mapping', 'messy', 'nominal',
    'pathology', 'plan', 'power', 'radiology', 'resources', 'scales',
    'sciences', 'solutions', 'statistical', 'terminal', 'tumors',
    'uncovering', 'workflows', 'zero', 'shot', 'building', 'schema',
    'validation', 'real', 'world', 'graph', 'ontology', 'grounded',
    'automatic', 'towards', 'efficient', 'optimizing', 'prompt',
}

# Terms that are protected as multi-word phrases
PROTECTED_PHRASES = [
    'Part 107',
    'Remote ID',
    'United States',
    'Monte-Carlo',
    'Monte Carlo',
    'National Airspace System',
    'Human Factors Analysis and Classification System',
    'Federal Aviation Administration',
    'The Black Vault',
    'Aviation Safety Reporting System',
    'CoNLL-2003',
    'X Files',
    'Los Angeles',
    'Bombardier Inc',
    # Added 2026-07-30 (see PROTECTED_TERMS note)
    'DJI Phantom',
    'DJI Mavic',
    'Black Hawk',
    'Staten Island',
    'New York',
    'Johnson Valley',
    'U.S. Army',
    'Chatbot Arena',
    'MT-Bench',
]

TYPO_CORRECTIONS = {
    'Flordia': 'Florida',
    'unmaned': 'unmanned',
    'aircaft': 'aircraft',
    r'\(SORA\)approach': '(SORA) approach',
    r'\(sora\)approach': '(SORA) approach',
}

# Rate limiting
RATE_LIMIT_DELAY = 0.5


def remove_bibtex_braces(text: str) -> str:
    """Remove BetterBibTeX brace protection {{ }} from text."""
    text = re.sub(r'\{\{', '', text)
    text = re.sub(r'\}\}', '', text)
    text = re.sub(r'\{', '', text)
    text = re.sub(r'\}', '', text)
    return text


def fix_typos(text: str) -> str:
    """Fix known typos in text."""
    for wrong, correct in TYPO_CORRECTIONS.items():
        # Check if the pattern is a regex (starts with special chars)
        if wrong.startswith(r'\('):
            text = re.sub(wrong, correct, text, flags=re.IGNORECASE)
        else:
            text = re.sub(rf'\b{wrong}\b', correct, text, flags=re.IGNORECASE)
    return text


def matches_protected_pattern(word: str) -> bool:
    """
    Check if word matches patterns that should be preserved.

    Patterns detected:
    - All-caps acronyms (2+ letters): UAV, UAVs, GA, LLM, BI
    - Roman numerals: I, II, III, IV, V, VI, VII, VIII, IX, X
    - CamelCase product names: YouTube, PowerBI, iPhone
    """
    if not word:
        return False

    # All-caps acronyms (2+ letters, optionally ending in lowercase 's' for plurals)
    # e.g., UAV, UAVs, GA, LLM, NLP, BI
    if re.match(r'^[A-Z]{2,}s?$', word):
        return True

    # Roman numerals (standalone, up to 4 characters to avoid false positives)
    # e.g., I, II, III, IV, V, VI, VII, VIII, IX, X, XI, XII
    if re.match(r'^[IVXLCDM]+$', word) and len(word) <= 4:
        return True

    # Alphanumeric type designators: uppercase letters mixed with digits and no
    # lowercase. Covers aircraft and model designators that the all-caps rule
    # above misses because of the digits.
    # e.g., AS350BA, 60M (from UH-60M), 7110.65W, A320, F1
    # Added 2026-07-30: their absence lowercased "UH-60M" to "UH-60m" and
    # "AS350BA" to "as350ba" in NTSB accident titles.
    if (re.match(r'^[A-Z0-9.\-]+$', word)
            and any(c.isdigit() for c in word)
            and any(c.isupper() for c in word)):
        return True

    # CamelCase / mixed case product names
    # e.g., YouTube, PowerBI, iPhone, macOS
    if re.match(r'^[a-z]+[A-Z]', word):  # starts lowercase, has uppercase (iPhone, macOS)
        return True
    if re.match(r'^[A-Z][a-z]+[A-Z]', word):  # YouTuBe, PowerBI pattern
        return True

    return False


def is_protected(word: str) -> bool:
    """Check if a word should be protected from lowercasing."""
    # Strip punctuation (including parentheses) for comparison
    clean_word = re.sub(r'[^\w\-/.]', '', word)
    # Also try without periods for U.S. vs US matching
    clean_word_no_dots = clean_word.replace('.', '')
    # Strip possessive suffix: "Cohens" -> "Cohen", "Gwets" -> "Gwet"
    clean_word_base = re.sub(r's$', '', clean_word) if clean_word.endswith('s') else clean_word

    # Check pattern-based rules first (acronyms, Roman numerals, CamelCase)
    if matches_protected_pattern(clean_word):
        return True

    # Check exact match in PROTECTED_TERMS (word, without dots, or base form)
    for candidate in (clean_word, clean_word_no_dots, clean_word_base):
        if candidate in PROTECTED_TERMS:
            return True

    # Check case-insensitive match for terms in PROTECTED_TERMS
    for candidate in (clean_word, clean_word_no_dots, clean_word_base):
        if candidate.upper() in PROTECTED_TERMS:
            return True

    return False


def process_compound_word(word: str) -> str:
    """Process hyphenated or slashed compound words, preserving protected parts."""
    # Handle words with hyphens or slashes
    if '-' in word or '/' in word:
        # Split by hyphen or slash, preserving the delimiter
        parts = re.split(r'([-/])', word)
        result_parts = []
        for part in parts:
            if part in ['-', '/']:
                result_parts.append(part)
            elif matches_protected_pattern(part):
                # Pattern match (acronym, Roman numeral, CamelCase) - preserve original
                result_parts.append(part)
            elif part.upper() in PROTECTED_TERMS or part in PROTECTED_TERMS:
                # Find the correct casing from PROTECTED_TERMS
                for term in PROTECTED_TERMS:
                    if part.lower() == term.lower():
                        result_parts.append(term)
                        break
                else:
                    result_parts.append(part)
            else:
                result_parts.append(part.lower())
        return ''.join(result_parts)
    return word


def get_protected_form(word: str) -> str:
    """Get the correct protected form of a word."""
    clean_word = re.sub(r'[^\w\-.]', '', word)
    clean_word_no_dots = clean_word.replace('.', '')

    # Find leading and trailing punctuation
    punct_before = ''
    punct_after = ''
    i = 0
    while i < len(word) and not word[i].isalnum():
        punct_before += word[i]
        i += 1
    j = len(word) - 1
    while j >= 0 and not word[j].isalnum():
        punct_after = word[j] + punct_after
        j -= 1

    # If matches a pattern (acronym, Roman numeral, CamelCase), preserve original case
    if matches_protected_pattern(clean_word):
        return word  # Keep original exactly

    # Find matching protected term in PROTECTED_TERMS
    for term in PROTECTED_TERMS:
        if clean_word.lower() == term.lower():
            # Exact match including dots - use term's casing from PROTECTED_TERMS
            return punct_before + term + punct_after
        if clean_word_no_dots.lower() == term.lower():
            # Match without dots - preserve original word's dot pattern with term's casing
            # e.g., "U.S." matches "US" -> return "U.S." with correct casing
            result = ''
            term_idx = 0
            for char in clean_word:
                if char == '.':
                    result += '.'
                elif term_idx < len(term):
                    result += term[term_idx]
                    term_idx += 1
            return punct_before + result + punct_after

    return word


def to_sentence_case(title: str) -> str:
    """
    Convert title to APA7 sentence case.
    - First word capitalized
    - First word after colon/em-dash capitalized
    - Protected terms preserved
    - Everything else lowercase
    """
    if not title:
        return title

    # Step 1: Remove BibTeX braces
    title = remove_bibtex_braces(title)

    # Step 2: Fix typos
    title = fix_typos(title)

    # Step 3: Protect multi-word phrases by replacing spaces with placeholders
    phrase_map = {}
    for i, phrase in enumerate(PROTECTED_PHRASES):
        placeholder = f"__PHRASE_{i}__"
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(title):
            phrase_map[placeholder] = phrase
            title = pattern.sub(placeholder, title)

    # Step 4: Split into words
    words = title.split()
    result = []

    # Track if next word should be capitalized (start of sentence or after colon)
    capitalize_next = True

    for i, word in enumerate(words):
        # Check if this word ends with colon, em-dash, or question mark (capitalize next word)
        ends_with_colon = word.endswith(':') or word.endswith('—') or word.endswith('–') or word.endswith('?')

        # Get the word without trailing punctuation for checking
        word_base = word.rstrip(':—–,;.!?')
        trailing_punct = word[len(word_base):] if len(word_base) < len(word) else ''

        if capitalize_next:
            if is_protected(word_base):
                # Protected term - use correct form
                result.append(get_protected_form(word_base) + trailing_punct)
            elif '-' in word_base or '/' in word_base:
                # Compound word - process parts, capitalize first letter
                processed = process_compound_word(word_base)
                if len(processed) > 0:
                    processed = processed[0].upper() + processed[1:]
                result.append(processed + trailing_punct)
            else:
                # Capitalize first letter only
                if len(word_base) > 1:
                    result.append(word_base[0].upper() + word_base[1:].lower() + trailing_punct)
                else:
                    result.append(word_base.upper() + trailing_punct)
            capitalize_next = False
        elif is_protected(word_base):
            # Protected term - use correct form
            result.append(get_protected_form(word_base) + trailing_punct)
        elif '-' in word_base or '/' in word_base:
            # Compound word - process parts
            result.append(process_compound_word(word_base) + trailing_punct)
        else:
            # Regular word - lowercase
            result.append(word.lower())

        # Set flag for next word if this one ends with colon
        if ends_with_colon:
            capitalize_next = True

    title = ' '.join(result)

    # Step 5: Restore protected phrases
    for placeholder, phrase in phrase_map.items():
        title = title.replace(placeholder.lower(), phrase)
        title = title.replace(placeholder, phrase)

    return title


def detect_review_risks(original: str, transformed: str) -> list:
    """
    Find capitalized words the transform lowercased that may be proper nouns.

    The transform cannot distinguish "Black Hawk" (a helicopter) from "black box"
    (a common phrase) without a name list, and no list is complete. Rather than
    guess, flag every Capitalized -> lowercase change whose word is not recognized
    ordinary title vocabulary, and let a human decide.

    Returns a list of the suspicious words, in order of appearance. An empty list
    means every lowercasing in this title was routine.

    Added 2026-07-30 after a dry run proposed "DJI phantom 4", "U.S. army UH-60m
    Black hawk", and "staten island, new york" on NTSB accident reports.
    """
    risks = []
    original_words = original.split()
    transformed_words = transformed.split()

    if len(original_words) != len(transformed_words):
        # Word count changed (phrase placeholder or typo fix). Comparing
        # positionally would be meaningless, so report nothing rather than
        # report noise.
        return risks

    for index, (before, after) in enumerate(zip(original_words, transformed_words)):
        if before == after:
            continue

        stripped_before = before.strip('.,;:!?()[]"\'')
        stripped_after = after.strip('.,;:!?()[]"\'')

        # Only interested in a leading-capital word that became lowercase.
        if not stripped_before[:1].isupper() or not stripped_after[:1].islower():
            continue

        # The first word of the title, and the first after a colon, legitimately
        # change case; skip position 0 since sentence case governs it.
        if index == 0:
            continue

        if stripped_after.lower() in COMMON_TITLE_WORDS:
            continue

        risks.append(stripped_before)

    return risks


def get_collection_key(zot, collection_name: str) -> str:
    """Find collection key by name."""
    collections = zot.collections()
    for coll in collections:
        if coll['data'].get('name', '').lower() == collection_name.lower():
            return coll['key']

    # List available collections
    print(f"\nCollection '{collection_name}' not found. Available collections:")
    for coll in collections:
        print(f"  - {coll['data'].get('name')}")
    raise ValueError(f"Collection '{collection_name}' not found")


def classify_items(items: list) -> tuple:
    """
    Split items into safe changes and changes needing human review.

    Returns (changes, reviews, skipped_count). Both lists hold dicts with the
    item key, original title, proposed title, the raw item, and (for reviews)
    the suspicious words that triggered the flag.
    """
    changes = []
    reviews = []
    skipped = 0

    for item in items:
        if item['data'].get('itemType') in ['attachment', 'note', 'annotation']:
            skipped += 1
            continue

        original_title = item['data'].get('title', '')
        if not original_title:
            continue

        new_title = to_sentence_case(original_title)
        if original_title == new_title:
            continue

        record = {
            'key': item['key'],
            'original': original_title,
            'new': new_title,
            'item': item,
        }

        risks = detect_review_risks(original_title, new_title)
        if risks:
            record['risks'] = risks
            reviews.append(record)
        else:
            changes.append(record)

    return changes, reviews, skipped


def apply_changes(zot, records: list) -> tuple:
    """Write the proposed titles. Returns (success_count, error_count)."""
    success = 0
    errors = 0

    for i, record in enumerate(records, 1):
        item = record['item']
        item['data']['title'] = record['new']

        # Also update shortTitle if it exists
        if item['data'].get('shortTitle'):
            item['data']['shortTitle'] = to_sentence_case(item['data']['shortTitle'])

        try:
            zot.update_item(item)
            print(f"  [{i}/{len(records)}] Updated: {record['key']}")
            success += 1

            if i < len(records):
                time.sleep(RATE_LIMIT_DELAY)
        except HTTPError as e:
            print(f"  [{i}/{len(records)}] ERROR: {record['key']} - {e}")
            errors += 1

    return success, errors


def process_items(zot, items: list, dry_run: bool = True,
                  include_review: bool = False):
    """
    Classify, report, and optionally apply title changes for a set of items.

    Items whose transform lowercases an unrecognized capitalized word are
    reported as [REVIEW] and are NOT written unless include_review is True.
    """
    changes, reviews, skipped = classify_items(items)
    mode_str = "[DRY RUN] " if dry_run else ""

    for record in changes:
        print(f"\n{mode_str}[CHANGE] {record['key']}")
        print(f"  FROM: {record['original']}")
        print(f"  TO:   {record['new']}")

    for record in reviews:
        print(f"\n{mode_str}[REVIEW] {record['key']}")
        print(f"  FROM: {record['original']}")
        print(f"  TO:   {record['new']}")
        print(f"  UNRECOGNIZED CAPITALIZED WORD(S): {', '.join(record['risks'])}")
        print("  Possible proper noun. Not written unless --include-review.")

    total_flagged = len(changes) + len(reviews)
    print(f"\n{'='*70}")
    print(f"Total items reviewed: {len(items)}")
    print(f"Attachments/notes skipped: {skipped}")
    print(f"Safe changes: {len(changes)}")
    print(f"Needs human review: {len(reviews)}")
    print(f"Items unchanged: {len(items) - skipped - total_flagged}")
    print(f"{'='*70}")

    if reviews:
        # One consolidated vocabulary list, so the whole review pile can be
        # triaged in a single pass instead of item by item. In a title-cased
        # string every content word is capitalized, so capitalization carries no
        # proper-noun signal and this list will contain mostly ordinary words.
        # Sorting them into the two sets below is what makes the next run quiet.
        distinct = sorted({word for r in reviews for word in r['risks']},
                          key=str.lower)
        print(f"\n{'-'*70}")
        print(f"Distinct unrecognized words across {len(reviews)} item(s):")
        print(f"  {', '.join(distinct)}")
        print("\n  Proper nouns  -> add to PROTECTED_TERMS / PROTECTED_PHRASES")
        print("  Ordinary words -> add to COMMON_TITLE_WORDS")
        print(f"{'-'*70}")

    if reviews and not include_review:
        print("\nReview items were NOT applied. Inspect them, then either add the")
        print("proper nouns to PROTECTED_TERMS / PROTECTED_PHRASES and re-run, or")
        print("pass --include-review to accept the proposed titles as-is.")

    to_write = changes + (reviews if include_review else [])

    if not dry_run and to_write:
        print("\nApplying changes...")
        success, errors = apply_changes(zot, to_write)
        print(f"\nDone! {success} items updated, {errors} errors.")
    elif dry_run and to_write:
        print("\n[DRY RUN] No changes applied. Remove --dry-run to apply.")

    return changes, reviews


def process_collection(zot, collection_key: str, dry_run: bool = True,
                       include_review: bool = False):
    """Process all items in a collection."""
    print("\nFetching items from collection...")
    items = zot.everything(zot.collection_items(collection_key))
    print(f"Found {len(items)} items")
    return process_items(zot, items, dry_run, include_review)


def process_library(zot, dry_run: bool = True, include_review: bool = False):
    """Process all items in the library."""
    print("\nFetching all items from library...")
    items = zot.everything(zot.items())
    print(f"Found {len(items)} items")
    return process_items(zot, items, dry_run, include_review)


def process_keys(zot, item_keys: list, dry_run: bool = True,
                 include_review: bool = False):
    """Process an explicit list of item keys."""
    print(f"\nFetching {len(item_keys)} item(s) by key...")
    items = []
    for key in item_keys:
        try:
            items.append(zot.item(key))
        except HTTPError as e:
            print(f"  ERROR: could not fetch {key} - {e}")
    print(f"Found {len(items)} items")
    return process_items(zot, items, dry_run, include_review)


def main():
    parser = argparse.ArgumentParser(
        description="Transform Zotero titles to APA7 sentence case.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run              Preview changes
  %(prog)s                        Apply changes
  %(prog)s --collection "My Refs" Use different collection
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying'
    )
    parser.add_argument(
        '--collection', '-c',
        default=None,
        help='Collection name (default: process entire library)'
    )
    parser.add_argument(
        '--items', '-i',
        nargs='+',
        default=None,
        metavar='KEY',
        help='Process only these Zotero item keys (overrides --collection)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Process all items in the library (default behavior)'
    )
    parser.add_argument(
        '--include-review',
        action='store_true',
        help='Also apply titles flagged as possible proper-noun damage'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Load credentials
    library_id, library_type, api_key = load_credentials()

    print("Zotero APA7 Title Cleanup Script")
    print("=" * 70)
    print(f"Library ID: {library_id}")
    print(f"Library Type: {library_type}")
    if args.items:
        scope = f"{len(args.items)} explicit item key(s)"
    elif args.collection:
        scope = args.collection
    else:
        scope = 'Entire library'
    print(f"Scope: {scope}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Apply review-flagged items: {args.include_review}")
    print("=" * 70)

    # Connect to Zotero
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print("Connected to Zotero API")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Process items - explicit keys, a collection, or the entire library
    if args.items:
        process_keys(zot, args.items, dry_run=args.dry_run,
                     include_review=args.include_review)
    elif args.collection:
        try:
            collection_key = get_collection_key(zot, args.collection)
            print(f"Found collection key: {collection_key}")
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        process_collection(zot, collection_key, dry_run=args.dry_run,
                           include_review=args.include_review)
    else:
        process_library(zot, dry_run=args.dry_run,
                        include_review=args.include_review)


if __name__ == '__main__':
    main()
