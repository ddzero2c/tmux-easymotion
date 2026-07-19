import os
import subprocess
import time
import uuid
from unittest.mock import patch

import pytest

import easymotion
from easymotion import (
    Config,
    PaneInfo,
    _detect_tmux_version,
    _expand_tabs,
    _clear_options_cache,
    assign_hints_by_distance,
    calculate_tab_width,
    find_matches,
    generate_hints,
    generate_smartsign_patterns,
    get_char_width,
    get_string_width,
    get_tmux_option,
    get_startup_info,
    get_true_position,
    tmux_capture_pane,
    tmux_move_cursor,
    update_hints_display,
    visual_slice,
)


def test_get_char_width():
    assert get_char_width("a") == 1  # ASCII character
    assert get_char_width("あ") == 2  # Japanese character (wide)
    assert get_char_width("漢") == 2  # Chinese character (wide)
    assert get_char_width("한") == 2  # Korean character (wide)
    assert get_char_width(" ") == 1  # Space
    assert get_char_width("\n") == 1  # Newline


def test_get_string_width():
    assert get_string_width("hello") == 5
    assert get_string_width("こんにちは") == 10
    assert get_string_width("hello こんにちは") == 16
    assert get_string_width("") == 0


def test_get_true_position():
    assert get_true_position("hello", 3) == 3
    assert get_true_position("あいうえお", 4) == 2
    assert get_true_position("hello あいうえお", 7) == 7
    assert get_true_position("", 5) == 0


# ---------------------------------------------------------------------------
# Tab handling — both tmux version code paths exercised on every CI run via
# the ``tmux_mode`` fixture, regardless of which tmux is actually installed.
# ---------------------------------------------------------------------------


@pytest.fixture(params=[(3, 5), (3, 6)], ids=["tmux<3.6", "tmux>=3.6"])
def tmux_mode(request, monkeypatch):
    """Force easymotion to behave as the parametrized tmux version.

    Patches ``TMUX_VERSION`` and clears the width caches so pre-fixture
    lookups don't bleed into the test.
    """
    version = request.param
    monkeypatch.setattr(easymotion, "TMUX_VERSION", version)
    easymotion._char_width_no_tab.cache_clear()
    easymotion.get_string_width.cache_clear()
    yield version
    easymotion._char_width_no_tab.cache_clear()
    easymotion.get_string_width.cache_clear()


def test_get_char_width_tab(tmux_mode):
    # Tab at column 0 is always 8 columns regardless of tmux version
    assert get_char_width("\t", 0) == 8

    if tmux_mode >= (3, 6):
        # tmux 3.6+: position-aware (next 8-column tab stop)
        assert get_char_width("\t", 1) == 7
        assert get_char_width("\t", 7) == 1
    else:
        # Older tmux: fixed-width 8-column glyph
        assert get_char_width("\t", 1) == 8
        assert get_char_width("\t", 7) == 8


def test_get_string_width_tab(tmux_mode):
    assert get_string_width("\t") == 8  # leading tab always lands on first stop

    if tmux_mode >= (3, 6):
        assert get_string_width("a\t") == 8  # 1 + (8-1)
        assert get_string_width("1234567\t") == 8  # 7 + (8-7)
        assert get_string_width("a\tb\t") == 16  # 1 + 7 + 1 + 7
    else:
        assert get_string_width("a\t") == 9  # 1 + 8
        assert get_string_width("1234567\t") == 15  # 7 + 8
        assert get_string_width("a\tb\t") == 18  # 1 + 8 + 1 + 8


def test_get_true_position_tab(tmux_mode):
    # Halfway-through-tab still maps to the tab itself, both versions
    assert get_true_position("\t", 4) == 1
    assert get_true_position("\t", 8) == 1

    # 'b' lives at string index 2 in "a\tb" regardless of tmux version;
    # the visual column it sits on differs.
    if tmux_mode >= (3, 6):
        # 'a' = col 0, '\t' = cols 1-7, 'b' = col 8
        assert get_true_position("a\tb", 5) == 2  # past tab → 'b'
        assert get_true_position("a\tb", 8) == 2  # exactly at 'b'
    else:
        # 'a' = col 0, '\t' = cols 1-8, 'b' = col 9
        assert get_true_position("a\tb", 5) == 2  # past tab → 'b'
        assert get_true_position("a\tb", 9) == 2  # exactly at 'b'
    assert get_true_position("a\tb", 100) == 3  # past end of string


