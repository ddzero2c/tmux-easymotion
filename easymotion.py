#!/usr/bin/env python3
import curses
import re
import os
import unicodedata

KEYS='asdfghjkl;'
stdscr = None

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

def get_visible_panes():
    panes =  pyshell('tmux list-panes -F "#{pane_id},#{window_zoomed_flag},#{pane_active}" -t "{last}"').strip().split('\n')
    panes = [v.split(',') for v in panes]
    if panes[0][1] == "1":
        return [v[0] for v in panes if v[2] == "1"]
    else:
        return [v[0] for v in panes]

class PaneInfo:
    def __init__(self, pane_id, start_y, height, start_x, width):
        self.pane_id = pane_id
        self.start_y = start_y
        self.height = height
        self.start_x = start_x
        self.width = width
        self.content = ''
        self.positions = []
        self.copy_mode = False
        self.scroll_position = 0

def get_pane_info(pane_id):
    """Get pane position and size information"""
    cmd = f'tmux display-message -p -t {pane_id} "#{{pane_top}} #{{pane_height}} #{{pane_left}} #{{pane_width}}"'
    top, height, left, width = map(int, pyshell(cmd).strip().split())
    pane = PaneInfo(pane_id, top, height, left, width)
    copy_mode = pyshell(f'tmux display-message -p -t {pane_id} "#{{pane_in_mode}}"').strip()
    if copy_mode == "1":
        pane.copy_mode = True
    scroll_pos = pyshell(f'tmux display-message -p -t {pane_id} "#{{scroll_position}}"').strip()
    try:
        pane.scroll_position =  int(scroll_pos)
    except:
        pane.scroll_position =  0
    return pane

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

def tmux_capture_pane(pane):
    if pane.scroll_position > 0:
        # When scrolled up, use negative numbers to capture from history
        # -scroll_pos is where we are in history
        # -(scroll_pos - curses.LINES + 1) captures one screen worth from there
        end_pos = -(pane.scroll_position - curses.LINES + 1)  # Calculate separately to avoid string formatting issues
        cmd = f'tmux capture-pane -p -S -{pane.scroll_position} -E {end_pos} -t {pane.pane_id}'
    else:
        # If not scrolled, just capture current view (default behavior)
        cmd = f'tmux capture-pane -p -t {pane.pane_id}'
    return pyshell(cmd)[:-1]

def fill_pane_content_with_space(pane_content, width):
    lines = pane_content.splitlines()
    result = []
    for line in lines:
        visual_width = get_string_width(line)
        padding = max(0, width - visual_width)
        result.append(line + ' ' * padding)
    return '\n'.join(result)


def tmux_move_cursor(pane, line_num, true_col):
    cmd = f'tmux select-pane -t {pane.pane_id}'
    if not pane.copy_mode:
        cmd += f' \\; copy-mode -t {pane.pane_id}'
    cmd += f' \\; send-keys -X -t {pane.pane_id} top-line'
    if line_num > 0:
        cmd += f' \\; send-keys -X -t {pane.pane_id} -N {line_num} cursor-down'
    cmd += f' \\; send-keys -X -t {pane.pane_id} start-of-line'
    if true_col > 0:
        cmd += f' \\; send-keys -X -t {pane.pane_id} -N {true_col} cursor-right'
    pyshell(cmd)

def generate_hints(keys):
    """Generate two-character hints from key set more efficiently"""
    return [k1 + k2 for k1 in keys for k2 in keys]

RED = 1
GREEN = 2

def main(stdscr):
    panes = []
    for pane_id in get_visible_panes():
        pane = get_pane_info(pane_id)
        pane.content = tmux_capture_pane(pane)
        panes.append(pane)

    curses.curs_set(False)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(RED, curses.COLOR_RED, -1)
    curses.init_pair(GREEN, curses.COLOR_GREEN, -1)

    hints = generate_hints(KEYS)

    # Draw all pane contents
    for pane in panes:
        fixed_width_content = fill_pane_content_with_space(pane.content, pane.width)
        for y, line in enumerate(fixed_width_content.splitlines()[:pane.height]):
            try:
                stdscr.addstr(pane.start_y + y, pane.start_x, line[:pane.width])
            except curses.error:
                pass
    stdscr.refresh()

    search_ch = stdscr.getkey()

    # Find matches in all panes
    hint_index = 0
    for pane in panes:
        lines = pane.content.splitlines()
        for line_num, line in enumerate(lines):
            for match in re.finditer(search_ch, line.lower()):
                if hint_index >= len(hints):
                    continue
                visual_col = sum(get_char_width(c) for c in line[:match.start()])
                pane.positions.append((line_num, visual_col, line[match.start()], hints[hint_index]))
                hint_index += 1

    # Draw hints
    for pane in panes:
        for line_num, col, char, hint in pane.positions:
            y = pane.start_y + line_num
            x = pane.start_x + col
            if (y < pane.start_y + pane.height and 
                x < pane.start_x + pane.width and 
                x + get_char_width(char) + 1 < pane.start_x + pane.width):
                try:
                    stdscr.addstr(y, x, hint[0], curses.color_pair(RED))
                    char_width = get_char_width(char)
                    stdscr.addstr(y, x + char_width, hint[1], curses.color_pair(GREEN))
                except curses.error:
                    pass
    stdscr.refresh()

    # Handle hint selection
    ch1 = stdscr.getkey()
    if ch1 not in KEYS:
        cleanup_window()
        exit(0)

    # Redraw and show second character hints
    for pane in panes:
        fixed_width_content = fill_pane_content_with_space(pane.content, pane.width)
        for y, line in enumerate(fixed_width_content.splitlines()[:pane.height]):
            try:
                stdscr.addstr(pane.start_y + y, pane.start_x, line[:pane.width])
            except curses.error:
                pass
        for line_num, col, char, hint in pane.positions:
            if not hint.startswith(ch1):
                continue
            y = pane.start_y + line_num
            x = pane.start_x + col
            char_width = get_char_width(char)
            if (y < pane.start_y + pane.height and 
                x < pane.start_x + pane.width and 
                x + char_width + 1 < pane.start_x + pane.width):
                try:
                    stdscr.addstr(y, x + char_width, hint[1], curses.color_pair(GREEN))
                except curses.error:
                    pass
    stdscr.refresh()

    ch2 = stdscr.getkey()
    if ch2 not in KEYS:
        cleanup_window()
        exit(0)

    # Find target pane and position
    target_hint = ch1 + ch2
    for pane in panes:
        for line_num, col, char, hint in pane.positions:
            if hint == target_hint:
                lines = pane.content.splitlines()
                true_col = get_true_position(lines[line_num], col)
                tmux_move_cursor(pane, line_num, true_col)
                break

    cleanup_window()

if __name__ == '__main__':
    curses.wrapper(main)
