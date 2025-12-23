import os
import subprocess
import time
import uuid
from unittest.mock import patch

import pytest

from easymotion import (
    Config,
    PaneInfo,
    _get_all_tmux_options,
    assign_hints_by_distance,
    find_matches,
    generate_hints,
    generate_smartsign_patterns,
    get_char_width,
    get_string_width,
    get_tmux_option,
    get_true_position,
    tmux_move_cursor,
    update_hints_display,
)


def test_get_char_width():
    assert get_char_width('a') == 1  # ASCII character
    assert get_char_width('あ') == 2  # Japanese character (wide)
    assert get_char_width('漢') == 2  # Chinese character (wide)
    assert get_char_width('한') == 2  # Korean character (wide)
    assert get_char_width(' ') == 1  # Space
    assert get_char_width('\n') == 1  # Newline


def test_get_string_width():
    assert get_string_width('hello') == 5
    assert get_string_width('こんにちは') == 10
    assert get_string_width('hello こんにちは') == 16
    assert get_string_width('') == 0


def test_get_true_position():
    assert get_true_position('hello', 3) == 3
    assert get_true_position('あいうえお', 4) == 2
    assert get_true_position('hello あいうえお', 7) == 7
    assert get_true_position('', 5) == 0


def test_generate_hints():
    test_keys = 'ab'
    hints = generate_hints(test_keys)
    expected = ['aa', 'ab', 'ba', 'bb']
    assert hints == expected


def test_generate_hints_no_duplicates():
    keys = 'asdf'  # 4 characters

    # Test all possible hint counts from 1 to max (16)
    for count in range(1, 17):
        hints = generate_hints(keys, count)

        # Check no duplicates
        assert len(hints) == len(
            set(hints)), f"Duplicates found in hints for count {count}"

        # For double character hints, check first character usage
        single_chars = [h for h in hints if len(h) == 1]
        double_chars = [h for h in hints if len(h) == 2]
        if double_chars:
            for double_char in double_chars:
                assert double_char[0] not in single_chars, \
                    f"Double char hint {double_char} starts with single char hint"

            # Check all characters are from the key set
            assert all(c in keys for h in hints for c in h), \
                f"Invalid characters found in hints for count {count}"


def test_generate_hints_distribution():
    keys = 'asdf'  # 4 characters

    # Case i=4: 4 hints (all single chars)
    hints = generate_hints(keys, 4)
    assert len(hints) == 4
    assert all(len(hint) == 1 for hint in hints)
    assert set(hints) == set('asdf')

    # Case i=3: 7 hints (3 single + 4 double)
    hints = generate_hints(keys, 7)
    assert len(hints) == 7
    single_chars = [h for h in hints if len(h) == 1]
    double_chars = [h for h in hints if len(h) == 2]
    assert len(single_chars) == 3
    assert len(double_chars) == 4
    # Ensure double char prefixes don't overlap with single chars
    single_char_set = set(single_chars)
    double_char_firsts = set(h[0] for h in double_chars)
    assert not (single_char_set &
                double_char_firsts), "Double char prefixes overlap with single chars"

    # Case i=2: 10 hints (2 single + 8 double)
    hints = generate_hints(keys, 10)
    assert len(hints) == 10
    single_chars = [h for h in hints if len(h) == 1]
    double_chars = [h for h in hints if len(h) == 2]
    assert len(single_chars) == 2
    assert len(double_chars) == 8
    # Ensure double char prefixes don't overlap with single chars
    single_char_set = set(single_chars)
    double_char_firsts = set(h[0] for h in double_chars)
    assert not (single_char_set &
                double_char_firsts), "Double char prefixes overlap with single chars"

    # Case i=1: 13 hints (1 single + 12 double)
    hints = generate_hints(keys, 13)
    assert len(hints) == 13
    single_chars = [h for h in hints if len(h) == 1]
    double_chars = [h for h in hints if len(h) == 2]
    assert len(single_chars) == 1
    assert len(double_chars) == 12
    # Ensure double char prefixes don't overlap with single chars
    single_char_set = set(single_chars)
    double_char_firsts = set(h[0] for h in double_chars)
    assert not (single_char_set &
                double_char_firsts), "Double char prefixes overlap with single chars"

    # Case i=0: 16 hints (all double chars)
    hints = generate_hints(keys, 16)
    assert len(hints) == 16
    assert all(len(hint) == 2 for hint in hints)
    # For all double chars case, just ensure no duplicate combinations
    assert len(hints) == len(set(hints))


# ============================================================================
# Fixtures for reusable test data
# ============================================================================

