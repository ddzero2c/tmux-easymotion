#!/usr/bin/env python3
import curses
import re
import os
import itertools
import unicodedata

KEYS='asdfghjkl;'

def get_char_width(char):
    """Get visual width of a single character"""
    return 2 if unicodedata.east_asian_width(char) in 'WF' else 1

def get_string_width(s):
    """Calculate visual width of string, accounting for double-width characters"""
    width = 0
    for c in s:
        width += get_char_width(c)
    return width

def get_true_position(line, target_col):
    """Calculate true position accounting for wide characters"""
    visual_pos = 0
    true_pos = 0
    while true_pos < len(line) and visual_pos < target_col:
        char_width = get_char_width(line[true_pos])
        visual_pos += char_width
        true_pos += 1
    return true_pos

def pyshell(cmd):
    debug = os.environ.get('TMUX_EASYMOTION_DEBUG') == 'true'
    if debug:
        with open(os.path.expanduser('~/easymotion.log'), 'a') as log:
            log.write(f"Command: {cmd}\n")
            result = os.popen(cmd).read()
            log.write(f"Result: {result}\n")
            log.write("-" * 40 + "\n")
            return result
    return os.popen(cmd).read()

def tmux_pane_id():
    # Get the ID of the pane that launched this script
    source_pane = os.environ.get('TMUX_PANE')
    if not source_pane:
        return '%0'

    # We're in a new window, get the pane from the previous window
    previous_pane = pyshell('tmux list-panes -F "#{pane_id}" -t "{last}"').strip()
    if re.match(r'%\d+', previous_pane):
        return previous_pane.split('\n')[0]
        
    # Fallback to current pane if can't get previous
    return pyshell('tmux display-message -p "#{pane_id}"').strip()

def cleanup_window():
    """Close the current window if we opened in a new one"""
    current_window = pyshell('tmux display-message -p "#{window_id}"').strip()
    previous_window = pyshell('tmux display-message -p "#{window_id}" -t "{last}"').strip()
    if current_window != previous_window:
        pyshell('tmux kill-window')

def tmux_capture_pane(pane_id):
    scroll_pos = get_scroll_position(pane_id)
    
    if scroll_pos > 0:
        # When scrolled up, use negative numbers to capture from history
        # -scroll_pos is where we are in history
        # -(scroll_pos - curses.LINES + 1) captures one screen worth from there
        end_pos = -(scroll_pos - curses.LINES + 1)  # Calculate separately to avoid string formatting issues
        cmd = f'tmux capture-pane -p -S -{scroll_pos} -E {end_pos} -t {pane_id}'
    else:
        # If not scrolled, just capture current view (default behavior)
        cmd = f'tmux capture-pane -p -t {pane_id}'
    
    return pyshell(cmd)[:-1]

def fill_pane_content_with_space(pane_content, width):
    lines = pane_content.splitlines()
    result = []
    for line in lines:
        visual_width = get_string_width(line)
        padding = max(0, width - visual_width)
        result.append(line + ' ' * padding)
    return '\n'.join(result)

def get_scroll_position(pane_id):
    # First check if we're in copy-mode
    copy_mode = pyshell(f'tmux display-message -p -t {pane_id} "#{{pane_in_mode}}"').strip()
    if copy_mode != "1":
        return 0
        
    # Get scroll position only if in copy-mode
    scroll_pos = pyshell(f'tmux display-message -p -t {pane_id} "#{{scroll_position}}"').strip()
    try:
        return int(scroll_pos)
    except ValueError:
        return 0

def tmux_move_cursor(pane_id, position):
    # First ensure we're in copy mode
    pyshell(f'tmux copy-mode -t {pane_id}')
    # Move to top and then navigate to position
    pyshell(f'tmux send-keys -X -t {pane_id} top-line')
    pyshell(f'tmux send-keys -X -t {pane_id} -N {position} cursor-right')

def generate_hints(keys):
    """Generate two-character hints from key set more efficiently"""
    return [k1 + k2 for k1 in keys for k2 in keys]

RED = 1
GREEN = 2

def main(stdscr):
    pane_id = tmux_pane_id()
    scroll_position = get_scroll_position(pane_id)
    captured_pane = tmux_capture_pane(pane_id)

    # invisible cursor
    curses.curs_set(False)

    # get screen width
    _, width = stdscr.getmaxyx()

    # init default colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(RED, curses.COLOR_RED, -1)
    curses.init_pair(GREEN, curses.COLOR_GREEN, -1)

    # keys = 'abcd', hints = a, b, c, d, aa, ab, ac .... dd
    hints = generate_hints(KEYS)
    hints_dict = {hint: i for i, hint in enumerate(hints)}

    # wrap newline to fixed width space
    fixed_width_pane = fill_pane_content_with_space(captured_pane, width)

    # Split into lines and add each line separately
    for y, line in enumerate(fixed_width_pane.splitlines()):
        try:
            stdscr.addstr(y, 0, line)
        except curses.error:
            pass  # Ignore errors from writing to bottom-right corner
    stdscr.refresh()
    search_ch = stdscr.getkey()

    # Track positions by line number and column
    positions = []
    lines = captured_pane.splitlines()
    for line_num, line in enumerate(lines):
        for match in re.finditer(search_ch, line.lower()):
            visual_col = sum(get_char_width(c) for c in line[:match.start()])
            positions.append((line_num, visual_col, line[match.start()]))

    # render 1st hints
    for i, (line_num, col, char) in enumerate(positions):
        if i >= len(hints):
            break
        y = line_num
        x = col
        stdscr.addstr(y, x, hints[i][0], curses.color_pair(RED))
        char_width = get_char_width(char)
        if x + char_width < width:
            stdscr.addstr(y, x + char_width, hints[i][1], curses.color_pair(GREEN))
    stdscr.refresh()

    ch1 = stdscr.getkey()
    if  ch1 not in KEYS:
        exit(0)

    # render 2nd hints
    for y, line in enumerate(fixed_width_pane.splitlines()):
        try:
            stdscr.addstr(y, 0, line)
        except curses.error:
            pass
    for i, (line_num, col, char) in enumerate(positions):
        if not hints[i].startswith(ch1) or len(hints[i]) < 2:
            continue
        y = line_num
        x = col
        char_width = get_char_width(char)
        if x + char_width < width:
            stdscr.addstr(y, x + char_width, hints[i][1], curses.color_pair(GREEN))
    stdscr.refresh()

    ch2 = stdscr.getkey()
    if ch2 not in KEYS:
        cleanup_window()
        exit(0)
    # Calculate final position based on line and column
    target_pos = positions[hints_dict[ch1+ch2]]
    line_offset = sum(len(line) + 1 for line in lines[:target_pos[0]])
    true_col = get_true_position(lines[target_pos[0]], target_pos[1])
    final_pos = line_offset + true_col  # Convert visual position to true position
    
    # Adjust for scroll position
    if scroll_position > 0:
        tmux_move_cursor(pane_id, final_pos)
    else:
        # If not scrolled, move to absolute position
        tmux_move_cursor(pane_id, final_pos)
    cleanup_window()

if __name__ == '__main__':
    curses.wrapper(main)
