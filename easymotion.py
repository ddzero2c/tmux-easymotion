#!/usr/bin/env python3
import functools
import os
import re
import sys
import termios
import tty
import unicodedata
from itertools import islice
from typing import List, Optional

# ANSI escape sequences
ESC = '\033'
CLEAR = f'{ESC}[2J'
CLEAR_LINE = f'{ESC}[2K'
HIDE_CURSOR = f'{ESC}[?25l'
SHOW_CURSOR = f'{ESC}[?25h'
RESET = f'{ESC}[0m'
RED_FG = f'{ESC}[31m'
GREEN_FG = f'{ESC}[32m'
DIM = f'{ESC}[2m'

# Configuration from environment
KEYS = os.environ.get('TMUX_EASYMOTION_KEYS', 'asdfghjkl;')
HINT_COLOR_1 = int(os.environ.get('TMUX_EASYMOTION_COLOR1', '1'))  # RED
HINT_COLOR_2 = int(os.environ.get('TMUX_EASYMOTION_COLOR2', '2'))  # GREEN
VERTICAL_BORDER = os.environ.get('TMUX_EASYMOTION_VERTICAL_BORDER', '│')
HORIZONTAL_BORDER = os.environ.get('TMUX_EASYMOTION_HORIZONTAL_BORDER', '─')


@functools.lru_cache(maxsize=1024)
def get_char_width(char: str) -> int:
    """Get visual width of a single character with caching"""
    return 2 if unicodedata.east_asian_width(char) in 'WF' else 1


@functools.lru_cache(maxsize=1024)
def get_string_width(s: str) -> int:
    """Calculate visual width of string, accounting for double-width characters"""
    return sum(map(get_char_width, s))


def get_visual_col(line: str, pos: int) -> int:
    """More efficient visual column calculation"""
    return sum(map(get_char_width, islice(line, 0, pos)))


def get_true_position(line, target_col):
    """Calculate true position accounting for wide characters"""
    visual_pos = 0
    true_pos = 0
    while true_pos < len(line) and visual_pos < target_col:
        char_width = get_char_width(line[true_pos])
        visual_pos += char_width
        true_pos += 1
    return true_pos


def pyshell(cmd: str) -> str:
    """Execute shell command with error handling"""
    debug = os.environ.get('TMUX_EASYMOTION_DEBUG') == 'true'
    try:
        result = os.popen(cmd).read()
        if debug:
            with open(os.path.expanduser('~/easymotion.log'), 'a') as log:
                log.write(f"Command: {cmd}\n")
                log.write(f"Result: {result}\n")
                log.write("-" * 40 + "\n")
        return result
    except Exception as e:
        if debug:
            with open(os.path.expanduser('~/easymotion.log'), 'a') as log:
                log.write(f"Error executing {cmd}: {str(e)}\n")
        raise


def get_visible_panes():
    panes = pyshell(
        'tmux list-panes -F "#{pane_id},#{window_zoomed_flag},#{pane_active}" -t "{last}"'
    ).strip().split('\n')
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
        self.lines = []  # Store split lines instead of content
        self.positions = []
        self.copy_mode = False
        self.scroll_position = 0


def get_pane_info(pane_id):
    """Get pane position and size information"""
    cmd = f'tmux display-message -p -t {pane_id} "#{{pane_top}} #{{pane_height}} #{{pane_left}} #{{pane_width}}"'
    top, height, left, width = map(int, pyshell(cmd).strip().split())
    pane = PaneInfo(pane_id, top, height, left, width)
    copy_mode = pyshell(
        f'tmux display-message -p -t {pane_id} "#{{pane_in_mode}}"').strip()
    if copy_mode == "1":
        pane.copy_mode = True
    scroll_pos = pyshell(
        f'tmux display-message -p -t {pane_id} "#{{scroll_position}}"').strip(
        )
    try:
        pane.scroll_position = int(scroll_pos)
    except ValueError:
        pane.scroll_position = 0
    return pane


def tmux_pane_id():
    # Get the ID of the pane that launched this script
    source_pane = os.environ.get('TMUX_PANE')
    if not source_pane:
        return '%0'

    # We're in a new window, get the pane from the previous window
    previous_pane = pyshell(
        'tmux list-panes -F "#{pane_id}" -t "{last}"').strip()
    if re.match(r'%\d+', previous_pane):
        return previous_pane.split('\n')[0]

    # Fallback to current pane if can't get previous
    return pyshell('tmux display-message -p "#{pane_id}"').strip()


