import time
from unittest.mock import patch

from easymotion import (draw_all_panes, generate_hints, get_char_width,
                        get_string_width, get_true_position, init_panes)


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


def test_generate_hints_with_full_keys():
    # Test with actual KEYS constant
    from easymotion import KEYS
    hints = generate_hints(KEYS)
    # Check first few hints
    assert len(hints) == len(KEYS) * len(KEYS)
    assert all(len(hint) == 2 for hint in hints)
    assert all(all(c in KEYS for c in hint) for hint in hints)
