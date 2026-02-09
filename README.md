# TMUX Easymotion

[![Tests](https://github.com/ddzero2c/tmux-easymotion/actions/workflows/test.yml/badge.svg)](https://github.com/ddzero2c/tmux-easymotion/actions/workflows/test.yml)

> [!NOTE]
> **📢 Active Development**
>
> The master branch may include breaking changes. Please use a tagged version for stability.

![demo](https://github.com/user-attachments/assets/6f9ef875-47b1-4dee-823d-f1990f2af51e)

## Features

- **Cross-pane jumping** - Jump between any visible pane in the same window
- **Two search modes** - 1-char (`s`) and 2-char (`s2`, leap.nvim style)
- **CJK support** - Proper handling of wide characters
- **Smartsign** - Match shifted symbols (e.g., `1` matches `!`)
- **Distance-based hints** - Closer matches get shorter hints

## Installation

Add plugin to the list of [TPM](https://github.com/tmux-plugins/tpm) plugins in `~/.tmux.conf`:

<!-- x-release-please-start-version -->
```bash
set -g @plugin 'ddzero2c/tmux-easymotion#v1.1.0'
set -g @easymotion-s 's'
```
<!-- x-release-please-end -->

Press `prefix` + `I` to install

> **For development version:** Use `set -g @plugin 'ddzero2c/tmux-easymotion'` (master branch, may be unstable)


## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `@easymotion-s` | `s` | 1-character search key binding |
| `@easymotion-s2` | (none) | 2-character search key binding (leap.nvim style) |
| `@easymotion-hints` | `asdghklqwertyuiopzxcvbnmfj;` | Characters used for hints |
| `@easymotion-case-sensitive` | `false` | Case-sensitive search |
| `@easymotion-smartsign` | `false` | Match shifted symbols (e.g., `1` matches `!`) |
| `@easymotion-vertical-border` | `│` | Vertical border character |
| `@easymotion-horizontal-border` | `─` | Horizontal border character |
| `@easymotion-use-curses` | `false` | Use curses instead of ANSI sequences |
| `@easymotion-debug` | `false` | Debug logging to ~/easymotion.log |
| `@easymotion-perf` | `false` | Performance logging to ~/easymotion.log |

Example configuration:

```bash
set -g @easymotion-s 's'
set -g @easymotion-s2 'f'
set -g @easymotion-hints 'asdfghjkl;'
set -g @easymotion-case-sensitive 'true'
set -g @easymotion-smartsign 'true'
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