@pytest.fixture
def simple_pane():
    """Single pane with basic ASCII content"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ['hello world', 'foo bar baz', 'test line']
    return pane


@pytest.fixture
def wide_char_pane():
    """Pane with CJK (wide) characters"""
    pane = PaneInfo(
        pane_id='%2', active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ['こんにちは world', '你好 hello', 'test 테스트']
    return pane


@pytest.fixture
def multi_pane():
    """Multiple panes for cross-pane testing"""
    pane1 = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=40
    )
    pane1.lines = ['left pane', 'aaa bbb']

    pane2 = PaneInfo(
        pane_id='%2', active=False, start_y=0, height=10, start_x=40, width=40
    )
    pane2.lines = ['right pane', 'ccc ddd']

    return [pane1, pane2]


# ============================================================================
# Tests for find_matches()
# ============================================================================

@pytest.mark.parametrize("search_char,expected_min_count", [
    ('o', 4),   # 'o' in "hello", "world", "foo"
    ('l', 3),   # 'l' in "hello", "world"
    ('b', 2),   # 'b' in "bar", "baz"
    ('x', 0),   # no matches
])
def test_find_matches_basic(simple_pane, search_char, expected_min_count):
    """Test basic character matching with various characters"""
    matches = find_matches([simple_pane], search_char)
    assert len(matches) >= expected_min_count


def test_find_matches_case_insensitive(simple_pane):
    """Test case-insensitive matching (default behavior)"""
    # Add a line with uppercase
    simple_pane.lines = ['Hello World']

    # With case_sensitive=False, should match both 'h' and 'H'
    matches_lower = find_matches([simple_pane], 'h', case_sensitive=False)
    matches_upper = find_matches([simple_pane], 'H', case_sensitive=False)

    # Both should find the 'H' in "Hello"
    assert len(matches_lower) >= 1
    assert len(matches_upper) >= 1


def test_find_matches_smartsign():
    """Test SMARTSIGN feature - searching ',' also finds '<'"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ['hello, world < test']

    # With smartsign enabled, searching ',' should also find '<'
    matches = find_matches([pane], ',', smartsign=True)
    # Should find both ',' and '<'
    assert len(matches) >= 2

    # Without smartsign, should only find ','
    matches = find_matches([pane], ',', smartsign=False)
    assert len(matches) == 1


def test_smartsign_key_mappings():
    """Test smartsign with key number-to-symbol mappings (issue reported: '3' not matching '#')"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )

    # Test '3' -> '#' mapping (user reported issue)
    pane.lines = ['test 3# code']
    matches = find_matches([pane], '3', smartsign=True)
    assert len(matches) == 2  # Should find both '3' and '#'

    # Test '1' -> '!' mapping
    pane.lines = ['test 1! code']
    matches = find_matches([pane], '1', smartsign=True)
    assert len(matches) == 2  # Should find both '1' and '!'

    # Test '2' -> '@' mapping
    pane.lines = ['email 2@ test']
    matches = find_matches([pane], '2', smartsign=True)
    assert len(matches) == 2  # Should find both '2' and '@'

    # Test '8' -> '*' mapping
    pane.lines = ['star 8* test']
    matches = find_matches([pane], '8', smartsign=True)
    assert len(matches) == 2  # Should find both '8' and '*'


def test_smartsign_with_case_insensitive():
    """Test smartsign combined with case insensitive mode (1-char and 2-char)"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )

    # 1-char: smartsign should work with case insensitive mode
    pane.lines = ['test 3# CODE']
    matches = find_matches([pane], '3', case_sensitive=False, smartsign=True)
    assert len(matches) == 2  # Should find both '3' and '#'

    # 2-char: should match all case variations + smartsign variants
    pane.lines = ['3X #X 3x #x test']
    matches = find_matches([pane], '3x', case_sensitive=False, smartsign=True)
    assert len(matches) == 4  # Matches: 3X, #X, 3x, #x


