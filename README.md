# TMUX Easymotion

![demo](https://user-images.githubusercontent.com/20437334/109680947-f1bf2680-7bb7-11eb-9990-1deb3d5a5736.gif)

### Installation

Clone TPM
`$ git clone https://github.com/ddzero2c/tmux-easymotion.git ~/.tmux-easymotion`

Put this at the bottom of ~/.tmux.conf

```
bind s run-shell "tmux neww ~/.tmux-easymotion/easymotion.py"
```

### Key bindings
`prefix` + `s` -> hit a character -> hit hints (jump to position) -> press `Enter` to copy

`prefix` + `]` to paste

Configure vim-like movement:
```
# .tmux.conf
set-window-option -g mode-keys vi
bind-key -T copy-mode-vi C-v send-keys -X begin-selection \; send-keys -X rectangle-toggle;
bind-key -T copy-mode-vi v send-keys -X begin-selection;
bind-key -T copy-mode-vi V send-keys -X select-line;
```

### Inspire by
- [tmux-yank](https://github.com/tmux-plugins/tmux-yank)
- [vim-easymotion](https://github.com/easymotion/vim-easymotion)

### Known issues
- ~~Render wield when tmux pane contain wide character.~~
    ~~- ex. `'哈哈'`.~~
- ~~Scrolled up panes are not supported~~
- ~~Broken when tmux window has split panes~~
- Jump between panes is not supported
