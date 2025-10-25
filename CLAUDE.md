# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tmux-easymotion is a tmux plugin that provides vim-easymotion-like functionality for quickly jumping to visible text positions across tmux panes. The key feature that distinguishes this plugin is its ability to jump between split panes within a tmux window.

## Architecture

The plugin consists of three main components:

1. **easymotion.tmux** (bash): TPM plugin entry point that reads tmux options and sets up key bindings. It spawns a background tmux window that runs the Python script with environment variables for configuration.

2. **easymotion.py** (Python): Core implementation that:
   - Uses either curses or ANSI escape sequences for rendering (configurable)
   - Captures all visible pane contents via `tmux capture-pane`
   - Implements hint generation and assignment based on distance from cursor
   - Handles wide (CJK) characters with proper width calculations
   - Supports both normal mode and copy mode cursor positioning

3. **Rendering Strategy**: The plugin uses an abstract `Screen` class with two implementations:
   - `Curses`: Standard curses-based rendering (opt-in via `@easymotion-use-curses`)
   - `AnsiSequence`: ANSI escape sequence rendering (default, more portable)

## Key Technical Details

### Wide Character Handling
The codebase has special handling for double-width characters (CJK characters). Functions like `get_char_width()`, `get_string_width()`, and `get_true_position()` convert between visual columns and string indices. When modifying character position logic, always use `get_true_position()` to convert visual columns to true string positions.

### Hint Generation Algorithm
The `generate_hints()` function dynamically balances single-character and double-character hints to minimize keystrokes. It ensures double-character hints never start with characters used as single-character hints. The `assign_hints_by_distance()` function sorts matches by Euclidean distance from the cursor.

### Pane Information Gathering
`get_initial_tmux_info()` makes a single tmux call to batch-fetch all pane information (positions, dimensions, cursor state, scroll position) for performance. It handles zoomed windows by filtering out non-active panes.

### Input Flow
User input flows through a temporary file (created by `mktemp`) to handle the initial search character, then switches to direct stdin reading via `getch()` for hint selection. This avoids conflicts with tmux's command-prompt.

## Development Commands

### Running Tests
```bash
pytest test_easymotion.py -v --cache-clear
```

### Testing in tmux
After making changes, reload the plugin in tmux:
```bash
# In tmux, press prefix + I to reload TPM plugins
# Or source the config manually:
tmux source-file ~/.tmux.conf
```

### Debugging
Enable debug logging by setting in ~/.tmux.conf:
```bash
set -g @easymotion-debug 'true'
```
Logs are written to ~/easymotion.log

Enable performance logging:
```bash
set -g @easymotion-perf 'true'
```

## Configuration Options (tmux.conf)

All options are read from tmux options in easymotion.tmux and passed as environment variables to the Python script:

- `@easymotion-key`: Trigger key binding (default: 's')
- `@easymotion-hints`: Characters used for hints (default: 'asdghklqwertyuiopzxcvbnmfj;')
- `@easymotion-vertical-border`: Character for vertical borders (default: '│')
- `@easymotion-horizontal-border`: Character for horizontal borders (default: '─')
- `@easymotion-use-curses`: Use curses instead of ANSI sequences (default: 'false')
- `@easymotion-case-sensitive`: Case-sensitive search (default: 'false')
- `@easymotion-smartsign`: Enable smartsign feature to match shifted symbols (default: 'false')

## Important Implementation Notes

- The Python script runs in a detached tmux window (`neww -d`) to avoid interfering with the user's session
- Cursor position differs between normal mode and copy mode - check `pane.copy_mode` flag
- The `__slots__` optimization on `PaneInfo` reduces memory overhead
- Functions decorated with `@perf_timer()` only log timing when `TMUX_EASYMOTION_PERF` is enabled
- The `@functools.lru_cache` on width calculation functions significantly improves performance with repeated characters