def test_find_matches_visual_col_after_tab(tmux_mode):
    """Match column reported by find_matches must respect tab width."""
    pane = PaneInfo(
        pane_id="%0", active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ["a\tb"]

    matches = find_matches([pane], "b")
    assert len(matches) == 1
    _, line_num, visual_col = matches[0]
    assert line_num == 0

    expected = 8 if tmux_mode >= (3, 6) else 9
    assert visual_col == expected


def test_find_matches_visual_col_cjk_tab_mixed(tmux_mode):
    """Regression: find_matches computes visual_col incrementally (lazily
    advanced between matches) instead of get_string_width(line[:pos]).
    A line mixing wide chars and a tab must yield the same columns —
    including the position-dependent tab width on tmux >= 3.6."""
    pane = PaneInfo(
        pane_id="%0", active=True, start_y=0, height=10, start_x=0, width=80
    )
    line = "x中\tx漢x"
    pane.lines = [line]

    matches = find_matches([pane], "x")
    cols = [col for (_, _, col) in matches]

    if tmux_mode >= (3, 6):
        # x=0 | 中=1-2 | tab 3-7 (5 cells to next stop) | x=8 | 漢=9-10 | x=11
        assert cols == [0, 8, 11]
    else:
        # pre-3.6: tab is always 8 cells → x at 11, x at 14
        assert cols == [0, 11, 14]

    # must agree with the prefix-width helper the old implementation used
    assert cols == [get_string_width(line[:i]) for i, c in enumerate(line) if c == "x"]


def test_expand_tabs_uses_pane_local_stops(tmux_mode):
    """Tabs must be expanded against pane-local tab stops so that, after
    expansion, the line renders identically in any pane regardless of its
    screen position. Otherwise curses (screen-absolute tab stops) would
    disagree with tmux (pane-local) in split panes."""
    if tmux_mode >= (3, 6):
        # Position-aware: tab from col 0 → col 8 (8 cells).
        assert _expand_tabs("\t") == " " * 8
        # Tab from col 1 → col 8 (7 cells).
        assert _expand_tabs("a\t") == "a" + " " * 7
        # 7 chars then tab → col 8 (1 cell).
        assert _expand_tabs("1234567\t") == "1234567 "
        # Two tabs: 0→8 (8 cells), 9→16 (7 cells).
        assert _expand_tabs("a\tb\t") == "a" + " " * 7 + "b" + " " * 7
    else:
        # Pre-3.6 tmux: every tab is 8 cells regardless of position.
        assert _expand_tabs("\t") == " " * 8
        assert _expand_tabs("a\t") == "a" + " " * 8
        assert _expand_tabs("1234567\t") == "1234567" + " " * 8
    # No tabs → identity.
    assert _expand_tabs("hello") == "hello"
    assert _expand_tabs("") == ""


def test_visual_slice_truncates_by_cells_not_chars():
    """line[:pane.width] string-slicing overflows a pane when the line
    contains wide chars. visual_slice truncates by visual cells."""
    # 5 wide chars = 10 cells; truncate to 6 cells → keep 3 chars + pad.
    assert visual_slice("あいうえお", 6) == "あいう"
    # Truncating mid-wide-char drops the char and pads with a space.
    assert visual_slice("あいうえお", 5) == "あい "
    # Short lines get padded on the right.
    assert visual_slice("ab", 5) == "ab   "
    # Empty input pads to full width.
    assert visual_slice("", 4) == "    "
    # Pure ASCII slice behaves like the old string-index version.
    assert visual_slice("hello world", 5) == "hello"


def test_calculate_tab_width():
    assert calculate_tab_width(0) == 8
    assert calculate_tab_width(1) == 7
    assert calculate_tab_width(7) == 1
    assert calculate_tab_width(8) == 8
    assert calculate_tab_width(9) == 7
    # Custom tab size
    assert calculate_tab_width(0, tab_size=4) == 4
    assert calculate_tab_width(3, tab_size=4) == 1


def test_tmux_version_detection_returns_tuple():
    version = _detect_tmux_version()
    assert isinstance(version, tuple)
    assert len(version) == 2
    major, minor = version
    assert isinstance(major, int) and isinstance(minor, int)
    assert major >= 0 and minor >= 0


def test_tmux_version_string_parsing():
    """Replicates the parser inside _detect_tmux_version() for known formats."""
    import re

    cases = [
        ("tmux 3.5", (3, 5)),
        ("tmux 3.6a", (3, 6)),
        ("tmux 3.0a", (3, 0)),
        ("tmux 2.9a", (2, 9)),
        ("tmux next-3.6", (3, 6)),
        ("tmux next-3.7", (3, 7)),
        ("tmux 3.1-rc", (3, 1)),
        ("tmux 3.1-rc2", (3, 1)),
        ("tmux 3.1c", (3, 1)),
        ("tmux master", (0, 0)),
        ("tmux openbsd-6.6", (0, 0)),
        ("tmux openbsd-7.0", (0, 0)),
    ]
    for version_str, expected in cases:
        if "openbsd-" in version_str or "master" in version_str:
            result = (0, 0)
        else:
            match = re.search(r"(?:next-)?(\d+)\.(\d+)", version_str)
            result = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
        assert result == expected, f"{version_str!r} -> {result}, expected {expected}"


def test_generate_hints():
    test_keys = "ab"
    hints = generate_hints(test_keys)
    expected = ["aa", "ab", "ba", "bb"]
    assert hints == expected


def test_generate_hints_no_duplicates():
    keys = "asdf"  # 4 characters

    # Test all possible hint counts from 1 to max (16)
    for count in range(1, 17):
        hints = generate_hints(keys, count)

        # Check no duplicates
        assert len(hints) == len(set(hints)), (
            f"Duplicates found in hints for count {count}"
        )

        # For double character hints, check first character usage
        single_chars = [h for h in hints if len(h) == 1]
        double_chars = [h for h in hints if len(h) == 2]
        if double_chars:
            for double_char in double_chars:
                assert double_char[0] not in single_chars, (
                    f"Double char hint {double_char} starts with single char hint"
                )

            # Check all characters are from the key set
            assert all(c in keys for h in hints for c in h), (
                f"Invalid characters found in hints for count {count}"
            )


def test_generate_hints_distribution():
    keys = "asdf"  # 4 characters

    # Case i=4: 4 hints (all single chars)
    hints = generate_hints(keys, 4)
    assert len(hints) == 4
    assert all(len(hint) == 1 for hint in hints)
    assert set(hints) == set("asdf")

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
    assert not (single_char_set & double_char_firsts), (
        "Double char prefixes overlap with single chars"
    )

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
    assert not (single_char_set & double_char_firsts), (
        "Double char prefixes overlap with single chars"
    )

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
    assert not (single_char_set & double_char_firsts), (
        "Double char prefixes overlap with single chars"
    )

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
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ["hello world", "foo bar baz", "test line"]
    return pane


@pytest.fixture
def wide_char_pane():
    """Pane with CJK (wide) characters"""
    pane = PaneInfo(
        pane_id="%2", active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ["こんにちは world", "你好 hello", "test 테스트"]
    return pane


@pytest.fixture
def multi_pane():
    """Multiple panes for cross-pane testing"""
    pane1 = PaneInfo(
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=40
    )
    pane1.lines = ["left pane", "aaa bbb"]

    pane2 = PaneInfo(
        pane_id="%2", active=False, start_y=0, height=10, start_x=40, width=40
    )
    pane2.lines = ["right pane", "ccc ddd"]

    return [pane1, pane2]


# ============================================================================
# Tests for find_matches()
# ============================================================================


@pytest.mark.parametrize(
    "search_char,expected_min_count",
    [
        ("o", 4),  # 'o' in "hello", "world", "foo"
        ("l", 3),  # 'l' in "hello", "world"
        ("b", 2),  # 'b' in "bar", "baz"
        ("x", 0),  # no matches
    ],
)
def test_find_matches_basic(simple_pane, search_char, expected_min_count):
    """Test basic character matching with various characters"""
    matches = find_matches([simple_pane], search_char)
    assert len(matches) >= expected_min_count


def test_find_matches_case_insensitive(simple_pane):
    """Test case-insensitive matching (default behavior)"""
    # Add a line with uppercase
    simple_pane.lines = ["Hello World"]

    # With case_sensitive=False, should match both 'h' and 'H'
    matches_lower = find_matches([simple_pane], "h", case_sensitive=False)
    matches_upper = find_matches([simple_pane], "H", case_sensitive=False)

    # Both should find the 'H' in "Hello"
    assert len(matches_lower) >= 1
    assert len(matches_upper) >= 1


def test_find_matches_smartsign():
    """Test SMARTSIGN feature - various key mappings"""
    pane = PaneInfo(
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )

    # Test ',' -> '<' mapping
    pane.lines = ["hello, world < test"]
    matches = find_matches([pane], ",", smartsign=True)
    assert len(matches) == 2  # Should find both ',' and '<'

    # Without smartsign, should only find ','
    matches = find_matches([pane], ",", smartsign=False)
    assert len(matches) == 1

    # Test '3' -> '#' mapping
    pane.lines = ["test 3# code"]
    matches = find_matches([pane], "3", smartsign=True)
    assert len(matches) == 2  # Should find both '3' and '#'

    # Test '1' -> '!' mapping
    pane.lines = ["test 1! code"]
    matches = find_matches([pane], "1", smartsign=True)
    assert len(matches) == 2  # Should find both '1' and '!'


def test_smartsign_with_case_insensitive():
    """Test smartsign combined with case insensitive mode (1-char and 2-char)"""
    pane = PaneInfo(
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )

    # 1-char: smartsign should work with case insensitive mode
    pane.lines = ["test 3# CODE"]
    matches = find_matches([pane], "3", case_sensitive=False, smartsign=True)
    assert len(matches) == 2  # Should find both '3' and '#'

    # 2-char: should match all case variations + smartsign variants
    pane.lines = ["3X #X 3x #x test"]
    matches = find_matches([pane], "3x", case_sensitive=False, smartsign=True)
    assert len(matches) == 4  # Matches: 3X, #X, 3x, #x


def test_smartsign_reverse_search():
    """Test that searching for symbol itself (not number) works correctly"""
    pane = PaneInfo(
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )

    # Searching '#' should only find '#', not '3'
    # because '#' is not a key in SMARTSIGN_TABLE
    pane.lines = ["test 3# code"]
    matches = find_matches([pane], "#", smartsign=True)
    assert len(matches) == 1  # Should only find '#'

    # Searching '!' should only find '!'
    pane.lines = ["test 1! code"]
    matches = find_matches([pane], "!", smartsign=True)
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
    matches = find_matches([wide_char_pane], "w")

    # Should find 'w' in "world" on first line
    assert len(matches) >= 1

    # Check that visual column accounts for wide characters
    # 'こんにちは' = 5 chars * 2 width = 10, plus 1 space = 11
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    assert visual_col == 11  # After wide chars and space


def test_find_matches_multiple_panes(multi_pane):
    """Test finding matches across multiple panes"""
    matches = find_matches(multi_pane, "a")

    # Should find 'a' in both panes: "pane" (twice), "aaa" (3 times) = 5+ total
    assert len(matches) >= 5

    # Verify matches come from both panes
    pane_ids = {match[0].pane_id for match in matches}
    assert "%1" in pane_ids
    assert "%2" in pane_ids


def test_find_matches_edge_cases():
    """Test edge cases: empty pane, no matches"""
    # Empty pane
    empty_pane = PaneInfo(
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )
    empty_pane.lines = []

    matches = find_matches([empty_pane], "a")
    assert len(matches) == 0

    # Pane with content but no matches
    pane = PaneInfo(
        pane_id="%2", active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ["hello world"]

    matches = find_matches([pane], "z")
    assert len(matches) == 0


# ============================================================================
# Tests for assign_hints_by_distance()
# ============================================================================


def test_assign_hints_by_distance_basic(simple_pane):
    """Test that hints are assigned based on distance from cursor"""
    simple_pane.lines = ["hello world"]

    matches = [
        (simple_pane, 0, 0),  # 'h' at position (0, 0)
        (simple_pane, 0, 6),  # 'w' at position (0, 6)
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
        pane_id="%1", active=True, start_y=0, height=10, start_x=0, width=80
    )
    pane.lines = ["a" * 80]

    matches = [
        (pane, 0, 50),  # Far from cursor
        (pane, 0, 2),  # Close to cursor
        (pane, 0, 25),  # Medium distance
    ]

    # Cursor at (0, 0)
    hint_mapping = assign_hints_by_distance(
        matches, cursor_y=0, cursor_x=0, hints_keys="abc"
    )

    # Find hint for closest match
    closest_match = (pane, 0, 2)
    closest_hint = [k for k, v in hint_mapping.items() if v == closest_match][0]

    # Closest match should get shortest hint
    all_hint_lengths = [len(h) for h in hint_mapping.keys()]
    assert len(closest_hint) == min(all_hint_lengths)


def test_assign_hints_by_distance_multi_pane(multi_pane):
    """Test hint assignment across multiple panes"""
    matches = [
        (multi_pane[0], 0, 0),  # Left pane at screen x=0
        (multi_pane[1], 0, 0),  # Right pane at screen x=40
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
        pane_id="%1", active=True, start_y=5, height=20, start_x=10, width=80
    )

    # Check provided values
    assert pane.pane_id == "%1"
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
    simple_pane.lines = ["hello world test"]

    # Step 1: Find matches for 'e'
    matches = find_matches([simple_pane], "e")

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
    simple_pane.lines = ["hello world", "foo bar baz", "test line"]

    # Search for 'wo'
    matches = find_matches([simple_pane], "wo")
    assert len(matches) >= 1
    # Should find 'wo' in "world"
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    true_pos = get_true_position(simple_pane.lines[line_num], visual_col)
    assert simple_pane.lines[line_num][true_pos : true_pos + 2] == "wo"


def test_find_matches_2char_multiple(simple_pane):
    """Test 2-character search with multiple matches"""
    simple_pane.lines = ["hello hello", "test hello"]

    # Search for 'he'
    matches = find_matches([simple_pane], "he")
    # Should find 'he' three times
    assert len(matches) == 3


def test_find_matches_2char_case_insensitive(simple_pane):
    """Test 2-character search with case insensitivity"""
    simple_pane.lines = ["Hello HELLO heLLo"]

    # Search for 'he' should match 'He', 'HE', 'he'
    matches = find_matches([simple_pane], "he", case_sensitive=False)
    assert len(matches) == 3

    # Search for 'HE' should also match all
    matches_upper = find_matches([simple_pane], "HE", case_sensitive=False)
    assert len(matches_upper) == 3


def test_find_matches_2char_wide_characters(wide_char_pane):
    """Test 2-character search with wide characters"""
    # Search for 'ld' in "world"
    matches = find_matches([wide_char_pane], "ld")
    assert len(matches) >= 1


def test_find_matches_2char_no_match(simple_pane):
    """Test 2-character search with no matches"""
    simple_pane.lines = ["hello world"]

    # Search for pattern that doesn't exist
    matches = find_matches([simple_pane], "xy")
    assert len(matches) == 0


def test_find_matches_2char_partial_match(simple_pane):
    """Test that partial matches don't count"""
    simple_pane.lines = ["hello"]

    # Search for 'lo' - should find only one match at the end
    matches = find_matches([simple_pane], "lo")
    assert len(matches) == 1


def test_s2_smartsign_single_char_mapping():
    """Test s2 mode with smartsign when only one character has mapping"""
    pane = PaneInfo("%1", True, 0, 3, 0, 40)
    pane.lines = ["test 3x and #x code"]

    # Search for '3x' should match both '3x' and '#x'
    matches = find_matches([pane], "3x", smartsign=True)
    assert len(matches) == 2


def test_s2_smartsign_both_chars_mapping():
    """Test s2 mode with smartsign when both characters have mappings"""
    pane = PaneInfo("%1", True, 0, 3, 0, 60)
    # '3' -> '#', ',' -> '<'
    pane.lines = ["3, #, 3< #< test"]

    # Search for '3,' should match all 4 combinations
    matches = find_matches([pane], "3,", smartsign=True)
    assert len(matches) == 4


def test_s2_smartsign_no_mapping():
    """Test s2 mode with smartsign when no characters have mappings"""
    pane = PaneInfo("%1", True, 0, 3, 0, 40)
    pane.lines = ["test ab and cd code"]

    # Search for 'ab' should only match 'ab' (no mappings)
    matches = find_matches([pane], "ab", smartsign=True)
    assert len(matches) == 1


def test_find_matches_2char_at_line_end(simple_pane):
    """Test 2-character search at end of line"""
    simple_pane.lines = ["hello"]

    # Search for 'lo' at end of line
    matches = find_matches([simple_pane], "lo")
    assert len(matches) == 1
    pane, line_num, visual_col = matches[0]
    assert line_num == 0
    true_pos = get_true_position(simple_pane.lines[line_num], visual_col)
    assert simple_pane.lines[line_num][true_pos : true_pos + 2] == "lo"


# ============================================================================
# Tests for Line-End Hint Restoration Bug Fix
# ============================================================================


def test_positions_construction_at_line_end(simple_pane):
    """Test that positions are correctly constructed when match is at line end"""
    simple_pane.lines = ["hello"]

    # Find match for 'o' at end of line (position 4)
    matches = find_matches([simple_pane], "o")
    assert len(matches) == 1

    pane, line_num, visual_col = matches[0]
    line = pane.lines[line_num]
    true_col = get_true_position(line, visual_col)

    # At line end, true_col should be the last character
    assert true_col == 4  # 'o' is at index 4
    assert line[true_col] == "o"

    # next_char should be empty because we're at line end
    next_char = line[true_col + 1] if true_col + 1 < len(line) else ""
    assert next_char == ""

    # But next_x should still be within pane bounds (for padding area)
    next_x = simple_pane.start_x + visual_col + get_char_width("o")
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
        self.calls.append({"y": y, "x": x, "text": text, "attr": attr})

    def refresh(self):
        """Record refresh call"""
        self.refresh_called = True

    def get_calls_at_position(self, x):
        """Helper to get all calls at a specific x position"""
        return [call for call in self.calls if call["x"] == x]


def test_hint_restoration_at_line_end():
    """Test that hint at line end is properly restored when first char is pressed"""
    # Create a pane with line ending at 'o'
    pane = PaneInfo("%1", True, 0, 1, 0, 20)
    pane.lines = ["hello"]

    # Simulate a two-character hint 'ab' at the last character 'o' (position 4)
    # screen_y, screen_x, pane_right_edge, char, next_char, hint
    positions = [
        (0, 4, 20, "o", "", "ab")  # next_char is empty (line end)
    ]

    # Create mock screen
    screen = MockScreen()

    # Simulate user pressing first hint character 'a'
    update_hints_display(screen, positions, "a")

    # Verify that refresh was called
    assert screen.refresh_called

    # Get calls at position 5 (next_x = 4 + get_char_width('o') = 5)
    calls_at_next_pos = screen.get_calls_at_position(5)

    # Should have one call to restore the second position
    assert len(calls_at_next_pos) == 1

    # The restored character should be a space, not empty string
    assert calls_at_next_pos[0]["text"] == " "
    assert calls_at_next_pos[0]["text"] != ""  # Bug fix: was empty before


def test_hint_restoration_not_at_line_end():
    """Test that hint restoration works correctly when NOT at line end"""
    # Create a pane
    pane = PaneInfo("%1", True, 0, 1, 0, 20)
    pane.lines = ["hello world"]

    # Simulate a two-character hint 'ab' at 'e' (position 1), next_char is 'l'
    positions = [
        (0, 1, 20, "e", "l", "ab")  # next_char is 'l' (not empty)
    ]

    # Create mock screen
    screen = MockScreen()

    # Simulate user pressing first hint character 'a'
    update_hints_display(screen, positions, "a")

    # Get calls at position 2 (next_x = 1 + get_char_width('e') = 2)
    calls_at_next_pos = screen.get_calls_at_position(2)

    # Should restore the actual next character 'l'
    assert len(calls_at_next_pos) == 1
    assert calls_at_next_pos[0]["text"] == "l"


# =============================================================================
# Integration Tests - Issue #18 Wrapped Line Cursor Jump
# =============================================================================


def tmux_available():
    """Check if tmux is available for integration tests."""
    try:
        result = subprocess.run(["tmux", "-V"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


requires_tmux = pytest.mark.skipif(not tmux_available(), reason="tmux not available")


def _server_tmux_version() -> tuple:
    try:
        out = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return (0, 0)
    return easymotion._parse_tmux_version(out.strip())


# The direct frozen-view read needs #{copy_cursor_line} without the
# wide-char truncation bug (fixed in tmux 3.6); older tmux uses the
# legacy live-grid approximations with their documented limitations.
requires_view_read = pytest.mark.skipif(
    _server_tmux_version() < (3, 6),
    reason="frozen-view direct read needs tmux >= 3.6",
)


class TmuxTestServer:
    """Manage a separate tmux server for integration testing.

    Uses -L flag to create an isolated tmux server with controlled pane size.
    This is necessary because detached sessions in the main server inherit
    the terminal size from attached clients.
    """

    def __init__(self, width=30, height=10, shell_command=None):
        self.server_name = f"pytest_{uuid.uuid4().hex[:8]}"
        self.width = width
        self.height = height
        self.shell_command = shell_command  # e.g. custom-PS1 bash for geometry tests
        self.pane_id: str = ""

    def start(self):
        """Start the tmux server with controlled dimensions."""
        cmd = [
            "tmux",
            "-L",
            self.server_name,
            "new-session",
            "-d",
            "-s",
            "test",
            "-x",
            str(self.width),
            "-y",
            str(self.height),
        ]
        if self.shell_command:
            cmd.append(self.shell_command)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not create tmux server: {result.stderr}")

        time.sleep(0.2)
        self.pane_id = subprocess.run(
            ["tmux", "-L", self.server_name, "list-panes", "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        ).stdout.strip()

    def tmx(self, *args):
        """Run a tmux command against this test server, return stdout."""
        return subprocess.run(
            ["tmux", "-L", self.server_name, *args],
            capture_output=True, text=True,
        ).stdout.strip()

    def stop(self):
        """Kill the tmux server."""
        subprocess.run(
            ["tmux", "-L", self.server_name, "kill-server"], capture_output=True
        )

    def send_keys(self, *args):
        """Send keys to the pane."""
        subprocess.run(
            ["tmux", "-L", self.server_name, "send-keys", "-t", self.pane_id]
            + list(args)
        )

    def get_cursor_position(self):
        """Get cursor position in copy mode."""
        result = subprocess.run(
            [
                "tmux",
                "-L",
                self.server_name,
                "display-message",
                "-t",
                self.pane_id,
                "-p",
                "#{copy_cursor_x},#{copy_cursor_y}",
            ],
            capture_output=True,
            text=True,
        )
        x, y = result.stdout.strip().split(",")
        return int(x), int(y)

    def split_window(self, horizontal=True):
        """Split the window to create a new pane.

        Args:
            horizontal: If True, split horizontally (panes side by side).
                       If False, split vertically (panes stacked).

        Returns:
            The pane_id of the newly created pane.
        """
        split_flag = "-h" if horizontal else "-v"
        result = subprocess.run(
            [
                "tmux",
                "-L",
                self.server_name,
                "split-window",
                split_flag,
                "-t",
                self.pane_id,
                "-P",
                "-F",
                "#{pane_id}",
            ],
            capture_output=True,
            text=True,
        )
        new_pane_id = result.stdout.strip()
        time.sleep(0.1)
        return new_pane_id

    def get_active_pane(self):
        """Get the currently active pane ID."""
        result = subprocess.run(
            ["tmux", "-L", self.server_name, "display-message", "-p", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def send_keys_to_pane(self, pane_id, *args):
        """Send keys to a specific pane."""
        subprocess.run(
            ["tmux", "-L", self.server_name, "send-keys", "-t", pane_id] + list(args)
        )

    def get_cursor_position_in_pane(self, pane_id):
        """Get cursor position in copy mode for a specific pane."""
        result = subprocess.run(
            [
                "tmux",
                "-L",
                self.server_name,
                "display-message",
                "-t",
                pane_id,
                "-p",
                "#{copy_cursor_x},#{copy_cursor_y}",
            ],
            capture_output=True,
            text=True,
        )
        x, y = result.stdout.strip().split(",")
        return int(x), int(y)

    def make_sh_for_server(self):
        """Create a sh() function that targets this test server.

        Returns a function that can be used to patch easymotion.sh,
        injecting -L server_name into tmux commands.
        """
        server_name = self.server_name

        def patched_sh(cmd: list) -> str:
            # Inject -L server_name after 'tmux' command
            if cmd and cmd[0] == "tmux":
                cmd = ["tmux", "-L", server_name] + cmd[1:]
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
    tmux_server.send_keys(f'printf "{content}"', "Enter")
    time.sleep(0.3)

    # Jump to line 2 (the wrapped portion with C's)
    target_line = 2
    target_col = 5

    # Call tmux_move_cursor with patched sh() and real pane state
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        tmux_move_cursor(pane, target_line, target_col)
        print("NAV_TRACE:", *easymotion.NAV_TRACE, sep="\n  ")

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
    assert_frozen_cursor_on_content(
        tmux_server, pane_id, pane.lines[target_line], target_col
    )


@requires_tmux
def test_cursor_jump_with_empty_top_rows():
    """Regression test: cursor-down propagated end-of-line bias on tmux 3.6+.

    When the top rows of the pane are empty, tmux's copy-mode cursor-down
    never primed its internal lastsx state, so cursor-down -N pulled the
    cursor to the end of every non-empty row it crossed. With ``pane.lines``
    populated, ``tmux_move_cursor`` must compensate so the user-visible
    landing matches (target_line, target_col).

    Uses a custom 80x20 server so the user's interactive shell prompt
    can't wrap into row 0 and defeat the empty-leading-row precondition
    on slower CI runners.
    """
    server = TmuxTestServer(width=80, height=20)
    try:
        server.start()
    except RuntimeError as e:
        pytest.skip(str(e))

    try:
        pane_id = server.pane_id

        # Stage content with leading blank line so screen row 0 is empty.
        # `clear` first wipes any prompt; sleep keeps the pane stable.
        target_marker = "TARGET_HERE"
        content_file = f"/tmp/easymotion_test_{uuid.uuid4().hex[:8]}.txt"
        with open(content_file, "w") as f:
            f.write(f"\nfirst content\nsecond content\nthird {target_marker} line\n")

        server.send_keys(f"clear; cat {content_file}; sleep 30", "Enter")

        pane = PaneInfo(
            pane_id, active=True, start_y=0, height=20, start_x=0, width=80
        )
        pane.copy_mode = False

        def capture_pane_lines():
            capture = subprocess.run(
                [
                    "tmux", "-L", server.server_name,
                    "capture-pane", "-p", "-t", pane_id,
                ],
                capture_output=True,
                text=True,
            ).stdout
            return capture[:-1].split("\n")[: pane.height]

        # Poll until the content appears and row 0 is empty. The pane
        # state isn't observable until the shell finishes processing the
        # typed command, which is timing-sensitive on slow CI runners.
        deadline = time.time() + 5.0
        while time.time() < deadline:
            pane.lines = capture_pane_lines()
            target_visible = any(target_marker in line for line in pane.lines)
            if target_visible and pane.lines[0] == "":
                break
            time.sleep(0.1)
        else:
            raise AssertionError(
                f"Test setup did not stabilise: pane.lines[0]={pane.lines[0]!r}, "
                f"target_visible="
                f"{any(target_marker in line for line in pane.lines)}"
            )

        target_line = next(
            i for i, line in enumerate(pane.lines) if target_marker in line
        )
        target_col = pane.lines[target_line].index(target_marker)

        with patch("easymotion.sh", server.make_sh_for_server()):
            pane = easymotion.get_initial_tmux_info()[0]
            pane.lines = tmux_capture_pane(pane)  # freezes the pane
            tmux_move_cursor(pane, target_line, target_col)

        time.sleep(0.1)

        cursor_x, cursor_y = server.get_cursor_position()
        assert cursor_y == target_line, (
            f"Cursor landed on row {cursor_y}, expected {target_line}. "
            f"This indicates cursor-right wrapped past end of row because "
            f"cursor-down ended at end-of-line instead of col 0."
        )
        assert cursor_x == target_col, (
            f"Cursor at col {cursor_x}, expected {target_col}"
        )
        assert_frozen_cursor_on_content(
            server, pane_id, pane.lines[target_line], target_col
        )
    finally:
        server.stop()


def assert_cursor_on_content(server, pane_id, expected_text, expected_col=None):
    """Assert the copy-mode cursor sits on the row whose CONTENT equals
    ``expected_text``, regardless of any view shift — coordinate-only
    assertions pass even when the jump landed on the wrong content (the
    view shifted underneath), so every jump test must verify content."""
    out = subprocess.run(
        ["tmux", "-L", server.server_name, "display-message", "-p", "-t", pane_id,
         "#{copy_cursor_y},#{copy_cursor_x},#{scroll_position},#{pane_height}"],
        capture_output=True, text=True).stdout.strip()
    y, x, scroll, height = (int(v or 0) for v in out.split(","))
    row_text = subprocess.run(
        ["tmux", "-L", server.server_name, "capture-pane", "-p", "-t", pane_id,
         "-S", str(-scroll), "-E", str(height - 1 - scroll)],
        capture_output=True, text=True).stdout.split("\n")[y]
    assert row_text.rstrip() == expected_text.rstrip(), (
        f"cursor on content {row_text.rstrip()!r}, expected "
        f"{expected_text.rstrip()!r} (y={y} scroll={scroll})"
    )
    if expected_col is not None:
        assert x == expected_col, f"cursor col {x}, expected {expected_col}"


def test_frozen_frame_path_is_server_scoped(monkeypatch):
    """Two tmux servers both have a pane %0 — their frozen-frame caches
    (legacy tmux < 3.6 path) must not collide (isolated test servers
    would otherwise clobber the user's real cache)."""
    from easymotion import _frozen_frame_path

    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,123,0")
    a = _frozen_frame_path("%0")
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/pytest_abc,456,0")
    b = _frozen_frame_path("%0")
    assert a != b, "cache path must be scoped to the tmux server"


def read_frozen_view_top(server):
    """What the user sees at the top of a frozen copy-mode view (read
    through the cursor; capture-pane cannot see frozen views)."""
    for c in ("clear-selection", "top-line", "start-of-line",
              "begin-selection", "end-of-line", "copy-selection-no-clear"):
        server.tmx("send-keys", "-X", "-t", server.pane_id, c)
    text = server.tmx("show-buffer")
    server.tmx("send-keys", "-X", "-t", server.pane_id, "clear-selection")
    return text


def assert_frozen_cursor_on_content(server, pane_id, expected_text, expected_col):
    """Frozen-frame variant: capture-pane reads the LIVE grid and cannot
    see a frozen copy-mode view, so read the content under the cursor
    through copy-mode itself (select to end of line -> buffer holds
    row[x:], calibrated on 3.4/3.6)."""
    def tmx(*args):
        return subprocess.run(
            ["tmux", "-L", server.server_name, *args],
            capture_output=True, text=True).stdout.strip()
    x = int(tmx("display-message", "-p", "-t", pane_id, "#{copy_cursor_x}") or 0)
    assert x == expected_col, f"cursor col {x}, expected {expected_col}"
    tmx("send-keys", "-X", "-t", pane_id, "begin-selection")
    tmx("send-keys", "-X", "-t", pane_id, "end-of-line")
    tmx("send-keys", "-X", "-t", pane_id, "copy-selection-no-clear")
    got = tmx("show-buffer")
    tmx("send-keys", "-X", "-t", pane_id, "clear-selection")
    want = expected_text[expected_col:].rstrip()
    # end-of-line runs to the LOGICAL line end: on a wrapped row the
    # selection continues into following screen rows, so compare prefix
    assert got.rstrip().startswith(want), (
        f"cursor-to-EOL is {got.rstrip()!r}, expected it to start with "
        f"{want!r} (frozen frame mismatch)"
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
    tmux_server.send_keys('echo "line0"', "Enter")
    tmux_server.send_keys('echo "line1"', "Enter")
    tmux_server.send_keys('echo "line2_target"', "Enter")
    time.sleep(0.2)

    # Call tmux_move_cursor with patched sh() and real pane state.
    # The target is derived from the captured content (real usage only
    # ever jumps to match positions) so the test is independent of the
    # shell prompt's row geometry.
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines) if ln == "line2_target"
        )
        target_col = pane.lines[target_line].index("target")
        tmux_move_cursor(pane, target_line, target_col)
        print("NAV_TRACE:", *easymotion.NAV_TRACE, sep="\n  ")

    time.sleep(0.1)

    # Verify cursor position
    cursor_x, cursor_y = tmux_server.get_cursor_position()
    assert cursor_y == target_line, (
        f"Cursor Y position wrong: expected {target_line}, got {cursor_y}"
    )
    assert cursor_x == target_col, (
        f"Cursor X position wrong: expected {target_col}, got {cursor_x}"
    )
    assert_frozen_cursor_on_content(
        tmux_server, pane_id, pane.lines[target_line], target_col
    )


@requires_tmux
def test_cross_pane_jump(tmux_server):
    """Integration test: verify tmux_move_cursor jumps to another pane correctly.

    This tests the core cross-pane feature: jumping from pane 1 to pane 2.
    """
    # Create pane 2 with vertical split (stacked)
    pane2_id = tmux_server.split_window(horizontal=False)
    time.sleep(0.2)

    # Add content to pane 2
    tmux_server.send_keys_to_pane(pane2_id, 'echo "line0"', "Enter")
    tmux_server.send_keys_to_pane(pane2_id, 'echo "line1_target"', "Enter")
    time.sleep(0.2)

    # Call tmux_move_cursor with patched sh() and real pane state;
    # target derived from content so shell prompt geometry can't put a
    # hardcoded coordinate past a row's end
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane2 = next(
            p for p in easymotion.get_initial_tmux_info()
            if p.pane_id == pane2_id
        )
        pane2.lines = tmux_capture_pane(pane2)
        target_line = next(
            i for i, ln in enumerate(pane2.lines) if ln == "line1_target"
        )
        target_col = pane2.lines[target_line].index("target")
        tmux_move_cursor(pane2, target_line, target_col)
        print("NAV_TRACE:", *easymotion.NAV_TRACE, sep="\n  ")

    time.sleep(0.1)

    # Verify pane2 is active (select-pane worked)
    assert tmux_server.get_active_pane() == pane2_id, (
        "Pane 2 should be active after jump"
    )

    # Verify cursor position
    cursor_x, cursor_y = tmux_server.get_cursor_position_in_pane(pane2_id)
    assert cursor_y == target_line, (
        f"Cursor Y position wrong: expected {target_line}, got {cursor_y}"
    )
    assert cursor_x == target_col, (
        f"Cursor X position wrong: expected {target_col}, got {cursor_x}"
    )
    assert_frozen_cursor_on_content(
        tmux_server, pane2_id, pane2.lines[target_line], target_col
    )


# =============================================================================
# Navigator regression tests: wrap-at-top shift, CI prompt geometry,
# copy-mode movement semantics, zero-width chars, pre-move guard
# =============================================================================


@requires_tmux
def test_cursor_jump_unscrolled_wrapped_top(tmux_server):
    """T2 — audit #1: pane NOT scrolled, but the visible top row is the
    continuation of a wrapped logical line (long line pushed into history).
    start-of-line at the top walks above the view and shifts scroll; blind
    row counting then lands on the wrong CONTENT."""
    pane_id = tmux_server.pane_id
    # a 70-char line wrapping to 3 rows (30-col pane) followed by tail
    # lines; then push filler lines until the wrapped line's LAST row is
    # the visible top (a continuation row) — probing instead of counting
    # keeps the fixture independent of the shell prompt's geometry
    tmux_server.send_keys(
        "clear; printf 'W%.0s' {1..70}; echo; "
        "for i in 1 2 3 4 5; do echo LINE_$i qq; done",
        "Enter",
    )
    time.sleep(0.5)

    def tmx(*args):
        return subprocess.run(
            ["tmux", "-L", tmux_server.server_name, *args],
            capture_output=True, text=True).stdout.strip()

    def top_is_wrap_continuation():
        """Detect via the mechanism itself: on a continuation top row,
        top-line + start-of-line scrolls the view; cancel restores."""
        tmx("copy-mode", "-t", pane_id)
        tmx("send-keys", "-X", "-t", pane_id, "top-line")
        tmx("send-keys", "-X", "-t", pane_id, "start-of-line")
        shifted = tmx("display-message", "-p", "-t", pane_id,
                      "#{scroll_position}") != "0"
        tmx("send-keys", "-X", "-t", pane_id, "cancel")
        return shifted

    for i in range(15):
        if top_is_wrap_continuation():
            break
        tmux_server.send_keys(f"echo FILL_{i}_mark", "Enter")
        time.sleep(0.15)
    else:
        pytest.skip("could not line up a wrap-continuation top row")

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        assert pane.scroll_position == 0
        pane.lines = tmux_capture_pane(pane)
        # target: a uniquely-identifiable visible row in the lower half
        target_line = max(
            i for i, ln in enumerate(pane.lines)
            if ln.startswith(("LINE_", "FILL_"))
        )
        expected = pane.lines[target_line]
        tmux_move_cursor(pane, target_line, 2)

    time.sleep(0.1)
    assert_frozen_cursor_on_content(tmux_server, pane_id, expected, 2)


@requires_tmux
def test_cursor_jump_ci_prompt_geometry():
    """T3 — the CI failure class: a long shell prompt makes command lines
    wrap in a narrow pane; once content scrolls into history the visible
    top row is a wrap continuation and jumps land on wrong content."""
    server = TmuxTestServer(
        width=30, height=10,
        shell_command=(
            "env PS1='runner@fv-az1234-5678-90:~/work$ ' "
            "bash --norc --noprofile -i"
        ),
    )
    try:
        server.start()
    except RuntimeError as e:
        pytest.skip(str(e))
    try:
        pane_id = server.pane_id
        for c in ('echo "line0"', 'echo "line1"', 'echo "line2_target"'):
            server.send_keys(c, "Enter")
        time.sleep(0.5)

        with patch("easymotion.sh", server.make_sh_for_server()):
            pane = easymotion.get_initial_tmux_info()[0]
            pane.lines = tmux_capture_pane(pane)
            target_line = next(
                i for i, ln in enumerate(pane.lines) if ln == "line2_target"
            )
            tmux_move_cursor(pane, target_line, 3)

        time.sleep(0.1)
        assert_frozen_cursor_on_content(server, pane_id, "line2_target", 3)
    finally:
        server.stop()


@requires_tmux
def test_copy_mode_movement_semantics(tmux_server):
    """T4 — lock the copy-mode semantics all movement math relies on:
    (a) -N k cursor-down moves k SCREEN rows, even across wrapped lines;
    (b) -N big cursor-right does NOT clamp at end of line — it wraps to
        following lines (so column overshoot becomes a wrong-line jump)."""

    tmx = tmux_server.tmx

    tmux_server.send_keys(
        "clear; printf 'AAA\\n'; printf 'B%.0s' {1..70}; "
        "printf '\\nCCC\\nDDD\\n'",
        "Enter",
    )
    time.sleep(0.4)
    tmx("copy-mode")
    # (a) screen-row stepping across the wrapped B-block (3 screen rows)
    tmx("send-keys", "-X", "top-line")
    tmx("send-keys", "-X", "start-of-line")
    tmx("send-keys", "-X", "-N", "4", "cursor-down")
    assert tmx("display-message", "-p", "#{copy_cursor_y}") == "4", (
        "cursor-down is expected to move per SCREEN row (wrapped rows "
        "counted individually); movement math depends on this"
    )
    # (b) cursor-right past EOL wraps instead of clamping
    tmx("send-keys", "-X", "top-line")
    tmx("send-keys", "-X", "start-of-line")
    tmx("send-keys", "-X", "-N", "30", "cursor-right")  # row 0 is 'AAA'
    y = int(tmx("display-message", "-p", "#{copy_cursor_y}"))
    assert y != 0, (
        "cursor-right at EOL is expected to WRAP to following lines, not "
        "clamp — column overshoot must therefore never be relied on to "
        "stay on the row"
    )
    tmx("send-keys", "-X", "cancel")


def test_zero_width_char_widths():
    """T5a — zero-width code points must count as width 0: tmux merges
    combining marks into the previous cell, and ZWJ/ZWSP/VS16 occupy no
    cell of their own."""
    from easymotion import _char_width_no_tab

    assert _char_width_no_tab("́") == 0  # combining acute
    assert _char_width_no_tab("‍") == 0  # ZWJ
    assert _char_width_no_tab("‌") == 0  # ZWNJ
    assert _char_width_no_tab("​") == 0  # ZWSP
    assert _char_width_no_tab("️") == 0  # VS16
    # ordinary chars unchanged
    assert _char_width_no_tab("a") == 1
    assert _char_width_no_tab("中") == 2
    assert get_string_width("aébx") == 4  # a,é,b,x = 4 cells


@requires_tmux
def test_cursor_jump_combining_chars(tmux_server):
    """T5b — a line containing a combining mark: the jump must land on the
    correct screen CELL. cursor-right steps once per cell (the combining
    mark rides along with its base char), while the capture string carries
    the combining mark as an extra character."""
    pane_id = tmux_server.pane_id
    # 'aébx' with decomposed é (e + U+0301): cells a|é|b|x
    tmux_server.send_keys("clear; printf 'ae\\xcc\\x81bx\\n'", "Enter")
    time.sleep(0.4)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        line = pane.lines[0]
        assert "́" in line, f"fixture drift: {line!r}"
        # jump to 'x': visual col from our width model
        visual_col = get_string_width(line[: line.index("x")])
        tmux_move_cursor(pane, 0, easymotion.get_true_position(line, visual_col))

    time.sleep(0.1)
    out = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{copy_cursor_x}"],
        capture_output=True, text=True).stdout.strip()
    assert int(out) == 3, (
        f"cursor cell {out}, expected 3 ('x' is the 4th cell: a|é|b|x)"
    )


# =============================================================================
# Freeze-first behavior locks (Phase 1: tests before the refactor).
# Green tests lock current behavior the refactor must preserve; xfail(strict)
# tests define the freeze-first target behavior (they flip when implemented).
#
# Probe results recorded 2026-07-18 (tmux 3.4 + 3.6a):
# - copy-mode freezes the view/coordinates at entry (locked by
#   test_copy_mode_freezes_view below).
# - #{copy_cursor_line} exists in the man page but evaluates EMPTY on both
#   versions — no absolute anchor for panes the USER froze before streaming
#   output arrived; that stays a known limitation.
# - naive delta-compensated capture (-S -delta) after freezing was off by
#   one row in a quick probe — the freeze/capture race compensation must be
#   locked by its own test during implementation, not assumed.
# =============================================================================


@requires_tmux
def test_copy_mode_freezes_view(tmux_server):
    """Semantics lock: after entering copy-mode, new pane output must NOT
    move the frozen view — cursor movement keeps operating on the frozen
    content (verified on tmux 3.4 and 3.6a; guards against version drift)."""

    tmx = tmux_server.tmx

    tmux_server.send_keys(
        "clear; for i in 1 2 3 4 5 6 7 8; do echo N_$i; done; "
        "sleep 1.2; echo NEW_1; echo NEW_2; echo NEW_3",
        "Enter",
    )
    time.sleep(0.4)
    tmx("copy-mode")
    tmx("send-keys", "-X", "top-line")
    tmx("send-keys", "-X", "start-of-line")
    tmx("send-keys", "-X", "-N", "3", "cursor-down")
    time.sleep(1.5)  # NEW lines arrive while frozen
    # cursor-down still moves in FROZEN coordinates: two rows below the
    # frozen row-3 content, regardless of the live grid having new rows
    tmx("send-keys", "-X", "-N", "2", "cursor-down")
    tmx("send-keys", "-X", "begin-selection")
    tmx("send-keys", "-X", "end-of-line")
    tmx("send-keys", "-X", "copy-selection-no-clear")
    line = tmx("show-buffer")
    tmx("send-keys", "-X", "cancel")
    # frozen rows: 0='' (clear) or prompt-dependent — assert relative
    # movement stayed within the N_* block captured at freeze
    assert line.startswith("N_"), (
        f"cursor left the frozen frame: {line!r} — copy-mode no longer "
        f"freezes coordinates on this tmux version"
    )


@requires_tmux
def test_capture_leaves_pane_mode_untouched(tmux_server):
    """Lock: capturing panes must not leave copy-mode enabled on panes
    that weren't in copy-mode (the freeze-first refactor must restore
    state on abort to keep this green)."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo CONTENT", "Enter")
    time.sleep(0.3)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        # simulate overlay abort: main() releases frozen panes
        easymotion.release_frozen([pane])
    in_mode = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{pane_in_mode}"],
        capture_output=True, text=True).stdout.strip()
    assert in_mode == "0"


@requires_tmux
def test_scrolled_jump_lands_after_buffer_growth(tmux_server):
    # not view-read gated: the landing assertion reads only ASCII rows,
    # which #{copy_cursor_line} returns correctly even on tmux < 3.6
    """Field incident: hints were right but the jump landed rows off on
    the SECOND trigger. The copy-mode buffer keeps growing at the bottom
    while frozen (streaming pane), so replaying goto-line with the
    captured scroll number repositions relative to the NEW bottom and
    shifts the view by however many rows arrived since. Navigation must
    land on the captured content regardless of growth."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys(
        "clear; for i in $(seq 1 30); do echo S_$i; done; "
        "sleep 1.2; for i in $(seq 31 60); do echo S_$i; sleep 0.05; done",
        "Enter",
    )
    time.sleep(0.4)
    tmux_server.tmx("copy-mode", "-t", pane_id)
    tmux_server.tmx("send-keys", "-X", "-t", pane_id, "-N", "8", "scroll-up")
    time.sleep(1.4)  # streaming has resumed while frozen

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines)
            if ln.startswith("S_") and i >= 2
        )
        expected = pane.lines[target_line]
        # the user reads the hints and picks one; the pane keeps
        # streaming under the freeze the whole time. Guard the premise:
        # the buffer bottom must actually grow between capture and jump,
        # or the regression under test isn't being exercised.
        hist_at_capture = int(tmux_server.tmx(
            "display-message", "-p", "-t", pane_id, "#{history_size}"))
        assert _wait_for(lambda: int(tmux_server.tmx(
            "display-message", "-p", "-t", pane_id, "#{history_size}"
        )) > hist_at_capture), "buffer did not grow during the hint window"
        tmux_move_cursor(pane, target_line, 1)

    time.sleep(0.1)
    landed = tmux_server.tmx(
        "display-message", "-p", "-t", pane_id, "#{copy_cursor_line}"
    ).rstrip()
    assert landed == expected, (
        f"cursor landed on {landed!r}, target was {expected!r}"
    )


@requires_tmux
def test_scrolled_jump_never_moves_scroll(tmux_server):
    """Design lock from the second field incident: goto-line's landing
    row is not reliable on long-frozen streaming panes, and the large
    scroll excursion the correction loop then performs re-anchors the
    frozen view against the grown buffer — same scroll NUMBER, shifted
    content. A jump within a scrolled frozen view must navigate
    relative to the current cursor and never issue scroll-moving
    commands (goto-line / scroll-up / scroll-down)."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; for i in $(seq 1 30); do echo S_$i; done",
                          "Enter")
    time.sleep(0.4)
    tmux_server.tmx("copy-mode", "-t", pane_id)
    tmux_server.tmx("send-keys", "-X", "-t", pane_id, "-N", "12", "scroll-up")
    time.sleep(0.2)

    issued = []
    real_sh = tmux_server.make_sh_for_server()

    def spy_sh(cmd):
        issued.append(cmd)
        return real_sh(cmd)

    with patch("easymotion.sh", spy_sh):
        pane = easymotion.get_initial_tmux_info()[0]
        assert pane.scroll_position == 12
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines) if ln.startswith("S_")
        )
        expected = pane.lines[target_line]
        issued.clear()
        tmux_move_cursor(pane, target_line, 1)

    flat = [tok for cmd in issued for tok in cmd]
    for forbidden in ("goto-line", "scroll-up", "scroll-down"):
        assert forbidden not in flat, (
            f"jump issued {forbidden!r} on a scrolled frozen pane: {issued}"
        )
    tmux_server.tmx("send-keys", "-X", "-t", pane_id, "toggle-position")
    landed = tmux_server.tmx(
        "display-message", "-p", "-t", pane_id,
        "#{scroll_position},#{copy_cursor_line}",
    )
    tmux_server.tmx("send-keys", "-X", "-t", pane_id, "toggle-position")
    scroll_now, line_now = landed.split(",", 1)
    assert scroll_now == "12", f"scroll moved to {scroll_now}"
    assert line_now.rstrip() == expected, (
        f"cursor on {line_now.rstrip()!r}, target {expected!r}"
    )


@requires_tmux
def test_release_keeps_scrolled_pane_frozen(tmux_server):
    """Field report: pane A stays frozen after a previous jump (carrying
    our marker); the user scrolls up inside it to read, then triggers
    again and jumps to pane B. Releasing must NOT cancel A — the user
    demonstrably scrolled it to look at something, and cancelling dumps
    them back to the live bottom. Only unscrolled panes we froze are
    returned to live view."""
    pane_a = tmux_server.pane_id
    pane_b = tmux_server.split_window()
    tmux_server.send_keys("clear; for i in $(seq 1 30); do echo A_$i; done",
                          "Enter")
    tmux_server.send_keys_to_pane(pane_b, "clear; echo B_target", "Enter")
    time.sleep(0.4)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        # session 1: freeze all, jump INTO pane A (A kept frozen+marked)
        panes = easymotion.get_initial_tmux_info()
        for p in panes:
            p.lines = tmux_capture_pane(p)
        pa = next(p for p in panes if p.pane_id == pane_a)
        target = next(i for i, ln in enumerate(pa.lines)
                      if ln.startswith("A_"))
        easymotion.release_frozen(panes, keep=pa)
        tmux_move_cursor(pa, target, 1)

    # the user scrolls up inside the kept frozen pane to read
    tmux_server.tmx("send-keys", "-X", "-t", pane_a, "-N", "10", "scroll-up")
    time.sleep(0.2)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        # session 2: re-trigger, jump to pane B this time
        panes = easymotion.get_initial_tmux_info()
        for p in panes:
            p.lines = tmux_capture_pane(p)
        pb = next(p for p in panes if p.pane_id == pane_b)
        target = next(i for i, ln in enumerate(pb.lines)
                      if ln.startswith("B_"))
        easymotion.release_frozen(panes, keep=pb)
        tmux_move_cursor(pb, target, 1)

    state = tmux_server.tmx(
        "display-message", "-p", "-t", pane_a,
        "#{pane_in_mode},#{scroll_position}",
    )
    assert state == "1,10", (
        f"scrolled pane A was dumped out of its frozen view: {state!r}"
    )


@requires_tmux
def test_jump_preserves_user_scroll(tmux_server):
    """Lock: jumping within a pane the USER scrolled must leave the pane
    at that scroll position — their view of history is not lost."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; for i in $(seq 1 30); do echo S_$i; done",
                          "Enter")
    time.sleep(0.4)
    subprocess.run(["tmux", "-L", tmux_server.server_name, "copy-mode",
                    "-t", pane_id], check=True)
    subprocess.run(["tmux", "-L", tmux_server.server_name, "send-keys",
                    "-X", "-t", pane_id, "-N", "12", "scroll-up"], check=True)
    time.sleep(0.2)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        assert pane.scroll_position == 12
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines) if ln.startswith("S_")
        )
        tmux_move_cursor(pane, target_line, 1)
    time.sleep(0.1)
    scroll = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{scroll_position}"],
        capture_output=True, text=True).stdout.strip()
    assert scroll == "12", f"user's scroll lost: now {scroll}"