def test_smartsign_reverse_search():
    """Test that searching for symbol itself (not number) works correctly"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )

    # Searching '#' should only find '#', not '3'
    # because '#' is not a key in SMARTSIGN_TABLE
    pane.lines = ['test 3# code']
    matches = find_matches([pane], '#', smartsign=True)
    assert len(matches) == 1  # Should only find '#'

    # Searching '!' should only find '!'
    pane.lines = ['test 1! code']
    matches = find_matches([pane], '!', smartsign=True)
    assert len(matches) == 1  # Should only find '!'


# ============================================================================
# Tests for Generic Smartsign Pattern Generation
# ============================================================================

def test_generate_smartsign_patterns_disabled():
    """Test that pattern generation returns original when smartsign is disabled"""
    # Should return only the original pattern
    assert generate_smartsign_patterns("3", smartsign=False) == ["3"]
    assert generate_smartsign_patterns("3,", smartsign=False) == ["3,"]
    assert generate_smartsign_patterns("abc", smartsign=False) == ["abc"]


def test_generate_smartsign_patterns_1char():
    """Test 1-character smartsign pattern generation"""
    # Character with mapping
    patterns = generate_smartsign_patterns("3", smartsign=True)
    assert set(patterns) == {"3", "#"}

    # Character without mapping
    patterns = generate_smartsign_patterns("x", smartsign=True)
    assert patterns == ["x"]


def test_generate_smartsign_patterns_2char():
    """Test 2-character smartsign pattern generation (all combinations)"""
    # Both characters have mappings: '3' -> '#', ',' -> '<'
    patterns = generate_smartsign_patterns("3,", smartsign=True)
    assert set(patterns) == {"3,", "#,", "3<", "#<"}

    # Only first character has mapping
    patterns = generate_smartsign_patterns("3x", smartsign=True)
    assert set(patterns) == {"3x", "#x"}

    # Only second character has mapping
    patterns = generate_smartsign_patterns("x,", smartsign=True)
    assert set(patterns) == {"x,", "x<"}

    # Neither character has mapping
    patterns = generate_smartsign_patterns("ab", smartsign=True)
    assert patterns == ["ab"]


def test_generate_smartsign_patterns_3char():
    """Test 3-character pattern generation (verifies extensibility)"""
    # All three have mappings: '1' -> '!', '2' -> '@', '3' -> '#'
    patterns = generate_smartsign_patterns("123", smartsign=True)
    # Should generate 2^3 = 8 combinations
    expected = {"123", "!23", "1@3", "12#", "!@3", "!2#", "1@#", "!@#"}
    assert set(patterns) == expected

    # Mixed: first and last have mappings
    patterns = generate_smartsign_patterns("1x3", smartsign=True)
    assert set(patterns) == {"1x3", "!x3", "1x#", "!x#"}


def test_find_matches_wide_characters(wide_char_pane):
    """Test matching with wide characters and correct visual position"""
    matches = find_matches([wide_char_pane], 'w')

    # Should find 'w' in "world" on first line
    assert len(matches) >= 1

    # Check that visual column accounts for wide characters
    # 'こんにちは' = 5 chars * 2 width = 10, plus 1 space = 11
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    assert visual_col == 11  # After wide chars and space


def test_find_matches_multiple_panes(multi_pane):
    """Test finding matches across multiple panes"""
    matches = find_matches(multi_pane, 'a')

    # Should find 'a' in both panes: "pane" (twice), "aaa" (3 times) = 5+ total
    assert len(matches) >= 5

    # Verify matches come from both panes
    pane_ids = {match[0].pane_id for match in matches}
    assert '%1' in pane_ids
    assert '%2' in pane_ids


def test_find_matches_edge_cases():
    """Test edge cases: empty pane, no matches"""
    # Empty pane
    empty_pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )
    empty_pane.lines = []

    matches = find_matches([empty_pane], 'a')
    assert len(matches) == 0

    # Pane with content but no matches
    pane = PaneInfo(
        pane_id='%2', active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ['hello world']

    matches = find_matches([pane], 'z')
    assert len(matches) == 0


# ============================================================================
# Tests for assign_hints_by_distance()
# ============================================================================

def test_assign_hints_by_distance_basic(simple_pane):
    """Test that hints are assigned based on distance from cursor"""
    simple_pane.lines = ['hello world']

    matches = [
        (simple_pane, 0, 0),   # 'h' at position (0, 0)
        (simple_pane, 0, 6),   # 'w' at position (0, 6)
    ]

    # Cursor at (0, 0) - closer to first match
    hint_mapping = assign_hints_by_distance(matches, cursor_y=0, cursor_x=0)

    # Should have 2 hints
    assert len(hint_mapping) == 2

    # All matches should be in the mapping
    mapped_matches = list(hint_mapping.values())
    assert all(match in mapped_matches for match in matches)


def test_assign_hints_by_distance_priority():
    """Test that closer matches get simpler (shorter) hints"""
    pane = PaneInfo(
        pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ['a' * 80]

    matches = [
        (pane, 0, 50),  # Far from cursor
        (pane, 0, 2),   # Close to cursor
        (pane, 0, 25),  # Medium distance
    ]

    # Cursor at (0, 0)
    hint_mapping = assign_hints_by_distance(matches, cursor_y=0, cursor_x=0, hints_keys='abc')

    # Find hint for closest match
    closest_match = (pane, 0, 2)
    closest_hint = [k for k, v in hint_mapping.items() if v == closest_match][0]

    # Closest match should get shortest hint
    all_hint_lengths = [len(h) for h in hint_mapping.keys()]
    assert len(closest_hint) == min(all_hint_lengths)


def test_assign_hints_by_distance_multi_pane(multi_pane):
    """Test hint assignment across multiple panes"""
    matches = [
        (multi_pane[0], 0, 0),   # Left pane at screen x=0
        (multi_pane[1], 0, 0),   # Right pane at screen x=40
    ]

    # Cursor in left pane at (0, 0)
    hint_mapping = assign_hints_by_distance(matches, cursor_y=0, cursor_x=0)

    assert len(hint_mapping) == 2

    # Verify both matches are assigned hints
    mapped_matches = list(hint_mapping.values())
    assert matches[0] in mapped_matches
    assert matches[1] in mapped_matches


# ============================================================================
# Tests for PaneInfo
# ============================================================================

def test_pane_info_initialization():
    """Test PaneInfo initialization with correct defaults"""
    pane = PaneInfo(
        pane_id='%1',
        active=True,
        start_y=5,
        height=20,
        start_x=10,
        width=80
    )

    # Check provided values
    assert pane.pane_id == '%1'
    assert pane.active is True
    assert pane.start_y == 5
    assert pane.height == 20
    assert pane.start_x == 10
    assert pane.width == 80

    # Check defaults
    assert pane.lines == []
    assert pane.positions == []
    assert pane.copy_mode is False
    assert pane.scroll_position == 0
    assert pane.cursor_y == 0
    assert pane.cursor_x == 0


# ============================================================================
# Integration Test
# ============================================================================

def test_search_to_hint_integration(simple_pane):
    """Integration test: search → find matches → assign hints → verify positions"""
    simple_pane.lines = ['hello world test']

    # Step 1: Find matches for 'e'
    matches = find_matches([simple_pane], 'e')

    # Should find 'e' in "hello" and "test"
    assert len(matches) >= 2

    # Step 2: Assign hints based on distance from cursor
    cursor_y = simple_pane.start_y + 0  # First line
    cursor_x = simple_pane.start_x + 0  # Start of line

    hint_mapping = assign_hints_by_distance(matches, cursor_y, cursor_x)

    # Step 3: Verify hints are assigned to all matches
    assert len(hint_mapping) == len(matches)

    # Step 4: Verify positions can be extracted from matches
    for hint, (pane, line_num, visual_col) in hint_mapping.items():
        assert pane == simple_pane
        assert line_num == 0  # All matches on first line
        assert visual_col >= 0
        assert visual_col < len(simple_pane.lines[line_num])

        # Verify hint is valid
        assert len(hint) in [1, 2]  # Should be 1 or 2 characters


# ============================================================================
# Tests for 2-Character Search (Issue #6)
# ============================================================================

def test_find_matches_2char_basic(simple_pane):
    """Test 2-character search with basic patterns"""
    simple_pane.lines = ['hello world', 'foo bar baz', 'test line']

    # Search for 'wo'
    matches = find_matches([simple_pane], 'wo')
    assert len(matches) >= 1
    # Should find 'wo' in "world"
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    true_pos = get_true_position(simple_pane.lines[line_num], visual_col)
    assert simple_pane.lines[line_num][true_pos:true_pos+2] == 'wo'


def test_find_matches_2char_multiple(simple_pane):
    """Test 2-character search with multiple matches"""
    simple_pane.lines = ['hello hello', 'test hello']

    # Search for 'he'
    matches = find_matches([simple_pane], 'he')
    # Should find 'he' three times
    assert len(matches) == 3


def test_find_matches_2char_case_insensitive(simple_pane):
    """Test 2-character search with case insensitivity"""
    simple_pane.lines = ['Hello HELLO heLLo']

    # Search for 'he' should match 'He', 'HE', 'he'
    matches = find_matches([simple_pane], 'he', case_sensitive=False)
    assert len(matches) == 3

    # Search for 'HE' should also match all
    matches_upper = find_matches([simple_pane], 'HE', case_sensitive=False)
    assert len(matches_upper) == 3


def test_find_matches_2char_wide_characters(wide_char_pane):
    """Test 2-character search with wide characters"""
    # Search for 'ld' in "world"
    matches = find_matches([wide_char_pane], 'ld')
    assert len(matches) >= 1


def test_find_matches_2char_no_match(simple_pane):
    """Test 2-character search with no matches"""
    simple_pane.lines = ['hello world']

    # Search for pattern that doesn't exist
    matches = find_matches([simple_pane], 'xy')
    assert len(matches) == 0


def test_find_matches_2char_partial_match(simple_pane):
    """Test that partial matches don't count"""
    simple_pane.lines = ['hello']

    # Search for 'lo' - should find only one match at the end
    matches = find_matches([simple_pane], 'lo')
    assert len(matches) == 1


