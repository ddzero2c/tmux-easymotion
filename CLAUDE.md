# CLAUDE.md

## Project Overview

tmux-easymotion is a tmux plugin for quickly jumping to visible text positions across tmux panes (vim-easymotion style). Key feature: cross-pane jumping.

## Architecture

- **easymotion.tmux** (bash): TPM entry point, sets up key bindings
- **common.sh** (bash): Shared config functions, builds env vars for Python script
- **mode-s.sh / mode-s2.sh** (bash): Motion type launchers
- **easymotion.py** (Python): Core logic - capture panes, find matches, render hints, move cursor

## Development

```bash
pip install -r requirements-dev.txt
pytest test_easymotion.py -v
```

## Writing Integration Tests

Integration tests should call real functions, not simulate their implementation.

### Pattern: Testing tmux-dependent functions

```python
@requires_tmux
def test_something(tmux_server):
    # 1. Setup: create pane content
    tmux_server.send_keys('echo "test content"', 'Enter')
    time.sleep(0.2)

    # 2. Create PaneInfo for the target
    pane = PaneInfo(tmux_server.pane_id, active=True, ...)
    pane.copy_mode = False

    # 3. Call the REAL function with patched sh()
    with patch('easymotion.sh', tmux_server.make_sh_for_server()):
        tmux_move_cursor(pane, target_line, target_col)

    # 4. Verify the RESULT, not implementation details
    cursor_x, cursor_y = tmux_server.get_cursor_position()
    assert cursor_y == target_line
```

### Key points

1. **Call real functions** - Don't manually send tmux commands that simulate what the function does
2. **Use `make_sh_for_server()`** - Patches `sh()` to redirect tmux commands to the test server (`-L` flag)
3. **Verify results** - Check cursor position, active pane, etc. Not command order
4. **Validate regression tests** - Temporarily introduce the bug to confirm the test catches it

### TmuxTestServer methods

- `send_keys()` / `send_keys_to_pane()` - Setup test content
- `split_window()` - Create multi-pane scenarios
- `get_cursor_position()` / `get_cursor_position_in_pane()` - Verify cursor
- `get_active_pane()` - Verify pane switching
- `make_sh_for_server()` - Get patched `sh()` for isolated testing

## Key Functions

- `tmux_move_cursor(pane, line_num, true_col)` - Moves cursor to position in pane
- `find_matches(panes, search_pattern)` - Finds all matches across panes
- `get_true_position(line, visual_col)` - Converts visual column to string index (for CJK)

## Configuration Options

Set in tmux.conf:
- `@easymotion-key` / `@easymotion-s`: 1-char search binding
- `@easymotion-s2`: 2-char search binding
- `@easymotion-hints`: Hint characters
- `@easymotion-case-sensitive`: Case sensitivity
- `@easymotion-smartsign`: Match shifted symbols (e.g., `1` matches `!`)