@requires_tmux
def test_jump_reaches_content_scrolled_out_during_selection(tmux_server):
    """Freeze-first target behavior: if streamed output pushes the aimed
    row out of the live view while the user is picking a hint, the jump
    must still land on it — the frozen frame keeps it reachable. (Current
    architecture must cancel here: retargeting can't reach off-view rows.)
    """
    pane_id = tmux_server.pane_id
    tmux_server.send_keys(
        "clear; echo TOP_TARGET; for i in 1 2 3 4 5 6 7 8; do echo PAD_$i; "
        "done; sleep 1.2; for i in 1 2 3 4 5; do echo DRIFT_$i; done",
        "Enter",
    )
    time.sleep(0.4)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines) if ln == "TOP_TARGET"
        )
        time.sleep(1.5)  # DRIFT pushes TOP_TARGET above the live view
        tmux_move_cursor(pane, target_line, 2)
    time.sleep(0.1)
    in_mode = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{pane_in_mode}"],
        capture_output=True, text=True).stdout.strip()
    assert in_mode == "1", "jump was cancelled; frozen frame should keep it reachable"
    assert_frozen_cursor_on_content(tmux_server, pane_id, "TOP_TARGET", 2)


@requires_tmux
def test_inplace_rewrite_jump_succeeds(tmux_server):
    """Freeze-first target behavior: a TUI rewriting its screen in place
    must not prevent the jump — the frozen frame is what the user saw and
    aimed at."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys(
        "clear; echo ROW_A; echo ROW_B; echo ROW_C; "
        "sleep 1.2; tput cuu 3; echo SHIFTED_X; echo ROW_A2",
        "Enter",
    )
    time.sleep(0.4)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        target_line = next(i for i, ln in enumerate(pane.lines) if ln == "ROW_B")
        time.sleep(1.4)  # in-place rewrite happens
        tmux_move_cursor(pane, target_line, 1)
    time.sleep(0.1)
    in_mode = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{pane_in_mode}"],
        capture_output=True, text=True).stdout.strip()
    assert in_mode == "1", "jump cancelled; frozen frame should make it succeed"
    assert_frozen_cursor_on_content(tmux_server, pane_id, "ROW_B", 1)


@requires_tmux
def test_capture_freezes_pane(tmux_server):
    """Freeze-first target behavior: capturing for the overlay puts the
    pane into copy-mode (freezing its view for the whole hint-selection
    window). Restoration on abort is locked separately by
    test_capture_leaves_pane_mode_untouched once a release API exists."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo CONTENT", "Enter")
    time.sleep(0.3)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        in_mode = subprocess.run(
            ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
             "-t", pane_id, "#{pane_in_mode}"],
            capture_output=True, text=True).stdout.strip()
    assert in_mode == "1", "capture should freeze the pane in copy-mode"