def test_s2_smartsign_single_char_mapping():
    """Test s2 mode with smartsign when only one character has mapping"""
    pane = PaneInfo('%1', True, 0, 3, 0, 40)
    pane.lines = ['test 3x and #x code']

    # Search for '3x' should match both '3x' and '#x'
    matches = find_matches([pane], '3x', smartsign=True)
    assert len(matches) == 2


def test_s2_smartsign_both_chars_mapping():
    """Test s2 mode with smartsign when both characters have mappings"""
    pane = PaneInfo('%1', True, 0, 3, 0, 60)
    # '3' -> '#', ',' -> '<'
    pane.lines = ['3, #, 3< #< test']

    # Search for '3,' should match all 4 combinations
    matches = find_matches([pane], '3,', smartsign=True)
    assert len(matches) == 4


def test_s2_smartsign_no_mapping():
    """Test s2 mode with smartsign when no characters have mappings"""
    pane = PaneInfo('%1', True, 0, 3, 0, 40)
    pane.lines = ['test ab and cd code']

    # Search for 'ab' should only match 'ab' (no mappings)
    matches = find_matches([pane], 'ab', smartsign=True)
    assert len(matches) == 1


def test_find_matches_2char_at_line_end(simple_pane):
    """Test 2-character search at end of line"""
    simple_pane.lines = ['hello']

    # Search for 'lo' at end of line
    matches = find_matches([simple_pane], 'lo')
    assert len(matches) == 1
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    true_pos = get_true_position(simple_pane.lines[line_num], visual_col)
    assert simple_pane.lines[line_num][true_pos:true_pos+2] == 'lo'


