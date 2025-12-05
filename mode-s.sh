#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common configuration and functions
source "$CURRENT_DIR/common.sh"

# Create temporary input file
tmp_file=$(create_input_file)

# Prompt for single character
ENV_VARS=$(build_env_vars "s")
tmux command-prompt -1 -p 'Search for 1 character:' "run-shell \"printf %s\\\\n \\\"%1\\\" > $tmp_file\"; \
    neww -d '$ENV_VARS $CURRENT_DIR/easymotion.py $tmp_file'"