@requires_tmux
def test_jump_follows_streamed_content(tmux_server):
    """A streaming pane (ping, tail -f) pushes rows into history between
    capture and jump. Cancelling every jump would make such panes
    un-jumpable; instead the jump must RETARGET: the captured row's
    content moved up by exactly the history growth, so land on the same
    CONTENT at its new row."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys(
        "clear; for i in 1 2 3 4 5 6 7 8 9 10; do echo BASE_$i; done; "
        "sleep 1.2; echo DRIFT_1; echo DRIFT_2",
        "Enter",
    )
    time.sleep(0.4)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        target_line = next(
            i for i, ln in enumerate(pane.lines) if ln == "BASE_7"
        )
        time.sleep(1.4)  # DRIFT lines arrive: content shifts up
        tmux_move_cursor(pane, target_line, 2)
        print("NAV_TRACE:", *easymotion.NAV_TRACE, sep="\n  ")

    time.sleep(0.1)
    # must have jumped (not cancelled) and be sitting on BASE_7's content
    in_mode = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{pane_in_mode}"],
        capture_output=True, text=True).stdout.strip()
    assert in_mode == "1", "jump was cancelled; frozen coordinates should hold"
    assert_frozen_cursor_on_content(tmux_server, pane_id, "BASE_7", 2)


# =============================================================================
# Overlay-interaction locks (search character typed INSIDE the overlay).
# Target flow: binding opens the overlay focused (no -d) -> panes freeze &
# the frozen frame draws -> the search char and hint keys are read from the
# overlay's own stdin. Early keystrokes buffer in the overlay pty, so
# nothing leaks into the user's shell and the freeze covers the entire
# target-selection window.
# =============================================================================

EASYMOTION_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "easymotion.py")


def _wait_for(cond, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


class OverlayHarness:
    """Drive a real easymotion overlay end-to-end on an isolated server."""

    def __init__(self, server):
        self.server = server

    def tmx(self, *args):
        return self.server.tmx(*args)

    def launch(self, mode="s"):
        self.tmx("set-option", "-g", "@easymotion-debug", "true")
        src = self.tmx("display-message", "-p", "-t",
                       self.server.pane_id, "#{window_id}")
        self.window_id = self.tmx(
            "new-window", "-d", "-P", "-F", "#{window_id}",
            f"python3 {EASYMOTION_PY} {mode} --source {src}")
        self.overlay_pane = self.tmx(
            "list-panes", "-t", self.window_id, "-F", "#{pane_id}")
        return self.window_id

    def send(self, key):
        self.tmx("send-keys", "-t", self.overlay_pane, "-l", key)

    def send_until_gone(self, key, timeout=6.0, resend_every=1.0):
        """send-keys to a pane with no attached client can drop a key on
        heavily loaded machines (observed on CI runners and under local
        load; a real user's keystrokes travel the attached-client path
        instead). Resend until the overlay reacts — consumption order is
        still what the assertions verify."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.send(key)
            if _wait_for(lambda: not self.alive(), resend_every):
                return True
        return self.wait_gone(0.1)  # raises with diagnostics

    def alive(self):
        return self.window_id in self.tmx("list-windows", "-F", "#{window_id}")

    def wait_gone(self, timeout=5.0):
        if _wait_for(lambda: not self.alive(), timeout):
            return True
        # timed out: surface overlay state + log for CI diagnostics
        screen = self.tmx("capture-pane", "-p", "-t", self.overlay_pane)
        state = self.tmx(
            "display-message", "-p", "-t", self.overlay_pane,
            "in_mode=#{pane_in_mode} dead=#{pane_dead} "
            "cmd=#{pane_current_command} pid=#{pane_pid}")
        try:
            ps = subprocess.run(
                ["ps", "-o", "pid,stat,wchan,command", "-p",
                 state.split("pid=")[-1]],
                capture_output=True, text=True).stdout
        except Exception as exc:
            ps = f"<ps failed: {exc}>"
        try:
            with open(os.path.expanduser("~/easymotion.log")) as f:
                log_tail = "".join(f.readlines()[-60:])
        except OSError as exc:
            log_tail = f"<no log: {exc}>"
        raise AssertionError(
            f"overlay still open after {timeout}s; {state}\nps: {ps}\n"
            f"screen:\n{screen}\n--- easymotion.log tail:\n{log_tail}"
        )

    def pane_in_mode(self, pane_id):
        return self.tmx("display-message", "-p", "-t", pane_id,
                        "#{pane_in_mode}") == "1"


