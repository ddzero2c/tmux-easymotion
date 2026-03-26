#!/usr/bin/env bash

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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

# ============================================================================
# 1-Character Search Key Binding
# ============================================================================
# Prefer new naming (@easymotion-s), fallback to legacy (@easymotion-key)
S_KEY=$(get_tmux_option "@easymotion-s" "")
if [ -z "$S_KEY" ]; then
    # Fallback to legacy naming (for backward compatibility)
    S_KEY=$(get_tmux_option "@easymotion-key" "s")
fi

COPY_MODE_NO_PREFIX=$(get_tmux_option "@easymotion-copy-mode-no-prefix" "")
if [ "$COPY_MODE_NO_PREFIX" = "true" ]; then
    MODE_KEYS=$(tmux show-option -gqv mode-keys)
    if [ "$MODE_KEYS" = "vi" ]; then
        COPY_MODE_TABLE="copy-mode-vi"
    else
        COPY_MODE_TABLE="copy-mode"
    fi
fi

# Setup 1-char search binding
if [ -n "$S_KEY" ]; then
    tmux bind "$S_KEY" run-shell "$CURRENT_DIR/mode-s.sh"
    if [ -n "$COPY_MODE_TABLE" ]; then
        tmux bind -T "$COPY_MODE_TABLE" "$S_KEY" run-shell "$CURRENT_DIR/mode-s.sh"
    fi
fi

# ============================================================================
# 2-Character Search Key Binding
# ============================================================================
S2_KEY=$(get_tmux_option "@easymotion-s2" "")
if [ -n "$S2_KEY" ]; then
    tmux bind "$S2_KEY" run-shell "$CURRENT_DIR/mode-s2.sh"
    if [ -n "$COPY_MODE_TABLE" ]; then
        tmux bind -T "$COPY_MODE_TABLE" "$S2_KEY" run-shell "$CURRENT_DIR/mode-s2.sh"
    fi
fi
