#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# First prompt: get first character
tmux source - <<-EOF
    command-prompt -1 -p 'Search for 2 characters:' {
        set-option -g @_easymotion_tmp_char1 "%1"
    }
EOF

# Second prompt: get second character and launch easymotion
tmux source - <<-EOF
    command-prompt -1 -p 'Search for 2 characters: #{@_easymotion_tmp_char1}' {
        run-shell -C "new-window -d $CURRENT_DIR/easymotion.py s2 \"#{q:@_easymotion_tmp_char1}%%%\""
    }
EOF
