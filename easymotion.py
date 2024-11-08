#!/usr/bin/env python3
import curses
import functools
import logging
import os
import re
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from abc import ABC, abstractmethod
from typing import List, Optional

# Configuration from environment
KEYS = os.environ.get('TMUX_EASYMOTION_KEYS', 'asdfghjkl;')
VERTICAL_BORDER = os.environ.get('TMUX_EASYMOTION_VERTICAL_BORDER', '│')
HORIZONTAL_BORDER = os.environ.get('TMUX_EASYMOTION_HORIZONTAL_BORDER', '─')
USE_CURSES = os.environ.get(
    'TMUX_EASYMOTION_USE_CURSES', 'false').lower() == 'true'


class Screen(ABC):
    # Common attributes for both implementations
    A_NORMAL = 0
    A_DIM = 1
    A_HINT1 = 2
    A_HINT2 = 3

    @abstractmethod
    def transform_attr(self, attr):
        """Transform generic attributes to implementation-specific attributes"""
        pass

    @abstractmethod
    def init(self):
        """Initialize the screen"""
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup the screen"""
        pass

    @abstractmethod
    def addstr(self, y: int, x: int, text: str, attr=0):
        """Add string with attributes"""
        pass

    @abstractmethod
    def refresh(self):
        """Refresh the screen"""
        pass

    @abstractmethod
    def clear(self):
        """Clear the screen"""
        pass


class AnsiSequence(Screen):
    # ANSI escape sequences
    ESC = '\033'
    CLEAR = f'{ESC}[2J'
    CLEAR_LINE = f'{ESC}[2K'
    HIDE_CURSOR = f'{ESC}[?25l'
    SHOW_CURSOR = f'{ESC}[?25h'
    RESET = f'{ESC}[0m'
    DIM = f'{ESC}[2m'
    RED = f'{ESC}[1;31m'
    GREEN = f'{ESC}[1;32m'

    def init(self):
        sys.stdout.write(self.HIDE_CURSOR)
        sys.stdout.flush()

    def cleanup(self):
        sys.stdout.write(self.SHOW_CURSOR)
        sys.stdout.write(self.RESET)
        sys.stdout.flush()

    def transform_attr(self, attr):
        if attr == self.A_DIM:
            return self.DIM
        elif attr == self.A_HINT1:
            return self.RED
        elif attr == self.A_HINT2:
            return self.GREEN
        return ''

    def addstr(self, y: int, x: int, text: str, attr=0):
        attr_str = self.transform_attr(attr)
        if attr_str:
            sys.stdout.write(
                f'{self.ESC}[{y+1};{x+1}H{attr_str}{text}{self.RESET}')
        else:
            sys.stdout.write(f'{self.ESC}[{y+1};{x+1}H{text}')

    def refresh(self):
        sys.stdout.flush()

    def clear(self):
        sys.stdout.write(self.CLEAR)


class Curses(Screen):
    def __init__(self):
        self.stdscr = None

    def init(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)

    def cleanup(self):
        if not self.stdscr:
            return
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    def transform_attr(self, attr):
        if attr == self.A_DIM:
            return curses.A_DIM
        elif attr == self.A_HINT1:
            return curses.color_pair(1) | curses.A_BOLD
        elif attr == self.A_HINT2:
            return curses.color_pair(2) | curses.A_BOLD
        return curses.A_NORMAL

    def addstr(self, y: int, x: int, text: str, attr=0):
        try:
            self.stdscr.addstr(y, x, text, self.transform_attr(attr))
        except curses.error:
            pass

    def refresh(self):
        self.stdscr.refresh()

    def clear(self):
        self.stdscr.clear()


def setup_logging():
    """Initialize logging configuration based on environment variables"""
    debug_mode = os.environ.get('TMUX_EASYMOTION_DEBUG') == 'true'
    perf_mode = os.environ.get('TMUX_EASYMOTION_PERF') == 'true'

    if not (debug_mode or perf_mode):
        logging.getLogger().disabled = True
        return

    log_file = os.path.expanduser('~/easymotion.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format=f'%(asctime)s - %(levelname)s - {
            "CURSE" if USE_CURSES else "ANSI"} - %(message)s'
    )


def perf_timer(func_name=None):
    """Performance timing decorator that only logs when TMUX_EASYMOTION_PERF is true"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if os.environ.get('TMUX_EASYMOTION_PERF') != 'true':
                return func(*args, **kwargs)

            name = func_name or func.__name__
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()

            logging.info(f"{name} took: {end_time - start_time:.3f} seconds")
            return result
        return wrapper
    return decorator