@requires_tmux
def test_overlay_freezes_before_char_input(tmux_server):
    """N1: opening the overlay freezes the panes BEFORE any search
    character is typed — the whole target-picking window views one frame."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys(
        "i=0; while true; do i=$((i+1)); echo STREAM_$i; sleep 0.3; done",
        "Enter")
    time.sleep(1)
    h = OverlayHarness(tmux_server)
    h.launch("s")
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 3.0), (
        "source pane should be frozen (copy-mode) before any char is typed"
    )
    assert h.send_until_gone("q")  # no match -> overlay exits


@requires_tmux
def test_overlay_char_then_hint_jump(tmux_server):
    """N2: full flow — open overlay, type the search char, single match
    jumps directly onto the frozen target."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo alpha; echo bravo_Zed; echo charlie",
                          "Enter")
    time.sleep(0.4)
    h = OverlayHarness(tmux_server)
    h.launch("s")
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 3.0)
    assert h.send_until_gone("Z"), "overlay should close after the jump"
    assert h.pane_in_mode(pane_id)
    assert_frozen_cursor_on_content(tmux_server, pane_id, "bravo_Zed", 6)


@requires_tmux
def test_overlay_s2_double_char(tmux_server):
    """N3: s2 reads two chars from the overlay stdin — no command-prompt
    round-trips, no server-global temp option."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo alpha; echo bravo_Zx1; echo charlie",
                          "Enter")
    time.sleep(0.4)
    h = OverlayHarness(tmux_server)
    h.launch("s2")
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 3.0)
    assert h.send_until_gone("Zx"), "overlay should close after the jump"
    assert_frozen_cursor_on_content(tmux_server, pane_id, "bravo_Zx1", 6)
    # the legacy temp option must not exist anywhere
    opt = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "show-options", "-g"],
        capture_output=True, text=True).stdout
    assert "_easymotion_tmp" not in opt


@requires_tmux
def test_overlay_cancel_releases(tmux_server):
    """N4: cancelling at the search prompt (Ctrl-C) closes the overlay
    and releases every pane we froze."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo CONTENT", "Enter")
    time.sleep(0.3)
    h = OverlayHarness(tmux_server)
    h.launch("s")
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 3.0)
    deadline = time.time() + 6
    while h.alive() and time.time() < deadline:
        h.tmx("send-keys", "-t", h.overlay_pane, "C-c")
        time.sleep(0.5)
    assert h.wait_gone(0.1), "overlay should exit on Ctrl-C"
    assert _wait_for(lambda: not h.pane_in_mode(pane_id), 3.0), (
        "frozen pane must be released on cancel"
    )


