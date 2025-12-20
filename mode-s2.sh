#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common configuration and functions
source "$CURRENT_DIR/common.sh"

# Build environment variables
ENV_VAR_OPTS=$(build_env_var_opts "s2")

# First prompt: get first character
tmux source - <<-EOF
    command-prompt -1 -p 'Search for 2 characters:' {
        set-option -g @_easymotion_tmp_char1 "%1"
    }
EOF

# Second prompt: get second character and launch easymotion
tmux source - <<-EOF
    command-prompt -1 -p 'Search for 2 characters: #{@_easymotion_tmp_char1}' {
        run-shell -C "new-window -d $ENV_VAR_OPTS $CURRENT_DIR/easymotion.py \"#{q:@_easymotion_tmp_char1}%%%\""
    }
EOF
