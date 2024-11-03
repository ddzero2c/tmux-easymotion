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


def test_initial_draw_performance():
    # Mock necessary tmux commands and terminal operations
    mock_tmux_info = [
        '%0,0,1,0,10,0,20,0,0',  # Simulate a simple pane setup
    ]

    mock_pane_content = ['test content'] * 10  # Simulate 10 lines of content

    with patch('easymotion.pyshell') as mock_shell, \
            patch('easymotion.sys.stdout') as mock_stdout, \
            patch('easymotion.get_terminal_size', return_value=(80, 24)):

        # Setup mock returns
        mock_shell.side_effect = [
            '\n'.join(mock_tmux_info),  # For get_initial_tmux_info
            '\n'.join(mock_pane_content),  # For tmux_capture_pane
        ]

        # Measure time from init to first draw
        start_time = time.perf_counter()

        # Initialize panes
        panes, max_x, padding_cache = init_panes()

        # Draw initial screen
        draw_all_panes(panes, max_x, padding_cache, 24)

        end_time = time.perf_counter()

        # Calculate delay
        delay = end_time - start_time

        # Assert delay is within acceptable range (e.g., under 100ms)
        assert delay < 0.1, f"Initial draw took {
            delay:.3f} seconds, which exceeds 100ms threshold"

        # Verify we're making efficient tmux calls
        assert mock_shell.call_count <= 2, "Too many tmux calls during initialization"