@requires_tmux
def test_overlay_no_match_releases(tmux_server):
    """N5: a search char with no matches closes the overlay and releases
    frozen panes."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo aaaa", "Enter")
    time.sleep(0.3)
    h = OverlayHarness(tmux_server)
    h.launch("s")
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 3.0)
    assert h.send_until_gone("z")
    assert _wait_for(lambda: not h.pane_in_mode(pane_id), 3.0)


@requires_tmux
def test_overlay_early_keys_not_leaked(tmux_server):
    """N6: keys typed immediately after the binding (before the frame is
    drawn) buffer in the focused overlay pty — consumed in order, never
    leaked into the user's shell."""
    pane_id = tmux_server.pane_id
    tmux_server.send_keys("clear; echo alpha; echo bravo_Zed; echo charlie",
                          "Enter")
    time.sleep(0.4)
    before = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "capture-pane", "-p",
         "-t", pane_id], capture_output=True, text=True).stdout
    h = OverlayHarness(tmux_server)
    h.launch("s")
    # deterministic "raw mode active" signal: stdin switches to raw
    # before the startup query, and the query is what freezes the pane —
    # so in_mode==1 guarantees the key lands in the raw input queue, yet
    # the frame (drawn after all captures) is typically not up yet.
    assert _wait_for(lambda: h.pane_in_mode(pane_id), 5.0)
    assert h.send_until_gone("Z"), "early key should drive the jump"
    assert h.pane_in_mode(pane_id)
    assert_frozen_cursor_on_content(tmux_server, pane_id, "bravo_Zed", 6)
    after = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "capture-pane", "-p",
         "-t", pane_id], capture_output=True, text=True).stdout
    assert after == before, "early keystroke leaked into the source pane"


@requires_tmux
def test_recapture_of_our_frozen_pane_uses_frozen_frame(tmux_server):
    """Retrigger while a pane is still frozen from OUR previous jump: the
    user is looking at the frozen frame, so the new capture must
    reconstruct THAT frame — not the live grid that kept moving. We know
    the freeze-time history size (stored as a pane option), so the live
    grid can be captured at the right offset."""
    tmux_server.send_keys(
        "clear; echo OLD_A; echo OLD_B; echo OLD_C; "
        "sleep 1.2; echo NEW_1; echo NEW_2; echo NEW_3; echo NEW_4",
        "Enter",
    )
    time.sleep(0.4)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        first = tmux_capture_pane(pane)  # freezes; frame has OLD_* only
        assert any(ln == "OLD_B" for ln in first)
        assert not any(ln.startswith("NEW_") for ln in first)
        # jump leaves the pane frozen (this is the normal flow)
        target = next(i for i, ln in enumerate(first) if ln == "OLD_B")
        pane.lines = first
        tmux_move_cursor(pane, target, 1)

        time.sleep(1.5)  # NEW_* lands on the LIVE grid; frozen view unchanged

        # retrigger: fresh process = fresh pane info + capture
        pane2 = easymotion.get_initial_tmux_info()[0]
        second = tmux_capture_pane(pane2)
    assert any(ln == "OLD_B" for ln in second), (
        "recapture lost the frozen frame the user is looking at"
    )
    assert not any(ln.startswith("NEW_") for ln in second), (
        f"recapture shows LIVE content, not the frozen frame: {second!r}"
    )