# ============================================================================
# Tests for Line-End Hint Restoration Bug Fix
# ============================================================================

def test_positions_construction_at_line_end(simple_pane):
    """Test that positions are correctly constructed when match is at line end"""
    simple_pane.lines = ['hello']

    # Find match for 'o' at end of line (position 4)
    matches = find_matches([simple_pane], 'o')
    assert len(matches) == 1

    pane, line_num, visual_col = matches[0]
    line = pane.lines[line_num]
    true_col = get_true_position(line, visual_col)

    # At line end, true_col should be the last character
    assert true_col == 4  # 'o' is at index 4
    assert line[true_col] == 'o'

    # next_char should be empty because we're at line end
    next_char = line[true_col + 1] if true_col + 1 < len(line) else ''
    assert next_char == ''

    # But next_x should still be within pane bounds (for padding area)
    next_x = simple_pane.start_x + visual_col + get_char_width('o')
    pane_right_edge = simple_pane.start_x + simple_pane.width
    assert next_x < pane_right_edge  # Should be within pane for padding


class MockScreen:
    """Mock Screen class to record addstr calls for testing"""

    # Attribute constants matching real Screen class
    A_NORMAL = 0
    A_DIM = 1
    A_HINT1 = 2
    A_HINT2 = 3

    def __init__(self):
        self.calls = []
        self.refresh_called = False

    def addstr(self, y, x, text, attr=0):
        """Record all addstr calls"""
        self.calls.append({
            'y': y,
            'x': x,
            'text': text,
            'attr': attr
        })

    def refresh(self):
        """Record refresh call"""
        self.refresh_called = True

    def get_calls_at_position(self, x):
        """Helper to get all calls at a specific x position"""
        return [call for call in self.calls if call['x'] == x]


