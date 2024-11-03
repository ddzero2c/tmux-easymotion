# TMUX Easymotion

![demo](https://github.com/user-attachments/assets/19f621c0-9fef-4137-b4f6-03249dae8d31)

### Installation

`$ git clone https://github.com/ddzero2c/tmux-easymotion.git ~/.tmux-easymotion`

### Configuration

```bash
# Basic binding
bind s run-shell "tmux neww ~/.tmux-easymotion/easymotion.py"

# Or with custom environment variables
bind s run-shell "tmux neww TMUX_EASYMOTION_KEYS='asdfjkl;' ~/.tmux-easymotion/easymotion.py"

# Vim-like binding
set-window-option -g mode-keys vi
bind-key -T copy-mode-vi C-v send-keys -X begin-selection \; send-keys -X rectangle-toggle;
bind-key -T copy-mode-vi v send-keys -X begin-selection;
bind-key -T copy-mode-vi V send-keys -X select-line;
```

Available environment variables(default values):
```bash
# Keys used for hints
TMUX_EASYMOTION_KEYS="asdfghjkl;"

# For old users who need curses instead of ansi escape sequences
TMUX_EASYMOTION_USE_CURSES="true"

# Border characters
TMUX_EASYMOTION_VERTICAL_BORDER="│"
TMUX_EASYMOTION_HORIZONTAL_BORDER="─"

# Debug mode - writes debug info to ~/easymotion.log
TMUX_EASYMOTION_DEBUG="false"

# Performance logging - writes timing info to ~/easymotion.log
TMUX_EASYMOTION_PERF="false"
```

### Usage
`prefix` + `s` -> hit a character -> hit hints (jump to position) -> press `ve` and `y` to copy

`prefix` + `]` to paste


### Run tests

```bash
pytest test_easymotion.py -v --cache-clear
```

### Inspire by
- [tmux-yank](https://github.com/tmux-plugins/tmux-yank)
- [vim-easymotion](https://github.com/easymotion/vim-easymotion)

### Known issues
- ~~Render wield when tmux pane contain wide character.~~
    ~~- ex. `'哈哈'`.~~
- ~~Scrolled up panes are not supported~~
- ~~Broken when tmux window has split panes~~
- ~~Jump between panes is not supported~~
