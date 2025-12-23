#!/usr/bin/env python3
import curses
import functools
import itertools
import logging
import os
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from typing import List, Optional


@functools.lru_cache(maxsize=1)
def _get_all_tmux_options() -> dict:
    """Batch read all tmux options in one subprocess call."""
    try:
        result = subprocess.run(
            ["tmux", "show-options", "-g"], capture_output=True, text=True, check=False
        )
        options = {}
        for line in result.stdout.strip().split("\n"):
            if " " in line:
                key, value = line.split(" ", 1)
                options[key] = value.strip('"')
        return options
    except Exception:
        return {}


def get_tmux_option(option: str, default: str) -> str:
    """Get tmux option value, falling back to default if not set."""
    return _get_all_tmux_options().get(option, default)


@dataclass
class Config:
    """Configuration for easymotion."""

    hints: str = field(
        default="asdghklqwertyuiopzxcvbnmfj;", metadata={"opt": "@easymotion-hints"}
    )
    case_sensitive: bool = field(
        default=False, metadata={"opt": "@easymotion-case-sensitive"}
    )
    smartsign: bool = field(default=False, metadata={"opt": "@easymotion-smartsign"})
    vertical_border: str = field(
        default="│", metadata={"opt": "@easymotion-vertical-border"}
    )
    horizontal_border: str = field(
        default="─", metadata={"opt": "@easymotion-horizontal-border"}
    )
    use_curses: bool = field(default=False, metadata={"opt": "@easymotion-use-curses"})

    @classmethod
    def from_tmux(cls) -> "Config":
        """Load configuration from tmux options."""
        kwargs = {}
        for f in fields(cls):
            default_str = str(f.default).lower() if f.type is bool else f.default
            raw = get_tmux_option(f.metadata["opt"], default_str)
            kwargs[f.name] = raw.lower() == "true" if f.type is bool else raw
        return cls(**kwargs)


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
    ESC = "\033"
    CLEAR = f"{ESC}[2J"
    CLEAR_LINE = f"{ESC}[2K"
    HIDE_CURSOR = f"{ESC}[?25l"
    SHOW_CURSOR = f"{ESC}[?25h"
    RESET = f"{ESC}[0m"
    DIM = f"{ESC}[2m"
    RED = f"{ESC}[1;31m"
    GREEN = f"{ESC}[1;32m"

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
        return ""

    def addstr(self, y: int, x: int, text: str, attr=0):
        attr_str = self.transform_attr(attr)
        if attr_str:
            sys.stdout.write(f"{self.ESC}[{y + 1};{x + 1}H{attr_str}{text}{self.RESET}")
        else:
            sys.stdout.write(f"{self.ESC}[{y + 1};{x + 1}H{text}")

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


def setup_logging(use_curses: bool = False):
    """Initialize logging configuration based on tmux options"""
    debug = get_tmux_option("@easymotion-debug", "false").lower() == "true"
    perf = get_tmux_option("@easymotion-perf", "false").lower() == "true"

    if not (debug or perf):
        logging.getLogger().disabled = True
        return

    log_file = os.path.expanduser("~/easymotion.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format=f"%(asctime)s - %(levelname)s - {'CURSE' if use_curses else 'ANSI'} - %(message)s",
    )