def test_hint_restoration_at_line_end():
    """Test that hint at line end is properly restored when first char is pressed"""
    # Create a pane with line ending at 'o'
    pane = PaneInfo('%1', True, 0, 1, 0, 20)
    pane.lines = ['hello']

    # Simulate a two-character hint 'ab' at the last character 'o' (position 4)
    # screen_y, screen_x, pane_right_edge, char, next_char, hint
    positions = [
        (0, 4, 20, 'o', '', 'ab')  # next_char is empty (line end)
    ]

    # Create mock screen
    screen = MockScreen()

    # Simulate user pressing first hint character 'a'
    update_hints_display(screen, positions, 'a')

    # Verify that refresh was called
    assert screen.refresh_called

    # Get calls at position 5 (next_x = 4 + get_char_width('o') = 5)
    calls_at_next_pos = screen.get_calls_at_position(5)

    # Should have one call to restore the second position
    assert len(calls_at_next_pos) == 1

    # The restored character should be a space, not empty string
    assert calls_at_next_pos[0]['text'] == ' '
    assert calls_at_next_pos[0]['text'] != ''  # Bug fix: was empty before


def test_hint_restoration_not_at_line_end():
    """Test that hint restoration works correctly when NOT at line end"""
    # Create a pane
    pane = PaneInfo('%1', True, 0, 1, 0, 20)
    pane.lines = ['hello world']

    # Simulate a two-character hint 'ab' at 'e' (position 1), next_char is 'l'
    positions = [
        (0, 1, 20, 'e', 'l', 'ab')  # next_char is 'l' (not empty)
    ]

    # Create mock screen
    screen = MockScreen()

    # Simulate user pressing first hint character 'a'
    update_hints_display(screen, positions, 'a')

    # Get calls at position 2 (next_x = 1 + get_char_width('e') = 2)
    calls_at_next_pos = screen.get_calls_at_position(2)

    # Should restore the actual next character 'l'
    assert len(calls_at_next_pos) == 1
    assert calls_at_next_pos[0]['text'] == 'l'


# =============================================================================
# Integration Tests - Issue #18 Wrapped Line Cursor Jump
# =============================================================================

