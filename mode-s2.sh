#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common configuration and functions
source "$CURRENT_DIR/common.sh"

# Create temporary input file
tmp_file=$(create_input_file)

# Build environment variables
ENV_VARS=$(build_env_vars "s2")

# First prompt: get first character
tmux command-prompt -1 -p 'easymotion char 1:' \
    "run-shell \"printf '%1' > $tmp_file\"; \
     set-option -g @_easymotion_tmp_char1 '%1'"

# Second prompt: get second character and launch easymotion
tmux command-prompt -1 -p 'easymotion char 2: #{@_easymotion_tmp_char1}' \
    "run-shell \"printf '%1' >> $tmp_file && echo >> $tmp_file\"; \
     neww -d '$ENV_VARS $CURRENT_DIR/easymotion.py $tmp_file'"