@functools.lru_cache(maxsize=1024)
def get_char_width(char: str) -> int:
    """Get visual width of a single character with caching"""
    return 2 if unicodedata.east_asian_width(char) in 'WF' else 1


@functools.lru_cache(maxsize=1024)
def get_string_width(s: str) -> int:
    """Calculate visual width of string, accounting for double-width characters"""
    return sum(map(get_char_width, s))


def get_true_position(line, target_col):
    """Calculate true position accounting for wide characters"""
    visual_pos = 0
    true_pos = 0
    while true_pos < len(line) and visual_pos < target_col:
        char_width = get_char_width(line[true_pos])
        visual_pos += char_width
        true_pos += 1
    return true_pos


def sh(cmd: list) -> str:
    """Execute shell command with optional logging"""
    debug_mode = os.environ.get('TMUX_EASYMOTION_DEBUG') == 'true'

    try:
        result = subprocess.run(
            cmd,
            shell=False,
            text=True,
            capture_output=True,
            check=True
        ).stdout

        if debug_mode:
            logging.debug(f"Command: {cmd}")
            logging.debug(f"Result: {result}")
            logging.debug("-" * 40)

        return result
    except subprocess.CalledProcessError as e:
        if debug_mode:
            logging.error(f"Error executing {cmd}: {str(e)}")
        raise


def get_initial_tmux_info():
    """Get all needed tmux info in one optimized call"""
    format_str = '#{pane_id},#{window_zoomed_flag},#{pane_active},' + \
        '#{pane_top},#{pane_height},#{pane_left},#{pane_width},' + \
        '#{pane_in_mode},#{scroll_position}'

    cmd = ['tmux', 'list-panes', '-F', format_str]
    output = sh(cmd).strip()

    panes_info = []
    for line in output.split('\n'):
        if not line:
            continue

        fields = line.split(',')
        if len(fields) != 9:
            continue

        # Use destructuring assignment for better readability and performance
        (pane_id, zoomed, active, top, height,
         left, width, in_mode, scroll_pos) = fields

        # Only show all panes in non-zoomed state, or only active pane in zoomed state
        if zoomed == "1" and active != "1":
            continue

        pane = PaneInfo(
            pane_id=pane_id,
            start_y=int(top),
            height=int(height),
            start_x=int(left),
            width=int(width)
        )

        # Optimize flag setting
        pane.copy_mode = (in_mode == "1")
        pane.scroll_position = int(scroll_pos or 0)

        panes_info.append(pane)

    return panes_info


class PaneInfo:
    __slots__ = ('pane_id', 'start_y', 'height', 'start_x', 'width',
                 'lines', 'positions', 'copy_mode', 'scroll_position')

    def __init__(self, pane_id, start_y, height, start_x, width):
        self.pane_id = pane_id
        self.start_y = start_y
        self.height = height
        self.start_x = start_x
        self.width = width
        self.lines = []
        self.positions = []
        self.copy_mode = False
        self.scroll_position = 0


def tmux_pane_id():
    # Get the ID of the pane that launched this script
    source_pane = os.environ.get('TMUX_PANE')
    return source_pane or '%0'


def get_terminal_size():
    """Get terminal size from tmux"""
    output = sh(
        ['tmux', 'display-message', '-p', '#{client_width},#{client_height}'])
    width, height = map(int, output.strip().split(','))
    return width, height - 1  # Subtract 1 from height


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
    """Optimized pane content capture"""
    if not pane.height or not pane.width:
        return []

    cmd = ['tmux', 'capture-pane', '-p', '-t', pane.pane_id]
    if pane.scroll_position > 0:
        end_pos = -(pane.scroll_position - pane.height + 1)
        cmd.extend(['-S', str(-pane.scroll_position), '-E', str(end_pos)])

    # Directly split and limit lines
    return sh(cmd)[:-1].split('\n')[:pane.height]


