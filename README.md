# TMUX Easymotion

### Requirements
- Python3
- [Tmux Plugin Manager](https://github.com/tmux-plugins/tpm)

### Installation

Clone TPM
`$ git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm`

Put this at the bottom of ~/.tmux.conf

```
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'ddzero2c/tmux-easymotion'
run -b '~/.tmux/plugins/tpm/tpm'
```

Run `prefix` + `I` to install plugins.

### Key bindings
Configuration (vim-like)
```
# .tmux.conf
set-window-option -g mode-keys vi
bind-key -T copy-mode-vi C-v send-keys -X begin-selection \; send-keys -X rectangle-toggle;
bind-key -T copy-mode-vi v send-keys -X begin-selection;
bind-key -T copy-mode-vi V send-keys -X select-line;
bind-key -n C-k paste-buffer

...
run -b '~/.tmux/plugins/tpm/tpm'
```

`C-j` -> hit a character -> hit hints (jump to position) -> press `y` to copy

`C-k` to paste

`FIXME: demo screenshot`

### Inspire by
- [tpm](https://github.com/tmux-plugins/tpm)
- [tmux-yank](https://github.com/tmux-plugins/tmux-yank)
- [vim-easymotion](https://github.com/easymotion/vim-easymotion)

### Known issues
- Render wield when tmux pane contain wide character.
    - ex. `'哈哈'`.
