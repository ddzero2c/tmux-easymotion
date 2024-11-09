#!/usr/bin/env bash

get_tmux_option() {
    local option=$1
    local default_value=$2
    local option_value=$(tmux show-option -gqv "$option")
    if [ -z $option_value ]; then
        echo $default_value
    else
        echo $option_value
    fi
}

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Define all options and their default values
HINTS=$(get_tmux_option "@easymotion-hints" "asdfghjkl;")
VERTICAL_BORDER=$(get_tmux_option "@easymotion-vertical-border" "│")
HORIZONTAL_BORDER=$(get_tmux_option "@easymotion-horizontal-border" "─")
USE_CURSES=$(get_tmux_option "@easymotion-use-curses" "false")
DEBUG=$(get_tmux_option "@easymotion-debug" "false")
PERF=$(get_tmux_option "@easymotion-perf" "false")
CASE_SENSITIVE=$(get_tmux_option "@easymotion-case-sensitive" "false")
SMARTSIGN=$(get_tmux_option "@easymotion-smartsign" "false")

# Execute Python script with environment variables
tmux bind $(get_tmux_option "@easymotion-key" "s") run-shell "TMUX_EASYMOTION_HINTS='$HINTS' \
    TMUX_EASYMOTION_VERTICAL_BORDER='$VERTICAL_BORDER' \
    TMUX_EASYMOTION_HORIZONTAL_BORDER='$HORIZONTAL_BORDER' \
    TMUX_EASYMOTION_USE_CURSES='$USE_CURSES' \
    TMUX_EASYMOTION_DEBUG='$DEBUG' \
    TMUX_EASYMOTION_PERF='$PERF' \
    TMUX_EASYMOTION_CASE_SENSITIVE='$CASE_SENSITIVE' \
    TMUX_EASYMOTION_SMARTSIGN='$SMARTSIGN' \
    $CURRENT_DIR/easymotion.py"
