#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common configuration and functions
source "$CURRENT_DIR/common.sh"

# Build environment variables
ENV_VARS_OPTS=$(build_env_vars "s")

# Prompt for single character
tmux command-prompt -1F -p 'Search for 1 character:' "new-window -d $ENV_VARS_OPTS $CURRENT_DIR/easymotion.py \"%%%\""
