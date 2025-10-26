#!/usr/bin/env bash

# Common functions and configuration for easymotion modes

# Read configuration from tmux options
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

# Get all configuration options
HINTS=$(get_tmux_option "@easymotion-hints" "asdghklqwertyuiopzxcvbnmfj;")
VERTICAL_BORDER=$(get_tmux_option "@easymotion-vertical-border" "│")
HORIZONTAL_BORDER=$(get_tmux_option "@easymotion-horizontal-border" "─")
USE_CURSES=$(get_tmux_option "@easymotion-use-curses" "false")
DEBUG=$(get_tmux_option "@easymotion-debug" "false")
PERF=$(get_tmux_option "@easymotion-perf" "false")
CASE_SENSITIVE=$(get_tmux_option "@easymotion-case-sensitive" "false")
SMARTSIGN=$(get_tmux_option "@easymotion-smartsign" "false")

# Create temporary input file with reset character
create_input_file() {
    local tmp_file=$(mktemp -t tmux-easymotion_keystroke-XXXXXXX)
    printf '\x03' > "$tmp_file"
    echo "$tmp_file"
}

# Build environment variables string for neww -d
build_env_vars() {
    local motion_type=$1
    echo "TMUX_EASYMOTION_HINTS=\"$HINTS\" \
TMUX_EASYMOTION_VERTICAL_BORDER=\"$VERTICAL_BORDER\" \
TMUX_EASYMOTION_HORIZONTAL_BORDER=\"$HORIZONTAL_BORDER\" \
TMUX_EASYMOTION_USE_CURSES=\"$USE_CURSES\" \
TMUX_EASYMOTION_DEBUG=\"$DEBUG\" \
TMUX_EASYMOTION_PERF=\"$PERF\" \
TMUX_EASYMOTION_CASE_SENSITIVE=\"$CASE_SENSITIVE\" \
TMUX_EASYMOTION_SMARTSIGN=\"$SMARTSIGN\" \
TMUX_EASYMOTION_MOTION_TYPE=\"$motion_type\""
}
