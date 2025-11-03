#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common configuration and functions
source "$CURRENT_DIR/common.sh"

# Prompt for single character
ENV_VARS=$(build_env_vars "s")
tmux command-prompt -1F -p 'easymotion:' "neww -d '$ENV_VARS $CURRENT_DIR/easymotion.py %1"
