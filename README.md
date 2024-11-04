# TMUX Easymotion

![demo](https://github.com/user-attachments/assets/19f621c0-9fef-4137-b4f6-03249dae8d31)


Q: There are already many plugins with similar functionality, why do we need this one?

A: **This one can jump between panes**

### Installation via [TPM](https://github.com/tmux-plugins/tpm)

Add plugin to the list of TPM plugins in ~/.tmux.conf:

```bash
set -g @plugin 'ddzero2c/tmux-easymotion'
set -g @easymotion-key 's'

```

### Manual Installation

`$ git clone https://github.com/ddzero2c/tmux-easymotion.git ~/.tmux-easymotion`

Add plugin to the list of TPM plugins in ~/.tmux.conf:

```bash
# Basic binding
bind s run-shell "tmux neww -d ~/.tmux-easymotion/easymotion.py"

# Or with custom environment variables
bind s run-shell "tmux neww -d 'TMUX_EASYMOTION_KEYS=asdfjkl; ~/.tmux-easymotion/easymotion.py'"
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

### Vim-like Configuration

```bash
set-window-option -g mode-keys vi
bind-key -T copy-mode-vi C-v send-keys -X begin-selection \; send-keys -X rectangle-toggle;
bind-key -T copy-mode-vi v send-keys -X begin-selection;
bind-key -T copy-mode-vi V send-keys -X select-line;
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