def cleanup_window():
    """Close the current window if we opened in a new one"""
    current_window = pyshell('tmux display-message -p "#{window_id}"').strip()
    previous_window = pyshell(
        'tmux display-message -p "#{window_id}" -t "{last}"').strip()
    if current_window != previous_window:
        pyshell('tmux kill-window')

def get_terminal_size():
    """Get terminal size from tmux"""
    output = pyshell('tmux display-message -p "#{client_width},#{client_height}"')
    width, height = map(int, output.strip().split(','))
    return width, height - 1  # Subtract 1 from height

def init_terminal():
    """Initialize terminal settings"""
    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.flush()

def restore_terminal():
    """Restore terminal settings"""
    sys.stdout.write(SHOW_CURSOR)
    sys.stdout.write(RESET)
    sys.stdout.flush()

def getch():
    """Get a single character from terminal"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def tmux_capture_pane(pane):
    if pane.scroll_position > 0:
        # When scrolled up, use negative numbers to capture from history
        # -scroll_pos is where we are in history
        # -(scroll_pos - pane.height + 1) captures one screen worth from there
        end_pos = -(pane.scroll_position - pane.height + 1)
        cmd = f'tmux capture-pane -p -S -{pane.scroll_position} -E {end_pos} -t {pane.pane_id}'
    else:
        # If not scrolled, just capture current view (default behavior)
        cmd = f'tmux capture-pane -p -t {pane.pane_id}'
    return pyshell(cmd)[:-1].splitlines()  # Split immediately


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


def generate_hints(keys: str, needed_count: Optional[int] = None) -> List[str]:
    """Generate only as many hints as needed"""
    if needed_count is None:
        return [k1 + k2 for k1 in keys for k2 in keys]
    hints = []
    for k1 in keys:
        for k2 in keys:
            hints.append(k1 + k2)
            if len(hints) >= needed_count:
                return hints
    return hints


RED = 1
GREEN = 2


# Remove the init_curses function as it's no longer needed

def init_panes():
    """Initialize pane information with cached calculations"""
    panes = []
    max_x = 0
    padding_cache = {}  # Cache for padding strings
    for pane_id in get_visible_panes():
        pane = get_pane_info(pane_id)
        pane.lines = tmux_capture_pane(pane)
        max_x = max(max_x, pane.start_x + pane.width)
        # Pre-calculate padding strings
        for line in pane.lines:
            visual_width = get_string_width(line)
            if visual_width < pane.width:
                padding_len = pane.width - visual_width
                if padding_len not in padding_cache:
                    padding_cache[padding_len] = ' ' * padding_len
        panes.append(pane)
    return panes, max_x, padding_cache


def draw_pane_content(pane, padding_cache):
    """Draw the content of a single pane"""
    for y, line in enumerate(pane.lines[:pane.height]):
        visual_width = get_string_width(line)
        if visual_width < pane.width:
            line = line + padding_cache[pane.width - visual_width]
        sys.stdout.write(f'{ESC}[{pane.start_y + y};{pane.start_x}H{line[:pane.width]}')


def draw_vertical_borders(pane, max_x):
    """Draw vertical borders for a pane"""
    if pane.start_x + pane.width < max_x:  # Only if not rightmost pane
        for y in range(pane.start_y, pane.start_y + pane.height):
            sys.stdout.write(f'{ESC}[{y};{pane.start_x + pane.width}H{DIM}{VERTICAL_BORDER}{RESET}')


def draw_horizontal_border(pane, y_pos):
    """Draw horizontal border for a pane"""
    sys.stdout.write(f'{ESC}[{y_pos};{pane.start_x}H{DIM}{HORIZONTAL_BORDER * pane.width}{RESET}')


def group_panes_by_end_y(panes):
    """Group panes by their end y position"""
    rows = {}
    for pane in panes:
        end_y = pane.start_y + pane.height
        rows.setdefault(end_y, []).append(pane)
    return rows


def draw_all_panes(panes, max_x, padding_cache, terminal_height):
    """Draw all panes and their borders"""
    sorted_panes = sorted(panes, key=lambda p: p.start_y + p.height)
    
    for pane in sorted_panes:
        # 限制繪製的行數
        visible_height = min(pane.height, terminal_height - pane.start_y)
        
        # 繪製內容
        for y, line in enumerate(pane.lines[:visible_height]):
            visual_width = get_string_width(line)
            if visual_width < pane.width:
                line = line + padding_cache[pane.width - visual_width]
            sys.stdout.write(f'{ESC}[{pane.start_y + y + 1};{pane.start_x + 1}H{line[:pane.width]}')
        
        # 繪製垂直邊框
        if pane.start_x + pane.width < max_x:
            for y in range(pane.start_y, pane.start_y + visible_height):
                sys.stdout.write(f'{ESC}[{y + 1};{pane.start_x + pane.width}H{DIM}{VERTICAL_BORDER}{RESET}')
        
        # 只為非最底部的 pane 繪製水平邊框
        end_y = pane.start_y + visible_height
        if end_y < terminal_height and pane != sorted_panes[-1]:
            sys.stdout.write(f'{ESC}[{end_y + 1};{pane.start_x + 1}H{DIM}{HORIZONTAL_BORDER * pane.width}{RESET}')
    
    sys.stdout.flush()


def find_matches(panes, search_ch, hints):
    """Find all matches for the search character and assign hints"""
    hint_index = 0
    hint_positions = {}  # Add lookup dictionary
    for pane in panes:
        for line_num, line in enumerate(pane.lines):  # Use lines directly
            for match in re.finditer(search_ch, line.lower()):
                if hint_index >= len(hints):
                    continue
                visual_col = sum(get_char_width(c) for c in line[:match.start()])
                position = (pane, line_num, visual_col)
                hint = hints[hint_index]
                pane.positions.append((line_num, visual_col, line[match.start()], hint))
                hint_positions[hint] = position  # Store for quick lookup
                hint_index += 1
    return hint_positions


def draw_all_hints(panes, terminal_height):
    """Draw all hints across all panes"""
    for pane in panes:
        for line_num, col, char, hint in pane.positions:
            y = pane.start_y + line_num
            x = pane.start_x + col
            if (y < min(pane.start_y + pane.height, terminal_height) and
                    x < pane.start_x + pane.width and
                    x + get_char_width(char) + 1 < pane.start_x + pane.width):
                sys.stdout.write(f'{ESC}[{y + 1};{x + 1}H{RED_FG}{hint[0]}{RESET}')
                char_width = get_char_width(char)
                sys.stdout.write(f'{ESC}[{y + 1};{x + char_width + 1}H{GREEN_FG}{hint[1]}{RESET}')
    sys.stdout.flush()


def main():
    try:
        init_terminal()
        terminal_width, terminal_height = get_terminal_size()
        panes, max_x, padding_cache = init_panes()
        hints = generate_hints(KEYS)

        def clear_and_draw():
            sys.stdout.write(CLEAR)
            draw_all_panes(panes, max_x, padding_cache, terminal_height)
            sys.stdout.write(f'{ESC}[{terminal_height};1H')
            sys.stdout.flush()

        clear_and_draw()

        # Get search character and find matches
        search_ch = getch()
        hint_positions = find_matches(panes, search_ch, hints)

        # Draw hints for all matches
        clear_and_draw()
        draw_all_hints(panes, terminal_height)
        sys.stdout.flush()

        # Handle first character selection
        ch1 = getch()
        if ch1 not in KEYS:
            return

        # Redraw panes and show filtered hints
        clear_and_draw()
        for pane in panes:
            for line_num, col, char, hint in pane.positions:
                if not hint.startswith(ch1):
                    continue
                y = pane.start_y + line_num
                x = pane.start_x + col
                char_width = get_char_width(char)
                if (y < min(pane.start_y + pane.height, terminal_height) and
                        x < pane.start_x + pane.width and
                        x + char_width + 1 < pane.start_x + pane.width):
                    sys.stdout.write(f'{ESC}[{y + 1};{x + char_width + 1}H{GREEN_FG}{hint[1]}{RESET}')
        sys.stdout.flush()

        # Handle second character selection
        ch2 = getch()
        if ch2 not in KEYS:
            return

        # Move cursor to selected position
        target_hint = ch1 + ch2
        if target_hint in hint_positions:
            pane, line_num, col = hint_positions[target_hint]
            true_col = get_true_position(pane.lines[line_num], col)
            tmux_move_cursor(pane, line_num, true_col)

    finally:
        restore_terminal()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        restore_terminal()
    finally:
        cleanup_window()
