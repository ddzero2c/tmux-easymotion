#!/usr/bin/env bash

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load common functions
source "$CURRENT_DIR/common.sh"

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
    tmux bind "$S_KEY" run-shell "$CURRENT_DIR/mode-s.sh"
fi

# ============================================================================
# 2-Character Search Key Binding
# ============================================================================
S2_KEY=$(get_tmux_option "@easymotion-s2" "")
if [ -n "$S2_KEY" ]; then
    tmux bind "$S2_KEY" run-shell "$CURRENT_DIR/mode-s2.sh"
fi
