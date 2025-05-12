# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tmux-easymotion is a tmux plugin inspired by vim-easymotion that provides a quick way to navigate and jump between positions in tmux panes. The key feature is the ability to jump between panes, not just within a single pane.

## Code Architecture

- **easymotion.tmux**: Main shell script that sets up the tmux key bindings and configuration options
- **easymotion.py**: Python implementation of the easymotion functionality
  - Uses two display methods: ANSI sequences or curses
  - Implements a hints system to quickly navigate to characters
  - Handles smart matching features like case sensitivity and smartsign

## Key Concepts

1. **Hint Generation**: Creates single or double character hints for navigation
2. **Smart Matching**: Supports case-insensitive matching and "smartsign" (matching symbol pairs)
3. **Pane Navigation**: Can jump between panes, not just within one pane
4. **Visual Width Handling**: Properly handles wide characters (CJK, etc.)

## Running Tests

To run the tests:

```bash
pytest test_easymotion.py -v --cache-clear
```

## Configuration Options

The plugin supports several configuration options set in tmux.conf:

- Hint characters
- Border style
- Display method (ANSI or curses)
- Case sensitivity
- Smartsign feature
- Debug and performance logging

## Common Development Tasks

When working on this plugin, you may need to:

1. Debug the easymotion behavior by enabling debug logging:
   ```
   set -g @easymotion-debug 'true'
   ```

2. Measure performance using the perf logging option:
   ```
   set -g @easymotion-perf 'true'
   ```

Both debug and perf logs are written to `~/easymotion.log`.