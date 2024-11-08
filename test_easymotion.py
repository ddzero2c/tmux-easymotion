from easymotion import (generate_hints, get_char_width, get_string_width,
                        get_true_position)


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
                assert double_char[0] not in single_chars, f"Double char hint {
                    double_char} starts with single char hint"

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
