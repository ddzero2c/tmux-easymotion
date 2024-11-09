# TMUX Easymotion

![demo](https://github.com/user-attachments/assets/6f9ef875-47b1-4dee-823d-f1990f2af51e)


Q: There are already many plugins with similar functionality, why do we need this one?

A: **This one can jump between panes**

### Installation via [TPM](https://github.com/tmux-plugins/tpm)

Add plugin to the list of TPM plugins in ~/.tmux.conf:

```bash
set -g @plugin 'ddzero2c/tmux-easymotion'
set -g @easymotion-key 's'
```

Press `prefix` + `I` to install


### Options:

```bash
# Keys used for hints (default: 'asdfghjkl;')
set -g @easymotion-hints 'asdfghjkl;'

# Border characters
set -g @easymotion-vertical-border '│'
set -g @easymotion-horizontal-border '─'

# Use curses instead of ansi escape sequences (default: false)
set -g @easymotion-use-curses 'false'

# Debug mode - writes debug info to ~/easymotion.log (default: false)
set -g @easymotion-debug 'false'

# Performance logging - writes timing info to ~/easymotion.log (default: false)
set -g @easymotion-perf 'false'

# Case sensitive search (default: false)
set -g @easymotion-case-sensitive 'false'

# Enable smartsign feature (default: false)
set -g @easymotion-smartsign 'false'
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
