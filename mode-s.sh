#!/usr/bin/env bash

# Get the directory where this script is located
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Prompt for single character and launch easymotion
tmux command-prompt -1F -p 'Search for 1 character:' "run-shell -C \"new-window -d $CURRENT_DIR/easymotion.py s \\\"%%%\\\"\""
