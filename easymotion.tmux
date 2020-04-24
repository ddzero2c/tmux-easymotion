#!/usr/bin/env bash

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
tmux bind-key -n C-j new-window "$CURRENT_DIR/scripts/easymotion.py"