def tmux_move_cursor(pane, line_num, true_col):
    # Execute commands sequentially
    cmds = [
        ['tmux', 'select-pane', '-t', pane.pane_id]
    ]

    if not pane.copy_mode:
        cmds.append(['tmux', 'copy-mode', '-t', pane.pane_id])

    cmds.append(['tmux', 'send-keys', '-X', '-t', pane.pane_id, 'top-line'])

    if line_num > 0:
        cmds.append(['tmux', 'send-keys', '-X', '-t', pane.pane_id,
                    '-N', str(line_num), 'cursor-down'])

    cmds.append(['tmux', 'send-keys', '-X', '-t',
                pane.pane_id, 'start-of-line'])

    if true_col > 0:
        cmds.append(['tmux', 'send-keys', '-X', '-t', pane.pane_id,
                    '-N', str(true_col), 'cursor-right'])

    for cmd in cmds:
        sh(cmd)


class HintTree:
    def __init__(self):
        self.targets = {}  # Store single key mappings
        self.children = {}  # Store double key mapping subtrees

    def add(self, hint, target):
        if len(hint) == 1:
            self.targets[hint] = target
        else:
            first, rest = hint[0], hint[1]
            if first not in self.children:
                self.children[first] = HintTree()
            self.children[first].add(rest, target)

    def get(self, key_sequence):
        if len(key_sequence) == 1:
            return self.targets.get(key_sequence)
        first, rest = key_sequence[0], key_sequence[1]
        if first in self.children:
            return self.children[first].get(rest)
        return None


def generate_hints(keys: str, needed_count: Optional[int] = None) -> List[str]:
    """Generate hints with optimal single/double key distribution"""
    if not needed_count:
        needed_count = len(keys)**2

    keys_list = list(keys)
    key_count = len(keys_list)
    max_hints = key_count * key_count  # All possible double-char combinations

    if needed_count > max_hints:
        needed_count = max_hints

    # When needed hints count is less than or equal to available keys, use single chars
    if needed_count <= key_count:
        return keys_list[:needed_count]

    # Generate all possible double char combinations
    double_char_hints = []
    for prefix in keys_list:  # Including first char as prefix
        for suffix in keys_list:
            double_char_hints.append(prefix + suffix)

    # If we need maximum possible combinations, return all double-char hints
    if needed_count == max_hints:
        return double_char_hints

    # Dynamically calculate how many single chars to keep
    single_chars = 0
    for i in range(key_count, 0, -1):
        if needed_count <= (key_count - i + 1) * key_count:
            single_chars = i
            break

    hints = []
    # Take needed doubles from the end
    needed_doubles = needed_count - single_chars
    hints.extend(double_char_hints[-needed_doubles:])

    # Add single chars at the beginning
    hints[0:0] = keys_list[:single_chars]

    return hints[:needed_count]


@perf_timer()
def init_panes():
    """Initialize pane information with optimized info gathering"""
    panes = []
    max_x = 0
    padding_cache = {}

    # Batch get all pane info
    panes_info = get_initial_tmux_info()

    # Initialize empty padding cache - will be populated as needed
    padding_cache = {}

    # Optimize pane processing with list comprehension
    for pane in panes_info:
        # Only capture pane content when really needed
        if pane.height > 0 and pane.width > 0:
            pane.lines = tmux_capture_pane(pane)
            max_x = max(max_x, pane.start_x + pane.width)
            panes.append(pane)

    return panes, max_x, padding_cache


@perf_timer()
def draw_all_panes(panes, max_x, padding_cache, terminal_height, screen):
    """Draw all panes and their borders"""
    sorted_panes = sorted(panes, key=lambda p: p.start_y + p.height)

    for pane in sorted_panes:
        visible_height = min(pane.height, terminal_height - pane.start_y)

        # Draw content
        for y, line in enumerate(pane.lines[:visible_height]):
            visual_width = get_string_width(line)
            if visual_width < pane.width:
                padding_size = pane.width - visual_width
                if padding_size not in padding_cache:
                    padding_cache[padding_size] = ' ' * padding_size
                line = line + padding_cache[padding_size]
            screen.addstr(pane.start_y + y, pane.start_x, line[:pane.width])

        # Draw vertical borders
        if pane.start_x + pane.width < max_x:
            for y in range(pane.start_y, pane.start_y + visible_height):
                screen.addstr(y, pane.start_x + pane.width,
                              VERTICAL_BORDER, screen.A_DIM)

        # Draw horizontal borders
        end_y = pane.start_y + visible_height
        if end_y < terminal_height and pane != sorted_panes[-1]:
            screen.addstr(end_y, pane.start_x, HORIZONTAL_BORDER *
                          pane.width, screen.A_DIM)

    screen.refresh()


