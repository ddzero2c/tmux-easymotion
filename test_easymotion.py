import os

import pytest

from easymotion import (
    PaneInfo,
    assign_hints_by_distance,
    find_matches,
    generate_hints,
    generate_smartsign_patterns,
    get_char_width,
    get_string_width,
    get_true_position,
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


def test_smartsign_key_mappings():
    """Test smartsign with key number-to-symbol mappings (issue reported: '3' not matching '#')"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True
        pane = PaneInfo(
            pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
        )

        # Test '3' -> '#' mapping (user reported issue)
        pane.lines = ['test 3# code']
        matches = find_matches([pane], '3')
        assert len(matches) == 2  # Should find both '3' and '#'

        # Test '1' -> '!' mapping
        pane.lines = ['test 1! code']
        matches = find_matches([pane], '1')
        assert len(matches) == 2  # Should find both '1' and '!'

        # Test '2' -> '@' mapping
        pane.lines = ['email 2@ test']
        matches = find_matches([pane], '2')
        assert len(matches) == 2  # Should find both '2' and '@'

        # Test '8' -> '*' mapping
        pane.lines = ['star 8* test']
        matches = find_matches([pane], '8')
        assert len(matches) == 2  # Should find both '8' and '*'

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_smartsign_with_case_insensitive():
    """Test smartsign combined with case insensitive mode"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN
    original_case_sensitive = easymotion.CASE_SENSITIVE

    try:
        easymotion.SMARTSIGN = True
        easymotion.CASE_SENSITIVE = False

        pane = PaneInfo(
            pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
        )

        # Smartsign should work with case insensitive mode
        pane.lines = ['test 3# CODE']
        matches = find_matches([pane], '3')
        assert len(matches) == 2  # Should find both '3' and '#'

    finally:
        easymotion.SMARTSIGN = original_smartsign
        easymotion.CASE_SENSITIVE = original_case_sensitive


def test_smartsign_reverse_search():
    """Test that searching for symbol itself (not number) works correctly"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True
        pane = PaneInfo(
            pane_id='%1', active=True, start_y=0, height=10, start_x=0, width=80
        )

        # Searching '#' should only find '#', not '3'
        # because '#' is not a key in SMARTSIGN_TABLE
        pane.lines = ['test 3# code']
        matches = find_matches([pane], '#')
        assert len(matches) == 1  # Should only find '#'

        # Searching '!' should only find '!'
        pane.lines = ['test 1! code']
        matches = find_matches([pane], '!')
        assert len(matches) == 1  # Should only find '!'

    finally:
        easymotion.SMARTSIGN = original_smartsign


# ============================================================================
# Tests for Generic Smartsign Pattern Generation
# ============================================================================

def test_generate_smartsign_patterns_disabled():
    """Test that pattern generation returns original when SMARTSIGN is disabled"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = False

        # Should return only the original pattern
        assert generate_smartsign_patterns("3") == ["3"]
        assert generate_smartsign_patterns("3,") == ["3,"]
        assert generate_smartsign_patterns("abc") == ["abc"]

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_generate_smartsign_patterns_1char():
    """Test 1-character smartsign pattern generation"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        # Character with mapping
        patterns = generate_smartsign_patterns("3")
        assert set(patterns) == {"3", "#"}

        # Character without mapping
        patterns = generate_smartsign_patterns("x")
        assert patterns == ["x"]

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_generate_smartsign_patterns_2char():
    """Test 2-character smartsign pattern generation (all combinations)"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        # Both characters have mappings: '3' -> '#', ',' -> '<'
        patterns = generate_smartsign_patterns("3,")
        assert set(patterns) == {"3,", "#,", "3<", "#<"}

        # Only first character has mapping
        patterns = generate_smartsign_patterns("3x")
        assert set(patterns) == {"3x", "#x"}

        # Only second character has mapping
        patterns = generate_smartsign_patterns("x,")
        assert set(patterns) == {"x,", "x<"}

        # Neither character has mapping
        patterns = generate_smartsign_patterns("ab")
        assert patterns == ["ab"]

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_generate_smartsign_patterns_3char():
    """Test 3-character pattern generation (verifies extensibility)"""
    import easymotion
    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        # All three have mappings: '1' -> '!', '2' -> '@', '3' -> '#'
        patterns = generate_smartsign_patterns("123")
        # Should generate 2^3 = 8 combinations
        expected = {"123", "!23", "1@3", "12#", "!@3", "!2#", "1@#", "!@#"}
        assert set(patterns) == expected

        # Mixed: first and last have mappings
        patterns = generate_smartsign_patterns("1x3")
        assert set(patterns) == {"1x3", "!x3", "1x#", "!x#"}

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
    import easymotion
    original_case_sensitive = easymotion.CASE_SENSITIVE

    try:
        easymotion.CASE_SENSITIVE = False
        simple_pane.lines = ['Hello HELLO heLLo']

        # Search for 'he' should match 'He', 'HE', 'he'
        matches = find_matches([simple_pane], 'he')
        assert len(matches) == 3

        # Search for 'HE' should also match all
        matches_upper = find_matches([simple_pane], 'HE')
        assert len(matches_upper) == 3

    finally:
        easymotion.CASE_SENSITIVE = original_case_sensitive


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
    import easymotion

    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        pane = PaneInfo('%1', True, 0, 3, 0, 40)
        pane.lines = ['test 3x and #x code']

        # Search for '3x' should match both '3x' and '#x'
        matches = find_matches([pane], '3x')
        assert len(matches) == 2

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_s2_smartsign_both_chars_mapping():
    """Test s2 mode with smartsign when both characters have mappings"""
    import easymotion

    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        pane = PaneInfo('%1', True, 0, 3, 0, 60)
        # '3' -> '#', ',' -> '<'
        pane.lines = ['3, #, 3< #< test']

        # Search for '3,' should match all 4 combinations
        matches = find_matches([pane], '3,')
        assert len(matches) == 4

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_s2_smartsign_no_mapping():
    """Test s2 mode with smartsign when no characters have mappings"""
    import easymotion

    original_smartsign = easymotion.SMARTSIGN

    try:
        easymotion.SMARTSIGN = True

        pane = PaneInfo('%1', True, 0, 3, 0, 40)
        pane.lines = ['test ab and cd code']

        # Search for 'ab' should only match 'ab' (no mappings)
        matches = find_matches([pane], 'ab')
        assert len(matches) == 1

    finally:
        easymotion.SMARTSIGN = original_smartsign


def test_s2_smartsign_with_case_insensitive():
    """Test s2 mode with smartsign + case insensitive combination"""
    import easymotion

    original_smartsign = easymotion.SMARTSIGN
    original_case_sensitive = easymotion.CASE_SENSITIVE

    try:
        easymotion.SMARTSIGN = True
        easymotion.CASE_SENSITIVE = False

        pane = PaneInfo('%1', True, 0, 3, 0, 40)
        pane.lines = ['3X #X 3x #x test']

        # Should match all case variations + smartsign variants
        matches = find_matches([pane], '3x')
        # Matches: 3X, #X, 3x, #x (4 total)
        assert len(matches) == 4

    finally:
        easymotion.SMARTSIGN = original_smartsign
        easymotion.CASE_SENSITIVE = original_case_sensitive


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
# Bash Script Validation Tests
# =============================================================================

import re
import subprocess
from pathlib import Path


def get_script_dir():
    """Get the directory containing the bash scripts"""
    return Path(__file__).parent


def test_bash_scripts_syntax():
    """Verify all bash scripts have valid syntax"""
    script_dir = get_script_dir()
    scripts = ['common.sh', 'mode-s.sh', 'mode-s2.sh', 'easymotion.tmux']

    for script_name in scripts:
        script_path = script_dir / script_name
        if script_path.exists():
            result = subprocess.run(
                ['bash', '-n', str(script_path)],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, \
                f"Syntax error in {script_name}: {result.stderr}"


def test_mode_scripts_use_defined_functions():
    """Verify mode scripts only call functions defined in common.sh

    This test catches issues like mode-s.sh calling 'build_env_vars'
    when the function was renamed to 'build_env_var_opts' in common.sh.
    """
    script_dir = get_script_dir()

    # Extract function definitions from common.sh
    common_sh = (script_dir / 'common.sh').read_text()
    defined_functions = set(re.findall(r'^(\w+)\s*\(\)\s*\{', common_sh, re.MULTILINE))

    # Scripts that source common.sh and may call its functions
    mode_scripts = ['mode-s.sh', 'mode-s2.sh']

    for script_name in mode_scripts:
        script_path = script_dir / script_name
        if not script_path.exists():
            continue

        script_content = script_path.read_text()

        # Find all function calls that look like: $(function_name ...)
        # This pattern matches $( followed by a word (function name)
        called_functions = set(re.findall(r'\$\((\w+)\s', script_content))

        # Filter to only functions that should be defined in common.sh
        # (exclude built-in commands and external utilities)
        builtins_and_externals = {
            'cd', 'dirname', 'pwd', 'echo', 'printf', 'cat', 'mktemp',
        }

        # Functions that start with 'build_' or 'create_' are likely from common.sh
        custom_functions = {f for f in called_functions
                           if f.startswith(('build_', 'create_', 'get_tmux'))}

        for func in custom_functions:
            assert func in defined_functions, \
                f"Script '{script_name}' calls undefined function '{func}'. " \
                f"Available functions in common.sh: {defined_functions}"


def test_mode_s_uses_run_shell_c():
    """Verify mode-s.sh uses 'run-shell -C' for proper command parsing

    When environment variables contain escaped quotes, tmux needs
    'run-shell -C' to properly parse the new-window command.
    This is how mode-s2.sh handles it, and mode-s.sh should do the same.
    """
    script_dir = get_script_dir()
    mode_s_content = (script_dir / 'mode-s.sh').read_text()

    # Check that new-window is wrapped in run-shell -C
    # The pattern should be: run-shell -C "new-window -d ...
    assert 'run-shell -C' in mode_s_content, \
        "mode-s.sh should use 'run-shell -C' to properly parse " \
        "environment variables with escaped quotes"

    # Ensure we're not using bare new-window without run-shell -C
    # Look for patterns like: "new-window -d $ENV but NOT inside run-shell -C
    lines = mode_s_content.split('\n')
    for line in lines:
        if 'new-window -d' in line and 'run-shell -C' not in line:
            # Allow comments
            if line.strip().startswith('#'):
                continue
            assert False, \
                f"mode-s.sh has 'new-window -d' without 'run-shell -C': {line}"
