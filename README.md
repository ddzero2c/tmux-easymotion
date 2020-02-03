# Tmux Easymotion

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
`prefix` + `space` -> hit a character -> hit hints.

Then, cursor will move to the position of the character in tmux copy-mode.

### Inspire by
- [vim-easymotion](https://github.com/easymotion/vim-easymotion)
- [tmux-yank](https://github.com/tmux-plugins/tmux-yank)

### Known issues
- Render wield when tmux pane contain wide character.
    - ex. `'哈哈'`.
- Can't locate double character.
    - ex. `'hook'`