@perf_timer("Finding matches")
def find_matches(panes, search_ch):
    """Find all matches and return match list"""
    matches = []
    for pane in panes:
        for line_num, line in enumerate(pane.lines):
            # Search each position in the line
            pos = 0
            while pos < len(line):
                idx = line.lower().find(search_ch.lower(), pos)
                if idx == -1:
                    break

                # Calculate visual column position
                visual_col = sum(get_char_width(c) for c in line[:idx])
                matches.append((pane, line_num, visual_col))
                pos = idx + 1

    return matches


@perf_timer("Drawing hints")
def update_hints_display(screen, panes, hint_tree, current_key):
    """Update hint display based on current key sequence"""
    terminal_width, terminal_height = get_terminal_size()

    for pane in panes:
        for line_num, col, char, hint in pane.positions:
            y = pane.start_y + line_num
            x = pane.start_x + col

            # First restore the second character position to original character
            if len(hint) > 1:
                char_width = get_char_width(char)
                if x + char_width < pane.start_x + pane.width:
                    screen.addstr(y, x + char_width, char)

            # Then show new hints based on current input
            if hint.startswith(current_key):
                if len(hint) > len(current_key):
                    screen.addstr(y, x, hint[len(current_key)], screen.A_HINT2)

    screen.refresh()


def draw_all_hints(panes, terminal_height, screen):
    """Draw all hints across all panes"""
    for pane in panes:
        for line_num, col, char, hint in pane.positions:
            y = pane.start_y + line_num
            x = pane.start_x + col

            # Ensure position is within visible range
            if (y < min(pane.start_y + pane.height, terminal_height) and
                    x + get_char_width(char) <= pane.start_x + pane.width):

                # Always show first character
                screen.addstr(y, x, hint[0], screen.A_HINT1)

                # Only show second character for two-character hints
                if len(hint) > 1:
                    char_width = get_char_width(char)
                    if x + char_width < pane.start_x + pane.width:
                        screen.addstr(y, x + char_width,
                                      hint[1], screen.A_HINT2)

    screen.refresh()


@perf_timer("Total execution")
def main(screen: Screen):
    setup_logging()
    terminal_width, terminal_height = get_terminal_size()
    panes, max_x, padding_cache = init_panes()

    draw_all_panes(panes, max_x, padding_cache, terminal_height, screen)
    sh(['tmux', 'select-window', '-t', '{end}'])

    search_ch = getch()
    matches = find_matches(panes, search_ch)
    hints = generate_hints(KEYS, len(matches))

    # Build hint tree
    hint_tree = HintTree()
    for match, hint in zip(matches, hints):
        hint_tree.add(hint, match)
        pane, line_num, col = match
        pane.positions.append((line_num, col, pane.lines[line_num][col], hint))

    draw_all_hints(panes, terminal_height, screen)

    # Handle user input
    key_sequence = ""
    while True:
        ch = getch()
        if ch not in KEYS:
            return

        key_sequence += ch
        target = hint_tree.get(key_sequence)

        if target:
            pane, line_num, col = target
            true_col = get_true_position(pane.lines[line_num], col)
            tmux_move_cursor(pane, line_num, true_col)
            return  # Exit after finding and moving to target
        elif len(key_sequence) >= 2:  # If no target found after 2 chars
            return  # Exit program
        else:
            # Update display to show remaining possible hints
            update_hints_display(screen, panes, hint_tree, key_sequence)


if __name__ == '__main__':
    screen: Screen = Curses() if USE_CURSES else AnsiSequence()
    screen.init()
    try:
        main(screen)
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}", exc_info=True)
    finally:
        screen.cleanup()
