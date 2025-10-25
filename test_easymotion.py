import os

import pytest

from easymotion import (
    PaneInfo,
    assign_hints_by_distance,
    find_matches,
    generate_hints,
    get_char_width,
    get_string_width,
    get_true_position,
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
    # Mock the CASE_SENSITIVE environment variable
    import easymotion
    original_case_sensitive = easymotion.CASE_SENSITIVE

    try:
        easymotion.CASE_SENSITIVE = False

        # Add a line with uppercase
        simple_pane.lines = ['Hello World']

        # Should match both 'h' and 'H'
        matches_lower = find_matches([simple_pane], 'h')
        matches_upper = find_matches([simple_pane], 'H')

        # Both should find the 'H' in "Hello"
        assert len(matches_lower) >= 1
        assert len(matches_upper) >= 1

    finally:
        easymotion.CASE_SENSITIVE = original_case_sensitive


def test_find_matches_smartsign():
    """Test SMARTSIGN feature - searching ',' also finds '<'"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        pane = PaneInfo(
            pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
        )
        pane.lines = ['hello, world < test']

        # With SMARTSIGN enabled, searching ',' should also find '<'
        easymotion.SMARTSIGN = True
        matches = find_matches([pane], ',')
        # Should find both ',' and '<'
        assert len(matches) >= 2

        # Without SMARTSIGN, should only find ','
        easymotion.SMARTSIGN = False
        matches = find_matches([pane], ',')
        assert len(matches) == 1

    finally:
        easymotion.SMARTSIGN = original_smartsign


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
    import easymotion
    original_hints = easymotion.HINTS

    try:
        easymotion.HINTS = 'abc'
        hint_mapping = assign_hints_by_distance(matches, cursor_y=0, cursor_x=0)

        # Find hint for closest match
        closest_match = (pane, 0, 2)
        closest_hint = [k for k, v in hint_mapping.items() if v == closest_match][0]

        # Closest match should get shortest hint
        all_hint_lengths = [len(h) for h in hint_mapping.keys()]
        assert len(closest_hint) == min(all_hint_lengths)

    finally:
        easymotion.HINTS = original_hints


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