@requires_tmux
def test_capture_of_user_scrolled_pane_matches_their_view(tmux_server):
    """The user scrolled back themselves (their own copy-mode freeze) and
    the pane kept streaming: their frozen view is CONTENT-anchored while
    capture-pane offsets are live-relative — capturing at -scroll shows
    far newer content than what they see. The capture must locate their
    view by content anchors and return the frame they are looking at."""
    tmux_server.send_keys(
        "clear; for i in $(seq 1 30); do echo N_$i; done; "
        "sleep 1.2; for i in $(seq 31 40); do echo N_$i; done",
        "Enter",
    )
    time.sleep(0.4)
    sn = tmux_server.server_name
    subprocess.run(["tmux", "-L", sn, "copy-mode", "-t", tmux_server.pane_id],
                   check=True)
    subprocess.run(["tmux", "-L", sn, "send-keys", "-X", "-t",
                    tmux_server.pane_id, "-N", "5", "scroll-up"], check=True)
    seen_top = read_frozen_view_top(tmux_server)
    time.sleep(1.5)  # N_31..N_40 stream in while they look at old content

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        frame = tmux_capture_pane(pane)
    assert frame[0].strip() == seen_top, (
        f"capture shows {frame[0].strip()!r} at the top; the user is "
        f"looking at {seen_top!r}"
    )
    # the anchor reads must not leave an active selection behind — the
    # user would find their pane in "select mode"
    assert tmux_server.tmx(
        "display-message", "-p", "-t", tmux_server.pane_id,
        "#{selection_present}",
    ) in ("0", ""), "anchor reads left an active selection"


@requires_tmux
def test_recapture_after_user_scrolls_within_our_freeze(tmux_server):
    """After our jump the pane stays frozen; the user then scrolls UP
    within that frozen snapshot and re-triggers. The capture must show
    the part of the snapshot they scrolled to — not the cached screen
    frame, and not live-relative content."""
    tmux_server.send_keys(
        "clear; for i in $(seq 1 30); do echo N_$i; done; "
        "sleep 1.6; for i in $(seq 31 36); do echo N_$i; done",
        "Enter",
    )
    time.sleep(0.4)
    sn = tmux_server.server_name

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        first = tmux_capture_pane(pane)  # our freeze at scroll 0
        pane.lines = first
        target = next(i for i, ln in enumerate(first) if ln.startswith("N_"))
        tmux_move_cursor(pane, target, 1)  # pane stays frozen

        # the user scrolls up 8 rows inside the frozen snapshot
        subprocess.run(["tmux", "-L", sn, "send-keys", "-X", "-t",
                        pane.pane_id, "-N", "8", "scroll-up"], check=True)
        seen_top = read_frozen_view_top(tmux_server)
        time.sleep(1.8)  # N_31.. streams into the LIVE grid meanwhile

        pane2 = easymotion.get_initial_tmux_info()[0]
        frame = tmux_capture_pane(pane2)
    assert frame[0].strip() == seen_top, (
        f"capture top is {frame[0].strip()!r}; the user sees {seen_top!r}"
    )


@requires_tmux
def test_scrolled_jump_wide_chars_and_giant_bottom_wrap(tmux_server):
    """Field geometry (Claude Code emits 100+-row logical lines): the
    scrolled view sits ENTIRELY inside one giant wrapped logical line
    containing wide chars. start-of-line at the bottom anchor walks
    above the view top (shifting scroll), and a cells-as-steps column
    correction overshoots on the wide chars and wraps to the next row."""
    # one logical line of ~200 repetitions of '中x' (3 cells each) with a
    # unique marker every stretch; wraps to ~15 rows in the 30-col pane
    tmux_server.send_keys(
        "clear; for i in $(seq 1 40); do printf 'M%02d\u4e2dx\u4e2d' $i; done",
        "Enter",
    )
    time.sleep(0.6)
    sn = tmux_server.server_name
    subprocess.run(["tmux", "-L", sn, "copy-mode", "-t", tmux_server.pane_id],
                   check=True)
    subprocess.run(["tmux", "-L", sn, "send-keys", "-X", "-t",
                    tmux_server.pane_id, "-N", "3", "scroll-up"], check=True)
    time.sleep(0.2)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        # target: an 'x' on a mid-view row full of wide chars
        target_line = next(
            i for i in range(2, pane.height)
            if "x" in pane.lines[i] and "中" in pane.lines[i]
        )
        line = pane.lines[target_line]
        true_col = line.rindex("x")
        tmux_move_cursor(pane, target_line, true_col)

    time.sleep(0.1)
    assert_frozen_cursor_on_content(
        tmux_server, tmux_server.pane_id, line,
        get_string_width(line[:true_col]),
    )


def read_frozen_view(server, height):
    """Ground truth: what the frozen copy-mode view actually shows, read
    row by row through #{copy_cursor_line} (a SCREEN row, not the logical
    line — verified on tmux 3.4 and 3.6a). The position indicator is
    rendered into the view's top row, so it is toggled off for the read."""
    pid = server.pane_id
    server.tmx("send-keys", "-X", "-t", pid, "toggle-position")
    rows = []
    server.tmx("send-keys", "-X", "-t", pid, "top-line")
    for i in range(height):
        rows.append(server.tmx(
            "display-message", "-p", "-t", pid, "#{copy_cursor_line}"
        ).rstrip())
        if i < height - 1:
            server.tmx("send-keys", "-X", "-t", pid, "cursor-down")
    server.tmx("send-keys", "-X", "-t", pid, "toggle-position")
    return rows


@requires_tmux
@requires_view_read
def test_refrozen_capture_matches_view_after_reflow(tmux_server):
    """Field incident 2026-07-19: the frozen view drifted progressively
    (+1 row per long paragraph) against our recapture. That signature is
    a scrollback REWRAP: any width change while frozen (border drag, a
    different-sized client attaching, window-size latest across
    sessions) rewraps live history in place — row counts shift at every
    wrap point, history_size moves without any output, and no scalar
    delta can realign snapshot coordinates with the live grid. The
    recapture must equal the frozen view itself, row for row."""
    tmux_server.send_keys(
        "clear; for i in $(seq 1 12); do echo hist$i; done; "
        "echo LONG$(printf 'x%.0s' {1..50}); "
        "for i in $(seq 13 24); do echo hist$i; done",
        "Enter",
    )
    time.sleep(0.5)
    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        first = tmux_capture_pane(pane)  # our freeze
        pane.lines = first
        target = next(i for i, ln in enumerate(first) if ln.strip())
        tmux_move_cursor(pane, target, 1)  # pane stays frozen

        # the user scrolls up inside the frozen snapshot, then the
        # window width changes (e.g. another client attaches): tmux
        # rewraps the scrollback under the frozen view
        tmux_server.tmx("send-keys", "-X", "-t", tmux_server.pane_id,
                        "-N", "8", "scroll-up")
        tmux_server.tmx("resize-window", "-t", "test", "-x", "24", "-y", "10")
        time.sleep(0.3)

        pane2 = easymotion.get_initial_tmux_info()[0]
        frame = tmux_capture_pane(pane2)

    view = read_frozen_view(tmux_server, pane2.height)
    assert [r.rstrip() for r in frame] == view, (
        "recapture does not match the frozen view the user sees:\n"
        + "\n".join(
            f"  row{i}: frame={f!r:24} view={v!r}"
            for i, (f, v) in enumerate(zip(frame, view))
        )
    )


@requires_tmux
@requires_view_read
def test_refrozen_capture_matches_view_after_tui_rewrite(tmux_server):
    """Companion regression guard: a TUI erases and rewrites its screen
    in place after our freeze while streaming on, and the user scrolls
    back within the frozen snapshot. The recapture must equal the frozen
    view row for row (this geometry exercises the history/screen-band
    seam of the snapshot)."""
    writer = (
        "import sys,time\n"
        "w=sys.stdout\n"
        "for i in range(1,31): w.write(f'hist{i}\\n')\n"
        "w.write('DIRTY_A\\nDIRTY_DUP\\nDIRTY_DUP\\nDIRTY_B\\n'); w.flush()\n"
        "time.sleep(2.5)\n"
        "w.write('\\x1b[4A\\x1b[0J')\n"  # erase the dirty block in place
        "w.write('CLEAN_A\\nCLEAN_extra\\nCLEAN_B\\nCLEAN_C\\nCLEAN_D\\n')\n"
        "w.flush()\n"
        "for i in range(1,21):\n"
        "    w.write(f'tail{i}\\n'); w.flush(); time.sleep(0.03)\n"
    )
    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False
    ) as f:
        f.write(writer)
        writer_path = f.name
    tmux_server.send_keys(f"clear; python3 {writer_path}", "Enter")
    _wait_for(
        lambda: "DIRTY_B" in tmux_server.tmx(
            "capture-pane", "-p", "-t", tmux_server.pane_id
        ),
    )

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        first = tmux_capture_pane(pane)  # our freeze, dirty frame
        assert any("DIRTY_DUP" in ln for ln in first)
        pane.lines = first
        target = next(i for i, ln in enumerate(first) if "DIRTY_A" in ln)
        tmux_move_cursor(pane, target, 1)  # pane stays frozen

        # the TUI rewrites in place and streams on while we are frozen
        _wait_for(
            lambda: "tail20" in tmux_server.tmx(
                "capture-pane", "-p", "-t", tmux_server.pane_id
            ),
        )
        # the user scrolls up inside the frozen snapshot; the view now
        # straddles history rows AND the frozen screen band (the band
        # is where in-place rewrites break live-grid arithmetic)
        tmux_server.tmx("send-keys", "-X", "-t", tmux_server.pane_id,
                        "-N", "6", "scroll-up")

        pane2 = easymotion.get_initial_tmux_info()[0]
        frame = tmux_capture_pane(pane2)

    view = read_frozen_view(tmux_server, pane2.height)
    assert [r.rstrip() for r in frame] == view, (
        "recapture does not match the frozen view the user sees:\n"
        + "\n".join(
            f"  row{i}: frame={f!r:24} view={v!r}"
            for i, (f, v) in enumerate(zip(frame, view))
        )
    )


# =============================================================================
# Integration Tests - get_tmux_option and Config
# =============================================================================


