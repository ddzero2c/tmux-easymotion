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

# Setup 1-char search binding. The overlay window opens FOCUSED and
# reads the search character itself: panes freeze at binding time, and
# keystrokes typed before the frame is drawn buffer in the overlay pty.
# run-shell expands #{window_id} when the binding fires, so the overlay
# knows its source window explicitly (the last-window token '!' goes
# stale once a previous overlay has closed). The window opens DETACHED:
# the frame draws in the background and easymotion switches to it once
# fully drawn — no flicker. Keys pressed meanwhile hit the already-
# frozen source pane's copy-mode (never the shell).
EASYMOTION_CMD_S="tmux new-window -d -n easymotion \"python3 '$CURRENT_DIR/easymotion.py' s --source #{window_id}\""
if [ -n "$S_KEY" ]; then
    tmux bind "$S_KEY" run-shell "$EASYMOTION_CMD_S"
    if [ -n "$COPY_MODE_TABLE" ]; then
        tmux bind -T "$COPY_MODE_TABLE" "$S_KEY" run-shell "$EASYMOTION_CMD_S"
    fi
fi

# ============================================================================
# 2-Character Search Key Binding
# ============================================================================
S2_KEY=$(get_tmux_option "@easymotion-s2" "")
EASYMOTION_CMD_S2="tmux new-window -d -n easymotion \"python3 '$CURRENT_DIR/easymotion.py' s2 --source #{window_id}\""
if [ -n "$S2_KEY" ]; then
    tmux bind "$S2_KEY" run-shell "$EASYMOTION_CMD_S2"
    if [ -n "$COPY_MODE_TABLE" ]; then
        tmux bind -T "$COPY_MODE_TABLE" "$S2_KEY" run-shell "$EASYMOTION_CMD_S2"
    fi
fi
