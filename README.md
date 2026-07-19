# TMUX Easymotion

[![Tests](https://github.com/ddzero2c/tmux-easymotion/actions/workflows/test.yml/badge.svg)](https://github.com/ddzero2c/tmux-easymotion/actions/workflows/test.yml)

![demo](https://github.com/user-attachments/assets/6f9ef875-47b1-4dee-823d-f1990f2af51e)

## Features

- **Cross-pane jumping** - Jump between any visible pane in the same window
- **Two search modes** - 1-char (`s`) and 2-char (`s2`, leap.nvim style)
- **CJK support** - Proper handling of wide characters
- **Smartsign** - Match shifted symbols (e.g., `1` matches `!`)
- **Distance-based hints** - Closer matches get shorter hints
- **Frozen frames** - Panes freeze the moment you trigger, so you always land on what you saw. On tmux ≥ 3.6 frozen views are read exactly; older tmux uses an approximation with [known edge cases](#requirements)

## Installation

Add plugin to the list of [TPM](https://github.com/tmux-plugins/tpm) plugins in `~/.tmux.conf`:

<!-- x-release-please-start-version -->
```bash
set -g @plugin 'ddzero2c/tmux-easymotion#v1.3.0'
set -g @easymotion-s 's'
```
<!-- x-release-please-end -->

Press `prefix` + `I` to install

> **For development version:** Use `set -g @plugin 'ddzero2c/tmux-easymotion'` (master branch, may be unstable)


## Requirements

- tmux ≥ 3.4 (Python 3.8+)
- **tmux ≥ 3.6 recommended**: overlays of re-triggered or user-scrolled frozen panes are read directly from the frozen view (exact). Older tmux lacks a reliable way to read a copy-mode view (`#{copy_cursor_line}` truncates at wide characters before 3.6), so it falls back to reconstructing the frame from the live grid — accurate in common cases, but the frame can drift when a TUI rewrites its screen in place or the pane is resized while frozen.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `@easymotion-s` | `s` | 1-character search key binding (opens the overlay; type the character on the frozen frame) |
| `@easymotion-s2` | (none) | 2-character search key binding (leap.nvim style) |
| `@easymotion-hints` | `asdghklqwertyuiopzxcvbnmfj;` | Characters used for hints |
| `@easymotion-case-sensitive` | `false` | Case-sensitive search |
| `@easymotion-smartsign` | `false` | Match shifted symbols (e.g., `1` matches `!`) |
| `@easymotion-copy-mode-no-prefix` | `false` | Bind keys directly in copy mode (no prefix required) |
| `@easymotion-vertical-border` | `│` | Vertical border character |
| `@easymotion-horizontal-border` | `─` | Horizontal border character |
| `@easymotion-use-curses` | `false` | Use curses instead of ANSI sequences |
| `@easymotion-hint1-fg` | `1;31` | SGR color code for the first hint character (bold red) |
| `@easymotion-hint2-fg` | `1;32` | SGR color code for the second hint character (bold green) |
| `@easymotion-dim` | `2` | SGR color code for the dimmed background text |
| `@easymotion-debug` | `false` | Debug logging to ~/easymotion.log |
| `@easymotion-perf` | `false` | Performance logging to ~/easymotion.log |

Example configuration:

```bash
set -g @easymotion-s 's'
set -g @easymotion-s2 'f'
set -g @easymotion-hints 'asdfghjkl;'
set -g @easymotion-case-sensitive 'true'
set -g @easymotion-smartsign 'true'

# Custom colors (standard SGR codes: "1" bold, "4" underline,
# "31"-"37" / "90"-"97" basic colors, "38;5;N" for 256-color)
set -g @easymotion-hint1-fg '1;38;5;208'  # bold orange
set -g @easymotion-hint2-fg '1;38;5;33'   # bold blue
set -g @easymotion-dim '2;90'             # dim grey
```


## Vim-like Configuration

```bash
set-window-option -g mode-keys vi
bind-key -T copy-mode-vi C-v send-keys -X begin-selection \; send-keys -X rectangle-toggle;
bind-key -T copy-mode-vi v send-keys -X begin-selection;
bind-key -T copy-mode-vi V send-keys -X select-line;
```


## Usage

**Copy a word:**
`prefix` + `s` → type character → select hint → press `ve` and `y` to copy

**Paste:**
`prefix` + `]` to paste


## Development

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest test_easymotion.py -v --cache-clear
```

## Inspired by
- [tmux-yank](https://github.com/tmux-plugins/tmux-yank)
- [vim-easymotion](https://github.com/easymotion/vim-easymotion)