@requires_tmux
def test_get_tmux_option_reads_value(tmux_server):
    """Integration test: verify get_tmux_option reads tmux options correctly."""
    # Clear cache to ensure fresh read
    _clear_options_cache()

    # Set a custom tmux option
    test_value = f"test_hints_{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "tmux",
            "-L",
            tmux_server.server_name,
            "set-option",
            "-g",
            "@easymotion-test-option",
            test_value,
        ],
        check=True,
    )

    # Patch subprocess.run to use our test server
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == "tmux" and "show-options" in cmd:
            # Add server flag to the command
            new_cmd = ["tmux", "-L", tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", patched_run):
        result = get_tmux_option("@easymotion-test-option", "default")

    assert result == test_value, f"Expected '{test_value}', got '{result}'"


@requires_tmux
def test_get_tmux_option_returns_default(tmux_server):
    """Integration test: verify get_tmux_option returns default when option not set."""
    # Clear cache to ensure fresh read
    _clear_options_cache()

    # Use an option name that definitely doesn't exist
    nonexistent_option = f"@easymotion-nonexistent-{uuid.uuid4().hex}"
    default_value = "my_default_value"

    # Patch subprocess.run to use our test server
    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == "tmux" and "show-options" in cmd:
            new_cmd = ["tmux", "-L", tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", patched_run):
        result = get_tmux_option(nonexistent_option, default_value)

    assert result == default_value, (
        f"Expected default '{default_value}', got '{result}'"
    )


@requires_tmux
def test_get_startup_info(tmux_server):
    """Integration test: the single batched startup query must yield the
    same options, panes, window id and version as the individual calls."""
    subprocess.run(
        ["tmux", "-L", tmux_server.server_name,
         "set-option", "-g", "@easymotion-hints", "xyz"],
        check=True,
    )
    _clear_options_cache()
    try:
        # TMUX_PANE from the developer's own tmux session would point at a
        # pane that doesn't exist on the isolated test server
        with patch("easymotion.sh", tmux_server.make_sh_for_server()), \
                patch.dict("os.environ", {"TMUX_PANE": ""}):
            info = get_startup_info()

        assert info is not None
        assert info.panes_info is not None
        assert [p.pane_id for p in info.panes_info] == [tmux_server.pane_id]
        pane = info.panes_info[0]
        assert pane.active and pane.width == tmux_server.width
        assert info.window_id.startswith("@")
        # detached test server has no attached client
        assert info.terminal_size is None
        # options were primed from the batch — no extra subprocess needed
        assert get_tmux_option("@easymotion-hints", "") == "xyz"
        assert easymotion.TMUX_VERSION is not None
        assert easymotion.TMUX_VERSION >= (0, 0)
    finally:
        _clear_options_cache()
        easymotion.TMUX_VERSION = None


def test_setup_logging_survives_early_logging_call(tmp_path, monkeypatch):
    """Regression: a logging call before setup_logging (e.g. sh() debug
    logging inside the batched startup query) auto-installs a stderr
    handler; without force=True the later basicConfig(filename=...) is a
    silent no-op and the perf/debug log is never written."""
    import logging

    log_file = tmp_path / "easymotion.log"
    monkeypatch.setattr(
        "os.path.expanduser", lambda p: str(log_file) if p.startswith("~") else p
    )
    monkeypatch.setattr(easymotion, "_tmux_options", {"@easymotion-perf": "true"})
    root = logging.getLogger()
    saved_handlers, root.handlers = root.handlers, []
    saved_disabled = root.disabled
    try:
        logging.debug("early call before setup_logging")  # installs stderr handler
        easymotion.setup_logging()
        logging.info("after setup_logging")
        logging.shutdown()
        assert log_file.exists() and "after setup_logging" in log_file.read_text()
    finally:
        for h in root.handlers:
            h.close()
        root.handlers = saved_handlers
        root.disabled = saved_disabled


@requires_tmux
def test_cursor_jump_scrolled_with_wrapped_top(tmux_server):
    """Regression: in a scrolled pane whose visible TOP row is the
    continuation of a wrapped logical line, start-of-line walks above the
    view and shifts scroll_position — row counts based on the captured
    view were then off by the shift, landing the jump on the wrong line."""
    pane_id = tmux_server.pane_id

    def tmx(*args):
        return subprocess.run(
            ["tmux", "-L", tmux_server.server_name, *args],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    # one line wide enough to wrap (30-col test pane), then numbered lines
    tmux_server.send_keys("clear; printf 'W%.0s' {1..70}; echo; "
                          "for i in {1..20}; do echo LINE_$i; done", "Enter")
    time.sleep(0.4)
    tmx("copy-mode", "-t", pane_id)

    # find a scroll position whose visible top row is a wrap continuation:
    # there, top-line + start-of-line walks above the view and shifts
    # scroll — the exact condition under test
    trigger_scroll = None
    for s in range(1, 30):
        tmx("send-keys", "-X", "-t", pane_id, "-N", "99", "scroll-down")
        tmx("send-keys", "-X", "-t", pane_id, "-N", str(s), "scroll-up")
        before = tmx("display-message", "-p", "-t", pane_id,
                     "#{scroll_position}")
        if before != str(s):  # clamped: ran out of history
            break
        tmx("send-keys", "-X", "-t", pane_id, "top-line")
        tmx("send-keys", "-X", "-t", pane_id, "start-of-line")
        after = tmx("display-message", "-p", "-t", pane_id,
                    "#{scroll_position}")
        if after != before:
            trigger_scroll = s
            break
    assert trigger_scroll is not None, "no wrap-continuation top row found"

    # restore the trigger scroll state
    tmx("send-keys", "-X", "-t", pane_id, "-N", "99", "scroll-down")
    tmx("send-keys", "-X", "-t", pane_id, "-N", str(trigger_scroll), "scroll-up")
    time.sleep(0.1)

    with patch("easymotion.sh", tmux_server.make_sh_for_server()):
        pane = easymotion.get_initial_tmux_info()[0]
        pane.lines = tmux_capture_pane(pane)
        # pick a stable target: first LINE_ row in the captured view
        target_line = next(i for i, ln in enumerate(pane.lines)
                           if ln.startswith("LINE_"))
        expected_text = pane.lines[target_line]
        tmux_move_cursor(pane, target_line, 2)

    time.sleep(0.2)
    # verify the cursor sits on the expected content line, regardless of
    # any view shift: read the char under the cursor's row via the
    # cursor-relative capture
    out = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "display-message", "-p",
         "-t", pane_id, "#{copy_cursor_y},#{copy_cursor_x},#{scroll_position}"],
        capture_output=True, text=True).stdout.strip()
    y, x, scroll = (int(v or 0) for v in out.split(","))
    assert x == 2
    row_text = subprocess.run(
        ["tmux", "-L", tmux_server.server_name, "capture-pane", "-p",
         "-t", pane_id, "-S", str(-scroll),
         "-E", str(pane.height - 1 - scroll)],
        capture_output=True, text=True).stdout.split("\n")[y]
    assert row_text.rstrip() == expected_text.rstrip()


def test_get_startup_info_failure_returns_none(tmp_path, monkeypatch):
    """A failing batch (e.g. no tmux/client) must degrade to None so main
    falls back to the lazy per-call queries instead of crashing — and the
    failure must land in the debug log file, not stderr."""
    import logging

    log_file = tmp_path / "easymotion.log"
    monkeypatch.setattr(
        "os.path.expanduser", lambda p: str(log_file) if p.startswith("~") else p
    )
    monkeypatch.setattr(easymotion, "_tmux_options", {"@easymotion-debug": "true"})
    root = logging.getLogger()
    saved_handlers, root.handlers = root.handlers, []
    saved_disabled = root.disabled

    def boom(cmd):
        raise subprocess.CalledProcessError(1, cmd)

    try:
        with patch("easymotion.sh", boom):
            assert get_startup_info() is None
        logging.shutdown()
        assert "Batched startup query failed" in log_file.read_text()
    finally:
        for h in root.handlers:
            h.close()
        root.handlers = saved_handlers
        root.disabled = saved_disabled


@requires_tmux
def test_config_from_tmux(tmux_server):
    """Integration test: verify Config.from_tmux() reads all options correctly."""
    _clear_options_cache()

    def set_option(name, value):
        subprocess.run(
            ["tmux", "-L", tmux_server.server_name, "set-option", "-g", name, value],
            check=True,
        )

    # Set all Config fields to non-default values
    set_option("@easymotion-hints", "abc")
    set_option("@easymotion-case-sensitive", "true")
    set_option("@easymotion-smartsign", "true")
    set_option("@easymotion-vertical-border", "|")
    set_option("@easymotion-horizontal-border", "-")
    set_option("@easymotion-use-curses", "true")
    set_option("@easymotion-hint1-fg", "1;34")
    set_option("@easymotion-hint2-fg", "38;5;208")
    set_option("@easymotion-dim", "2;90")

    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == "tmux" and "show-options" in cmd:
            new_cmd = ["tmux", "-L", tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", patched_run):
        config = Config.from_tmux()

    # Verify all fields
    assert config.hints == "abc"
    assert config.case_sensitive is True
    assert config.smartsign is True
    assert config.vertical_border == "|"
    assert config.horizontal_border == "-"
    assert config.use_curses is True
    assert config.hint1_fg == "1;34"
    assert config.hint2_fg == "38;5;208"
    assert config.dim == "2;90"

    # Now test with false values
    _clear_options_cache()
    set_option("@easymotion-case-sensitive", "false")
    set_option("@easymotion-smartsign", "false")
    set_option("@easymotion-use-curses", "false")

    with patch("subprocess.run", patched_run):
        config = Config.from_tmux()

    assert config.case_sensitive is False
    assert config.smartsign is False
    assert config.use_curses is False


@requires_tmux
def test_get_tmux_option_with_spaces(tmux_server):
    """Integration test: verify option values with spaces are parsed correctly."""
    _clear_options_cache()

    # Set option with spaces
    test_value = "hello world test"
    subprocess.run(
        [
            "tmux",
            "-L",
            tmux_server.server_name,
            "set-option",
            "-g",
            "@easymotion-test-spaces",
            test_value,
        ],
        check=True,
    )

    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == "tmux" and "show-options" in cmd:
            new_cmd = ["tmux", "-L", tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", patched_run):
        result = get_tmux_option("@easymotion-test-spaces", "default")

    assert result == test_value, f"Expected '{test_value}', got '{result}'"


@requires_tmux
def test_get_tmux_option_with_quotes(tmux_server):
    """Integration test: verify option values with quotes are parsed correctly."""
    _clear_options_cache()

    # Set option with quotes (tmux stores this with escaped quotes)
    test_value = 'it"s a test'
    subprocess.run(
        [
            "tmux",
            "-L",
            tmux_server.server_name,
            "set-option",
            "-g",
            "@easymotion-test-quotes",
            test_value,
        ],
        check=True,
    )

    original_run = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if cmd[0] == "tmux" and "show-options" in cmd:
            new_cmd = ["tmux", "-L", tmux_server.server_name] + cmd[1:]
            return original_run(new_cmd, *args, **kwargs)
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", patched_run):
        result = get_tmux_option("@easymotion-test-quotes", "default")

    assert result == test_value, f"Expected '{test_value}', got '{result}'"


def test_ansi_sequence_custom_colors():
    """AnsiSequence builds escape sequences from configured SGR codes."""
    config = Config(hint1_fg="1;34", hint2_fg="38;5;208", dim="2;90")
    screen = easymotion.AnsiSequence(config)
    assert screen.HINT1 == "\033[1;34m"
    assert screen.HINT2 == "\033[38;5;208m"
    assert screen.DIM == "\033[2;90m"


def test_ansi_sequence_default_colors():
    """AnsiSequence falls back to the default palette without config."""
    screen = easymotion.AnsiSequence()
    assert screen.HINT1 == "\033[1;31m"
    assert screen.HINT2 == "\033[1;32m"
    assert screen.DIM == "\033[2m"


def test_sgr_to_curses_parser():
    """_sgr_to_curses maps SGR codes to (foreground, attribute) pairs."""
    import curses

    assert easymotion._sgr_to_curses("1;31") == (curses.COLOR_RED, curses.A_BOLD)
    assert easymotion._sgr_to_curses("38;5;208") == (208, 0)
    assert easymotion._sgr_to_curses("2") == (-1, curses.A_DIM)
    assert easymotion._sgr_to_curses("4;34") == (curses.COLOR_BLUE, curses.A_UNDERLINE)
    assert easymotion._sgr_to_curses("2;90") == (
        curses.COLOR_BLACK,
        curses.A_DIM | curses.A_BOLD,
    )
    assert easymotion._sgr_to_curses("38;2;255;128;0") == (-1, 0)
    # bright color (90-97) implies bold
    fg, attr = easymotion._sgr_to_curses("90")
    assert fg == curses.COLOR_BLACK
    assert attr & curses.A_BOLD