def perf_timer(func_name=None):
    """Performance timing decorator that only logs when perf is enabled"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            perf = get_tmux_option("@easymotion-perf", "false").lower() == "true"
            if not perf:
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
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


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
    try:
        result = subprocess.run(
            cmd, shell=False, text=True, capture_output=True, check=True
        ).stdout

        logging.debug(f"Command: {cmd}")
        logging.debug(f"Result: {result}")
        logging.debug("-" * 40)

        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing {cmd}: {str(e)}")
        raise


def get_initial_tmux_info():
    """Get all needed tmux info in one optimized call"""
    format_str = (
        "#{pane_id},#{window_zoomed_flag},#{pane_active},"
        + "#{pane_top},#{pane_height},#{pane_left},#{pane_width},"
        + "#{pane_in_mode},#{scroll_position},"
        + "#{cursor_y},#{cursor_x},#{copy_cursor_y},#{copy_cursor_x}"
    )

    cmd = ["tmux", "list-panes", "-F", format_str]
    output = sh(cmd).strip()

    panes_info = []
    for line in output.split("\n"):
        if not line:
            continue

        fields = line.split(",")
        # Use destructuring assignment for better readability and performance
        (
            pane_id,
            zoomed,
            active,
            top,
            height,
            left,
            width,
            in_mode,
            scroll_pos,
            cursor_y,
            cursor_x,
            copy_cursor_y,
            copy_cursor_x,
        ) = fields

        # Only show all panes in non-zoomed state, or only active pane in zoomed state
        if zoomed == "1" and active != "1":
            continue

        pane = PaneInfo(
            pane_id=pane_id,
            active=active == "1",
            start_y=int(top),
            height=int(height),
            start_x=int(left),
            width=int(width),
        )

        # Optimize flag setting
        pane.copy_mode = in_mode == "1"
        pane.scroll_position = int(scroll_pos or 0)

        # Set cursor position
        if in_mode == "1":  # If in copy mode
            pane.cursor_y = int(copy_cursor_y)
            pane.cursor_x = int(copy_cursor_x)
        else:  # If not in copy mode, cursor is at bottom left
            pane.cursor_y = int(cursor_y)
            pane.cursor_x = int(cursor_x)

        panes_info.append(pane)

    return panes_info


class PaneInfo:
    __slots__ = (
        "pane_id",
        "active",
        "start_y",
        "height",
        "start_x",
        "width",
        "lines",
        "positions",
        "copy_mode",
        "scroll_position",
        "cursor_y",
        "cursor_x",
    )

    def __init__(self, pane_id, active, start_y, height, start_x, width):
        self.active = active
        self.pane_id = pane_id
        self.start_y = start_y
        self.height = height
        self.start_x = start_x
        self.width = width
        self.lines = []
        self.positions = []
        self.copy_mode = False
        self.scroll_position = 0
        self.cursor_y = 0
        self.cursor_x = 0


def get_terminal_size():
    """Get terminal size from tmux"""
    output = sh(["tmux", "display-message", "-p", "#{client_width},#{client_height}"])
    width, height = map(int, output.strip().split(","))
    return width, height - 1  # Subtract 1 from height


def get_current_window_id():
    """Return the window_id for the pane running this script"""
    pane_target = os.environ.get("TMUX_PANE")
    cmd = ["tmux", "display-message", "-p"]
    if pane_target:
        cmd.extend(["-t", pane_target])
    cmd.append("#{window_id}")
    return sh(cmd).strip()


def getch(input_str=None, num_chars=1):
    """Get character(s) from terminal or file

    Args:
        input_str: Optional string. If None, read from stdin.
        num_chars: Number of characters to read (default: 1)
    """
    if input_str is None:
        # Read from stdin
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(num_chars)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        ch = input_str[:num_chars]
    if ch == "\x03":
        logging.info("Operation cancelled by user")
        exit(1)

    return ch


def tmux_capture_pane(pane):
    """Optimized pane content capture"""
    if not pane.height or not pane.width:
        return []

    cmd = ["tmux", "capture-pane", "-p", "-t", pane.pane_id]
    if pane.scroll_position > 0:
        end_pos = -(pane.scroll_position - pane.height + 1)
        cmd.extend(["-S", str(-pane.scroll_position), "-E", str(end_pos)])

    # Directly split and limit lines
    return sh(cmd)[:-1].split("\n")[: pane.height]


def tmux_move_cursor(pane, line_num, true_col):
    # Execute commands sequentially
    cmds = [["tmux", "select-pane", "-t", pane.pane_id]]

    if not pane.copy_mode:
        cmds.append(["tmux", "copy-mode", "-t", pane.pane_id])

    cmds.append(["tmux", "send-keys", "-X", "-t", pane.pane_id, "top-line"])
    # Ensure we always start from column 0 of the *screen line*; doing this
    # before moving down avoids "start-of-line" jumping to the beginning of a
    # wrapped *logical* line.
    cmds.append(["tmux", "send-keys", "-X", "-t", pane.pane_id, "start-of-line"])

    if line_num > 0:
        cmds.append(
            [
                "tmux",
                "send-keys",
                "-X",
                "-t",
                pane.pane_id,
                "-N",
                str(line_num),
                "cursor-down",
            ]
        )

    if true_col > 0:
        cmds.append(
            [
                "tmux",
                "send-keys",
                "-X",
                "-t",
                pane.pane_id,
                "-N",
                str(true_col),
                "cursor-right",
            ]
        )

    for cmd in cmds:
        sh(cmd)


def assign_hints_by_distance(
    matches, cursor_y, cursor_x, hints_keys: str = "asdghklqwertyuiopzxcvbnmfj;"
):
    """Sort matches by distance and assign hints"""
    # Calculate distances and sort
    matches_with_dist = []
    for match in matches:
        pane, line_num, col = match
        dist = (pane.start_y + line_num - cursor_y) ** 2 + (
            pane.start_x + col - cursor_x
        ) ** 2
        matches_with_dist.append((dist, match))

    matches_with_dist.sort(key=lambda x: x[0])  # Sort by distance

    # Generate hints and create mapping
    hints = generate_hints(hints_keys, len(matches_with_dist))
    logging.debug(f"{hints}")
    return {hint: match for (_, match), hint in zip(matches_with_dist, hints)}


def generate_hints(keys: str, needed_count: Optional[int] = None) -> List[str]:
    """Generate hints with optimal single/double key distribution"""
    if not needed_count:
        needed_count = len(keys) ** 2

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
    for prefix in keys_list:
        for suffix in keys_list:
            double_char_hints.append(prefix + suffix)

    # Dynamically calculate how many single chars to keep
    single_chars = 0
    for i in range(key_count, 0, -1):
        if needed_count <= (key_count - i) * key_count + i:
            single_chars = i
            break

    hints = []
    # Add single chars at the beginning
    single_char_hints = keys_list[:single_chars]
    hints.extend(single_char_hints)

    # Filter out double char hints that start with any single char hint
    filtered_doubles = [h for h in double_char_hints if h[0] not in single_char_hints]

    # Take needed doubles
    needed_doubles = needed_count - single_chars
    hints.extend(filtered_doubles[:needed_doubles])

    return hints[:needed_count]


@perf_timer()
def init_panes():
    """Initialize pane information with optimized info gathering"""
    panes = []
    max_x = 0
    padding_cache = {}

    # Batch get all pane info
    panes_info = get_initial_tmux_info()

    # Optimize pane processing with list comprehension
    for pane in panes_info:
        # Only capture pane content when really needed
        if pane.height > 0 and pane.width > 0:
            pane.lines = tmux_capture_pane(pane)
            max_x = max(max_x, pane.start_x + pane.width)
            panes.append(pane)

    return panes, max_x, padding_cache


@perf_timer()
def draw_all_panes(
    panes,
    max_x,
    padding_cache,
    terminal_height,
    screen,
    vertical_border: str = "│",
    horizontal_border: str = "─",
):
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
                    padding_cache[padding_size] = " " * padding_size
                line = line + padding_cache[padding_size]
            screen.addstr(pane.start_y + y, pane.start_x, line[: pane.width])

        # Draw vertical borders
        if pane.start_x + pane.width < max_x:
            for y in range(pane.start_y, pane.start_y + visible_height):
                screen.addstr(
                    y, pane.start_x + pane.width, vertical_border, screen.A_DIM
                )

        # Draw horizontal borders
        end_y = pane.start_y + visible_height
        if end_y < terminal_height and pane != sorted_panes[-1]:
            screen.addstr(
                end_y, pane.start_x, horizontal_border * pane.width, screen.A_DIM
            )

    screen.refresh()


def generate_smartsign_patterns(
    pattern,
    smartsign: bool = False,
    # Mutable default as "static" variable - created once at function definition
    _table: dict = {
        "1": "!",
        "2": "@",
        "3": "#",
        "4": "$",
        "5": "%",
        "6": "^",
        "7": "&",
        "8": "*",
        "9": "(",
        "0": ")",
        "-": "_",
        "=": "+",
        "[": "{",
        "]": "}",
        "\\": "|",
        ";": ":",
        "'": '"',
        "`": "~",
        ",": "<",
        ".": ">",
        "/": "?",
    },
):
    """Generate all smartsign variants for ANY pattern

    This is a generic function that works for patterns of any length.
    Each character position is independently expanded if it has a smartsign mapping.
    This enables smartsign support for all search modes (s, s2, s3, etc.)

    Args:
        pattern: String of any length
        smartsign: Whether smartsign feature is enabled

    Returns:
        List of pattern variants (includes original pattern)

    Examples:
        "3" -> ["3", "#"]
        "3," -> ["3,", "#,", "3<", "#<"]
        "ab" -> ["ab"]
        "3x5" -> ["3x5", "#x5", "3x%", "#x%"]  # Future: 3-char support
    """
    if not smartsign:
        return [pattern]

    # For each character position, collect possible characters
    char_options = []
    for ch in pattern:
        options = [ch]
        # Add smartsign variant if exists
        if ch in _table:
            options.append(_table[ch])
        char_options.append(options)

    # Generate all combinations (Cartesian product)
    patterns = ["".join(combo) for combo in itertools.product(*char_options)]
    return patterns


@perf_timer("Finding matches")
def find_matches(
    panes, search_pattern, case_sensitive: bool = False, smartsign: bool = False
):
    """Generic pattern matching with smartsign support

    This function is pattern-agnostic - it works for any search pattern,
    regardless of how that pattern was generated (s, s2, bd-w, etc.)
    Smartsign is automatically applied via generate_smartsign_patterns().

    Args:
        panes: List of PaneInfo objects
        search_pattern: String to search for (1 or more characters)
        case_sensitive: Whether to match case-sensitively
        smartsign: Whether to enable smartsign matching
    """
    matches = []
    pattern_length = len(search_pattern)

    # GENERIC: Apply smartsign transformation (works for any pattern length)
    search_patterns = generate_smartsign_patterns(search_pattern, smartsign)

    for pane in panes:
        for line_num, line in enumerate(pane.lines):
            # Check each position in the line
            for pos in range(len(line)):
                # For multi-char search, make sure we have enough characters
                if pos + pattern_length > len(line):
                    continue

                # Get substring at current position
                substring = line[pos : pos + pattern_length]

                # Skip if substring would split a wide character
                if pattern_length > 1:
                    # Check if we're in the middle of a wide char
                    if pos > 0 and get_char_width(line[pos - 1]) == 2:
                        # Check if previous char's visual position overlaps with current pos
                        visual_before = sum(get_char_width(c) for c in line[: pos - 1])
                        visual_at_pos = sum(get_char_width(c) for c in line[:pos])
                        if visual_at_pos - visual_before == 1:
                            # We're at the second half of a wide char, skip
                            continue

                # Check against all search patterns
                for pattern in search_patterns:
                    matched = False
                    if case_sensitive:
                        matched = substring == pattern
                    else:
                        matched = substring.lower() == pattern.lower()

                    if matched:
                        visual_col = sum(get_char_width(c) for c in line[:pos])
                        matches.append((pane, line_num, visual_col))
                        break  # Found match, no need to check other patterns

    return matches


@perf_timer("Drawing hints")
def update_hints_display(screen, positions, current_key):
    """Update hint display based on current key sequence"""
    for screen_y, screen_x, pane_right_edge, char, next_char, hint in positions:
        logging.debug(f"{screen_x} {pane_right_edge} {char} {next_char} {hint}")
        if hint.startswith(current_key):
            next_x = screen_x + get_char_width(char)
            if next_x < pane_right_edge:
                # Use space if next_char is empty (end of line case)
                restore_char = next_char if next_char else " "
                logging.debug(f"Restoring next char {next_x} {restore_char}")
                screen.addstr(screen_y, next_x, restore_char)
        else:
            logging.debug(f"Non-matching hint {screen_x} {screen_y} {char}")
            # Restore original character for non-matching hints
            screen.addstr(screen_y, screen_x, char)
            # Always restore second character
            next_x = screen_x + get_char_width(char)
            if next_x < pane_right_edge:
                # Use space if next_char is empty (end of line case)
                restore_char = next_char if next_char else " "
                logging.debug(f"Restoring next char {next_x} {restore_char}")
                screen.addstr(screen_y, next_x, restore_char)
            continue

        # For matching hints:
        if len(hint) > len(current_key):
            # Show remaining hint character
            screen.addstr(screen_y, screen_x, hint[len(current_key)], screen.A_HINT2)
        else:
            # If hint is fully entered, restore all original characters
            screen.addstr(screen_y, screen_x, char)
            next_x = screen_x + get_char_width(char)
            if next_x < pane_right_edge:
                # Use space if next_char is empty (end of line case)
                restore_char = next_char if next_char else " "
                screen.addstr(screen_y, next_x, restore_char)

    screen.refresh()


def draw_all_hints(positions, terminal_height, screen):
    """Draw all hints across all panes"""
    for screen_y, screen_x, pane_right_edge, char, next_char, hint in positions:
        if screen_y >= terminal_height:
            continue

        # Draw first character of hint
        screen.addstr(screen_y, screen_x, hint[0], screen.A_HINT1)

        # Draw second character if hint has two chars and space allows
        if len(hint) > 1:
            next_x = screen_x + get_char_width(char)
            if next_x < pane_right_edge:
                screen.addstr(screen_y, next_x, hint[1], screen.A_HINT2)

    screen.refresh()


@perf_timer("Total execution")
def main(screen: Screen, config: Config):
    setup_logging(config.use_curses)
    panes, max_x, padding_cache = init_panes()

    # Get motion type from command line argument
    motion_type = sys.argv[1] if len(sys.argv) > 1 else "s"

    # Determine search mode and find matches
    if motion_type == "s":
        # 1 char search
        search_pattern = getch(sys.argv[2], 1)
        search_pattern = search_pattern.replace("\n", "").replace("\r", "")
        if not search_pattern:
            return
        matches = find_matches(
            panes,
            search_pattern,
            case_sensitive=config.case_sensitive,
            smartsign=config.smartsign,
        )
    elif motion_type == "s2":
        # 2 char search
        raw_input = getch(sys.argv[2], 2)
        logging.debug(f"Raw input (s2): {repr(raw_input)}")
        search_pattern = raw_input.replace("\n", "").replace("\r", "")
        logging.debug(f"Search pattern (s2): {repr(search_pattern)}")
        if not search_pattern:
            return
        matches = find_matches(
            panes,
            search_pattern,
            case_sensitive=config.case_sensitive,
            smartsign=config.smartsign,
        )
    else:
        logging.error(f"Invalid motion type: {motion_type}")
        exit(1)

    # Check for matches
    if len(matches) == 0:
        sh(["tmux", "display-message", "no match"])
        return
    # If only one match, jump directly
    if len(matches) == 1:
        pane, line_num, col = matches[0]
        true_col = get_true_position(pane.lines[line_num], col)
        tmux_move_cursor(pane, line_num, true_col)
        return

    # Get cursor position from current pane
    current_pane = next(p for p in panes if p.active)
    cursor_y = current_pane.start_y + current_pane.cursor_y
    cursor_x = current_pane.start_x + current_pane.cursor_x
    logging.debug(f"Cursor position: {current_pane.pane_id}, {cursor_y}, {cursor_x}")

    # Replace HintTree with direct hint assignment
    hint_mapping = assign_hints_by_distance(matches, cursor_y, cursor_x, config.hints)

    # Create flat positions list with all needed info
    positions = []
    for hint, (pane, line_num, visual_col) in hint_mapping.items():
        # make sure index is in valid range
        if line_num < len(pane.lines):
            line = pane.lines[line_num]
            #  convert visual column to actual column
            true_col = get_true_position(line, visual_col)
            if true_col < len(line):
                char = line[true_col]
                next_char = line[true_col + 1] if true_col + 1 < len(line) else ""
                positions.append(
                    (
                        pane.start_y + line_num,  # screen_y
                        pane.start_x + visual_col,  # screen_x
                        pane.start_x + pane.width,  # pane_right_edge
                        char,  # original char at hint position
                        next_char,  # original char at second hint position (if exists)
                        hint,
                    )
                )

    terminal_width, terminal_height = get_terminal_size()
    draw_all_panes(
        panes,
        max_x,
        padding_cache,
        terminal_height,
        screen,
        config.vertical_border,
        config.horizontal_border,
    )
    draw_all_hints(positions, terminal_height, screen)
    overlay_window_id = get_current_window_id()
    sh(["tmux", "select-window", "-t", overlay_window_id])

    # Handle user input
    key_sequence = ""
    while True:
        ch = getch()
        if ch not in config.hints:
            return

        key_sequence += ch
        target = hint_mapping.get(key_sequence)

        if target:
            pane, line_num, col = target
            true_col = get_true_position(pane.lines[line_num], col)
            tmux_move_cursor(pane, line_num, true_col)
            return  # Exit after finding and moving to target
        elif len(key_sequence) >= 2:  # If no target found after 2 chars
            return  # Exit program
        else:
            # Update display to show remaining possible hints
            update_hints_display(screen, positions, key_sequence)


if __name__ == "__main__":
    config = Config.from_tmux()
    screen: Screen = Curses() if config.use_curses else AnsiSequence()
    screen.init()
    try:
        main(screen, config)
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}", exc_info=True)
    finally:
        screen.cleanup()
