"""Tests for zotero_apa7_cleanup title transforms and the proper-noun guard.

The regression cases come from a live dry run on 2026-07-30 that proposed
corrupting NTSB accident titles (aircraft designators, product lines, and US
place names all lowercased). Those titles are pinned here so the damage cannot
silently return.
"""
import pytest

from zotero_apa7_cleanup import (
    COMMON_TITLE_WORDS,
    detect_review_risks,
    matches_protected_pattern,
    to_sentence_case,
)


class TestAlphanumericDesignators:
    """Uppercase-plus-digit tokens are type designators, not words."""

    @pytest.mark.parametrize('token', ['AS350BA', '60M', 'A320', 'F1', '7110.65W'])
    def test_designator_is_protected(self, token):
        assert matches_protected_pattern(token) is True

    @pytest.mark.parametrize('token', ['helicopter', 'Valley', 'the'])
    def test_ordinary_word_is_not_protected(self, token):
        assert matches_protected_pattern(token) is False

    def test_lowercase_with_digits_is_not_a_designator(self):
        # No uppercase letter, so nothing to preserve.
        assert matches_protected_pattern('covid19') is False


class TestNtsbRegressionTitles:
    """The five titles the tool proposed to corrupt on 2026-07-30."""

    def test_dji_phantom_and_black_hawk_survive(self):
        original = ('Collision of DJI Phantom 4 and U.S. Army UH-60M Black Hawk '
                    'helicopter, Staten Island, New York, September 21, 2017')
        result = to_sentence_case(original)
        assert 'DJI Phantom 4' in result
        assert 'Black Hawk' in result
        assert 'UH-60M' in result
        assert 'Staten Island' in result
        assert 'New York' in result
        assert 'phantom' not in result
        assert 'black hawk' not in result

    def test_airbus_designator_survives(self):
        original = ('Collision of DJI Mavic 2 Zoom and Airbus AS350BA helicopter, '
                    'Johnson Valley, California, February 6, 2020')
        result = to_sentence_case(original)
        assert 'DJI Mavic 2 Zoom' in result
        assert 'AS350BA' in result
        assert 'Johnson Valley' in result
        assert 'California' in result
        assert 'as350ba' not in result

    def test_benchmark_names_survive(self):
        original = 'Judging LLM-as-a-judge with MT-Bench and Chatbot Arena'
        result = to_sentence_case(original)
        assert 'MT-Bench' in result
        assert 'Chatbot Arena' in result


class TestRoutineSentenceCasing:
    """Ordinary title-case-to-sentence-case still works."""

    def test_common_words_lowercase(self):
        original = 'Drone Threats Are Evolving; Data Retention Rules Are Not'
        assert to_sentence_case(original) == (
            'Drone threats are evolving; data retention rules are not'
        )

    def test_llm_acronym_expansion_lowercases(self):
        original = 'Evaluating research quality with Large Language Models'
        result = to_sentence_case(original)
        assert 'large language models' in result

    def test_first_word_stays_capitalized(self):
        assert to_sentence_case('Machine learning methods').startswith('Machine')


class TestDetectReviewRisks:
    """The guard flags unrecognized capitalized words rather than guessing."""

    def test_flags_unknown_proper_noun(self):
        risks = detect_review_risks(
            'A study of Kalamazoo weather',
            'A study of kalamazoo weather',
        )
        assert risks == ['Kalamazoo']

    def test_ignores_common_vocabulary(self):
        risks = detect_review_risks(
            'Drone Threats Are Evolving',
            'Drone threats are evolving',
        )
        assert risks == []

    def test_ignores_first_word(self):
        # Position 0 is governed by sentence case, not by proper-noun status.
        risks = detect_review_risks('Methods for X', 'methods for X')
        assert risks == []

    def test_returns_empty_when_word_count_changes(self):
        # Phrase placeholders and typo fixes can change the token count;
        # positional comparison would produce noise.
        risks = detect_review_risks('A B C', 'a b')
        assert risks == []

    def test_unchanged_title_has_no_risks(self):
        assert detect_review_risks('Same title', 'Same title') == []


class TestCommonTitleWordsHygiene:
    def test_entries_are_lowercase(self):
        # detect_review_risks lowercases before lookup; uppercase entries
        # would be dead weight and mask a real flag.
        assert all(word == word.lower() for word in COMMON_TITLE_WORDS)
