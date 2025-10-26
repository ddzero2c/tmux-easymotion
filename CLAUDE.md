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
# First time: Install development dependencies
pip install -r requirements-dev.txt

# Run tests
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

## Motion Types

The plugin supports multiple motion types, controlled by the `TMUX_EASYMOTION_MOTION_TYPE` environment variable:

- **s** (default): 1-character search - prompts for a single character and shows hints for all matches
- **s2**: 2-character search - prompts for two consecutive characters for more precise matching

### Motion Type Implementation

Each motion type is set up via different tmux key bindings in easymotion.tmux:

- **@easymotion-key**: Legacy binding (backward compatible, uses 's' mode)
- **@easymotion-s**: Explicit 1-char search binding
- **@easymotion-s2**: 2-char search binding (uses two sequential `command-prompt` calls)

The `main()` function in easymotion.py reads the `MOTION_TYPE` environment variable and:
1. For 's': reads 1 character from the temp file
2. For 's2': reads 2 characters from the temp file
3. Calls `find_matches()` with the search pattern

### 2-Character Search Details

The `find_matches()` function was refactored to support multi-character patterns:
- Accepts `search_pattern` (1+ characters) instead of `search_ch` (single character)
- For multi-char patterns, checks substring matches at each position
- Handles wide character boundaries - skips matches that would split a wide (CJK) character
- Smartsign applies to **all pattern lengths** via `generate_smartsign_patterns()`

### Smartsign Architecture

**Design Principle**: Smartsign is a **generic transformation layer** that works independently of search mode.

**Key Components**:

1. **`generate_smartsign_patterns(pattern)`**: Generic pattern generator
   - Works for patterns of **any length** (1-char, 2-char, 3-char, etc.)
   - Each character position is independently expanded if it has a smartsign mapping
   - Returns all possible combinations using Cartesian product
   - Example: `"3,"` → `["3,", "#,", "3<", "#<"]` (4 combinations)

2. **`find_matches(panes, search_pattern)`**: Pattern-agnostic matching engine
   - Calls `generate_smartsign_patterns()` to get all pattern variants
   - Performs matching logic once for all variants
   - No mode-specific smartsign logic needed

3. **Extensibility**: New search modes automatically get smartsign support
   - Mode determines **what to search** (user input, word boundaries, etc.)
   - Smartsign determines **how to expand the pattern**
   - Matching logic is unified

**Performance**: For 2-char search with both chars having mappings, maximum 4 pattern variants. For 3-char, maximum 8 variants. This is acceptable overhead.

## Configuration Options (tmux.conf)

All options are read from tmux options in easymotion.tmux and passed as environment variables to the Python script:

- `@easymotion-key`: Trigger key binding for 1-char search (default: 's', backward compatible)
- `@easymotion-s`: Explicit 1-char search key binding (optional)
- `@easymotion-s2`: 2-char search key binding (optional, e.g., 'f')
- `@easymotion-hints`: Characters used for hints (default: 'asdghklqwertyuiopzxcvbnmfj;')
- `@easymotion-vertical-border`: Character for vertical borders (default: '│')
- `@easymotion-horizontal-border`: Character for horizontal borders (default: '─')
- `@easymotion-use-curses`: Use curses instead of ANSI sequences (default: 'false')
- `@easymotion-case-sensitive`: Case-sensitive search (default: 'false')
- `@easymotion-smartsign`: Enable smartsign feature to match shifted symbols (default: 'false', works with all search modes)

## Important Implementation Notes

- The Python script runs in a detached tmux window (`neww -d`) to avoid interfering with the user's session
- Cursor position differs between normal mode and copy mode - check `pane.copy_mode` flag
- The `__slots__` optimization on `PaneInfo` reduces memory overhead
- Functions decorated with `@perf_timer()` only log timing when `TMUX_EASYMOTION_PERF` is enabled
- The `@functools.lru_cache` on width calculation functions significantly improves performance with repeated characters
