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
HINTS=$(get_tmux_option "@easymotion-hints" "asdghklqwertyuiopzxcvbnmfj;")
VERTICAL_BORDER=$(get_tmux_option "@easymotion-vertical-border" "│")
HORIZONTAL_BORDER=$(get_tmux_option "@easymotion-horizontal-border" "─")
USE_CURSES=$(get_tmux_option "@easymotion-use-curses" "false")
DEBUG=$(get_tmux_option "@easymotion-debug" "false")
PERF=$(get_tmux_option "@easymotion-perf" "false")
CASE_SENSITIVE=$(get_tmux_option "@easymotion-case-sensitive" "false")
SMARTSIGN=$(get_tmux_option "@easymotion-smartsign" "false")

tmp_file=$(mktemp -t tmux-easymotion_keystroke-XXXXXXX)

# Escape semicolon in hints (if present)
HINTS_ESCAPED="${HINTS/;/\";\"}"

# Build environment variables string for passing to neww -d
# This must be done because neww -d does not inherit exported variables
ENV_VARS="\
TMUX_EASYMOTION_HINTS=$HINTS_ESCAPED \
TMUX_EASYMOTION_VERTICAL_BORDER=$VERTICAL_BORDER \
TMUX_EASYMOTION_HORIZONTAL_BORDER=$HORIZONTAL_BORDER \
TMUX_EASYMOTION_USE_CURSES=$USE_CURSES \
TMUX_EASYMOTION_DEBUG=$DEBUG \
TMUX_EASYMOTION_PERF=$PERF \
TMUX_EASYMOTION_CASE_SENSITIVE=$CASE_SENSITIVE \
TMUX_EASYMOTION_SMARTSIGN=$SMARTSIGN"

# ============================================================================
# 1-Character Search Key Binding
# ============================================================================
# Prefer new naming (@easymotion-s), fallback to legacy (@easymotion-key)
S_KEY=$(get_tmux_option "@easymotion-s" "")
if [ -z "$S_KEY" ]; then
    # Fallback to legacy naming (for backward compatibility)
    S_KEY=$(get_tmux_option "@easymotion-key" "s")
fi

# Setup 1-char search binding
if [ -n "$S_KEY" ]; then
    tmux bind "$S_KEY" run-shell "\
        printf '\x03' > $tmp_file && tmux command-prompt -1 -p 'easymotion:' 'run-shell \"printf %s\\\\n \\\"%1\\\" > $tmp_file\"' \; \
        neww -d '$ENV_VARS TMUX_EASYMOTION_MOTION_TYPE=s $CURRENT_DIR/easymotion.py $tmp_file'"
fi

# ============================================================================
# 2-Character Search Key Binding
# ============================================================================
S2_KEY=$(get_tmux_option "@easymotion-s2" "")
if [ -n "$S2_KEY" ]; then
    tmux bind "$S2_KEY" run-shell "\
        printf '\x03' > $tmp_file && \
        tmux command-prompt -1 -p 'easymotion char 1:' 'run-shell \"printf %s \\\"%1\\\" > $tmp_file\"' \; \
        command-prompt -1 -p 'easymotion char 2:' 'run-shell \"printf %s\\\\n \\\"%1\\\" >> $tmp_file\"' \; \
        neww -d '$ENV_VARS TMUX_EASYMOTION_MOTION_TYPE=s2 $CURRENT_DIR/easymotion.py $tmp_file'"
fi