def tmux_available():
    """Check if tmux is available for integration tests."""
    try:
        result = subprocess.run(['tmux', '-V'], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


requires_tmux = pytest.mark.skipif(
    not tmux_available(),
    reason="tmux not available"
)


class TmuxTestServer:
    """Manage a separate tmux server for integration testing.

    Uses -L flag to create an isolated tmux server with controlled pane size.
    This is necessary because detached sessions in the main server inherit
    the terminal size from attached clients.
    """

    def __init__(self, width=30, height=10):
        self.server_name = f"pytest_{uuid.uuid4().hex[:8]}"
        self.width = width
        self.height = height
        self.pane_id = None

    def start(self):
        """Start the tmux server with controlled dimensions."""
        result = subprocess.run(
            ['tmux', '-L', self.server_name, 'new-session', '-d',
             '-s', 'test', '-x', str(self.width), '-y', str(self.height)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not create tmux server: {result.stderr}")

        time.sleep(0.2)
        self.pane_id = subprocess.run(
            ['tmux', '-L', self.server_name, 'list-panes', '-F', '#{pane_id}'],
            capture_output=True,
            text=True
        ).stdout.strip()

    def stop(self):
        """Kill the tmux server."""
        subprocess.run(
            ['tmux', '-L', self.server_name, 'kill-server'],
            capture_output=True
        )

    def send_keys(self, *args):
        """Send keys to the pane."""
        subprocess.run(
            ['tmux', '-L', self.server_name, 'send-keys', '-t', self.pane_id] + list(args)
        )

    def get_cursor_position(self):
        """Get cursor position in copy mode."""
        result = subprocess.run(
            ['tmux', '-L', self.server_name, 'display-message', '-t', self.pane_id,
             '-p', '#{copy_cursor_x},#{copy_cursor_y}'],
            capture_output=True,
            text=True
        )
        x, y = result.stdout.strip().split(',')
        return int(x), int(y)

    def split_window(self, horizontal=True):
        """Split the window to create a new pane.

        Args:
            horizontal: If True, split horizontally (panes side by side).
                       If False, split vertically (panes stacked).

        Returns:
            The pane_id of the newly created pane.
        """
        split_flag = '-h' if horizontal else '-v'
        result = subprocess.run(
            ['tmux', '-L', self.server_name, 'split-window', split_flag,
             '-t', self.pane_id, '-P', '-F', '#{pane_id}'],
            capture_output=True,
            text=True
        )
        new_pane_id = result.stdout.strip()
        time.sleep(0.1)
        return new_pane_id

    def get_active_pane(self):
        """Get the currently active pane ID."""
        result = subprocess.run(
            ['tmux', '-L', self.server_name, 'display-message', '-p', '#{pane_id}'],
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def send_keys_to_pane(self, pane_id, *args):
        """Send keys to a specific pane."""
        subprocess.run(
            ['tmux', '-L', self.server_name, 'send-keys', '-t', pane_id] + list(args)
        )

    def get_cursor_position_in_pane(self, pane_id):
        """Get cursor position in copy mode for a specific pane."""
        result = subprocess.run(
            ['tmux', '-L', self.server_name, 'display-message', '-t', pane_id,
             '-p', '#{copy_cursor_x},#{copy_cursor_y}'],
            capture_output=True,
            text=True
        )
        x, y = result.stdout.strip().split(',')
        return int(x), int(y)

    def make_sh_for_server(self):
        """Create a sh() function that targets this test server.

        Returns a function that can be used to patch easymotion.sh,
        injecting -L server_name into tmux commands.
        """
        server_name = self.server_name

        def patched_sh(cmd: list) -> str:
            # Inject -L server_name after 'tmux' command
            if cmd and cmd[0] == 'tmux':
                cmd = ['tmux', '-L', server_name] + cmd[1:]
            result = subprocess.run(
                cmd,
                shell=False,
                text=True,
                capture_output=True,
            )
            return result.stdout

        return patched_sh


@pytest.fixture
def tmux_server():
    """Create a temporary tmux server for integration testing."""
    server = TmuxTestServer(width=30, height=10)
    try:
        server.start()
    except RuntimeError as e:
        pytest.skip(str(e))
    yield server
    server.stop()


@requires_tmux
def test_cursor_jump_on_wrapped_line(tmux_server):
    """Regression test for issue #18: tmux_move_cursor on wrapped lines.

    This test verifies that tmux_move_cursor correctly positions the cursor
    on wrapped lines (where a single logical line spans multiple screen lines).

    Setup:
    - Pane width: 30 chars
    - Content: 90 chars (AAA...BBB...CCC...) wrapping to 3 screen lines

    The fix in issue #18: start-of-line must come BEFORE cursor-down,
    otherwise cursor jumps to beginning of logical line.
    """
    pane_id = tmux_server.pane_id

    # Create content that wraps: 90 chars in 30-char pane = 3 screen lines
    content = "A" * 30 + "B" * 30 + "C" * 30
    tmux_server.send_keys(f'printf "{content}"', 'Enter')
    time.sleep(0.3)

    # Create PaneInfo
    pane = PaneInfo(pane_id, active=True, start_y=0, height=10, start_x=0, width=30)
    pane.copy_mode = False

    # Jump to line 2 (the wrapped portion with C's)
    target_line = 2
    target_col = 5

    # Call tmux_move_cursor with patched sh()
    with patch('easymotion.sh', tmux_server.make_sh_for_server()):
        tmux_move_cursor(pane, target_line, target_col)

    time.sleep(0.1)

    cursor_x, cursor_y = tmux_server.get_cursor_position()

    # The cursor Y should be at target_line (not jumped back to line 0)
    assert cursor_y == target_line, (
        f"Issue #18 regression: tmux_move_cursor landed on line {cursor_y}, "
        f"expected {target_line}. On wrapped lines, cursor should stay on "
        f"target screen line, not jump to logical line start."
    )
    assert cursor_x == target_col, (
        f"Cursor X position wrong: expected {target_col}, got {cursor_x}"
    )


# =============================================================================
# Integration Tests - Cross-Pane Jump (Core Feature)
# =============================================================================

@requires_tmux
def test_same_pane_jump(tmux_server):
    """Integration test: verify cursor positioning within the same pane.

    This tests tmux_move_cursor when jumping to a position in the current pane.
    """
    pane_id = tmux_server.pane_id

    # Add content to pane
    tmux_server.send_keys('echo "line0"', 'Enter')
    tmux_server.send_keys('echo "line1"', 'Enter')
    tmux_server.send_keys('echo "line2_target"', 'Enter')
    time.sleep(0.2)

    # Create PaneInfo for the pane
    pane = PaneInfo(pane_id, active=True, start_y=0, height=10, start_x=0, width=30)
    pane.copy_mode = False

    # Target position: line 2, column 7
    target_line = 2
    target_col = 7

    # Call tmux_move_cursor with patched sh()
    with patch('easymotion.sh', tmux_server.make_sh_for_server()):
        tmux_move_cursor(pane, target_line, target_col)

    time.sleep(0.1)

    # Verify cursor position
    cursor_x, cursor_y = tmux_server.get_cursor_position()
    assert cursor_y == target_line, (
        f"Cursor Y position wrong: expected {target_line}, got {cursor_y}"
    )
    assert cursor_x == target_col, (
        f"Cursor X position wrong: expected {target_col}, got {cursor_x}"
    )


@requires_tmux
def test_cross_pane_jump(tmux_server):
    """Integration test: verify tmux_move_cursor jumps to another pane correctly.

    This tests the core cross-pane feature: jumping from pane 1 to pane 2.
    """
    pane1_id = tmux_server.pane_id

    # Create pane 2 with vertical split (stacked)
    pane2_id = tmux_server.split_window(horizontal=False)
    time.sleep(0.2)

    # Add content to pane 2
    tmux_server.send_keys_to_pane(pane2_id, 'echo "line0"', 'Enter')
    tmux_server.send_keys_to_pane(pane2_id, 'echo "line1_target"', 'Enter')
    time.sleep(0.2)

    # Create PaneInfo for pane2 (the target)
    pane2 = PaneInfo(pane2_id, active=False, start_y=0, height=5, start_x=0, width=30)
    pane2.copy_mode = False

    # Target position: line 1, column 5
    target_line = 1
    target_col = 5

    # Call tmux_move_cursor with patched sh()
    with patch('easymotion.sh', tmux_server.make_sh_for_server()):
        tmux_move_cursor(pane2, target_line, target_col)

    time.sleep(0.1)

    # Verify pane2 is active (select-pane worked)
    assert tmux_server.get_active_pane() == pane2_id, "Pane 2 should be active after jump"

    # Verify cursor position
    cursor_x, cursor_y = tmux_server.get_cursor_position_in_pane(pane2_id)
    assert cursor_y == target_line, (
        f"Cursor Y position wrong: expected {target_line}, got {cursor_y}"
    )
    assert cursor_x == target_col, (
        f"Cursor X position wrong: expected {target_col}, got {cursor_x}"
    )


# =============================================================================
# Integration Tests - get_tmux_option and Config
# =============================================================================

@requires_tmux
def test_get_tmux_option_reads_value(tmux_server):
    """Integration test: verify get_tmux_option reads tmux options correctly."""
    # Clear cache to ensure fresh read
    _get_all_tmux_options.cache_clear()

    # Set a custom tmux option
    test_value = f"test_hints_{uuid.uuid4().hex[:8]}"
    subprocess.run([
        'tmux', '-L', tmux_server.server_name,
        'set-option', '-g', '@easymotion-test-option', test_value
    ], check=True)

    # Patch subprocess.run to use our test server
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == 'tmux' and 'show-options' in cmd:
            # Add server flag to the command
            new_cmd = ['tmux', '-L', tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch('subprocess.run', patched_run):
        result = get_tmux_option('@easymotion-test-option', 'default')

    assert result == test_value, f"Expected '{test_value}', got '{result}'"


@requires_tmux
def test_get_tmux_option_returns_default(tmux_server):
    """Integration test: verify get_tmux_option returns default when option not set."""
    # Clear cache to ensure fresh read
    _get_all_tmux_options.cache_clear()

    # Use an option name that definitely doesn't exist
    nonexistent_option = f"@easymotion-nonexistent-{uuid.uuid4().hex}"
    default_value = "my_default_value"

    # Patch subprocess.run to use our test server
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == 'tmux' and 'show-options' in cmd:
            new_cmd = ['tmux', '-L', tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch('subprocess.run', patched_run):
        result = get_tmux_option(nonexistent_option, default_value)

    assert result == default_value, f"Expected default '{default_value}', got '{result}'"


@requires_tmux
def test_config_from_tmux(tmux_server):
    """Integration test: verify Config.from_tmux() reads all options correctly."""
    # Clear cache to ensure fresh read
    _get_all_tmux_options.cache_clear()

    # Set custom tmux options
    subprocess.run([
        'tmux', '-L', tmux_server.server_name,
        'set-option', '-g', '@easymotion-hints', 'xyz'
    ], check=True)
    subprocess.run([
        'tmux', '-L', tmux_server.server_name,
        'set-option', '-g', '@easymotion-case-sensitive', 'true'
    ], check=True)
    subprocess.run([
        'tmux', '-L', tmux_server.server_name,
        'set-option', '-g', '@easymotion-smartsign', 'true'
    ], check=True)

    # Patch subprocess.run to use our test server
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == 'tmux' and 'show-options' in cmd:
            new_cmd = ['tmux', '-L', tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch('subprocess.run', patched_run):
        config = Config.from_tmux()

    assert config.hints == 'xyz', f"Expected hints='xyz', got '{config.hints}'"
    assert config.case_sensitive is True, f"Expected case_sensitive=True, got {config.case_sensitive}"
    assert config.smartsign is True, f"Expected smartsign=True, got {config.smartsign}"
