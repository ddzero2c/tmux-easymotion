#!/usr/bin/env python3
import curses
import functools
import itertools
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
from dataclasses import dataclass, field, fields
from typing import Any, List, Optional

_SCRIPT_START = time.perf_counter()


def _parse_tmux_version(version_str: str) -> tuple:
    """Parse a tmux version string (``tmux 3.6a`` or bare ``3.6a``) into
    (major, minor).

    Returns (0, 0) when the version cannot be parsed (e.g. ``tmux master``,
    ``tmux openbsd-6.6``). The fallback selects the pre-3.6 fixed-width tab
    behaviour, which matches every released tmux that shipped before
    position-aware tab rendering.
    """
    if "openbsd-" in version_str or "master" in version_str:
        return (0, 0)

    match = re.search(r"(?:next-)?(\d+)\.(\d+)", version_str)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def _detect_tmux_version() -> tuple:
    """Detect installed tmux version as (major, minor) via ``tmux -V``."""
    try:
        result = subprocess.run(
            ["tmux", "-V"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return (0, 0)
    return _parse_tmux_version(result.stdout.strip())


# Primed by set_tmux_version() (from the batched startup query's
# '#{version}') or lazily via 'tmux -V' on first tab-width lookup.
TMUX_VERSION: Optional[tuple] = None


def set_tmux_version(version_str: str) -> None:
    """Prime version-dependent behaviour from a version string."""
    global TMUX_VERSION
    TMUX_VERSION = _parse_tmux_version(version_str)


def _position_aware_tabs() -> bool:
    # tmux 3.6 changed tab rendering to be position-aware (terminal-correct),
    # matching the tab-stop behaviour expected by terminals. Older tmux
    # rendered tabs as a fixed 8-column glyph regardless of column.
    global TMUX_VERSION
    if TMUX_VERSION is None:
        TMUX_VERSION = _detect_tmux_version()
    return TMUX_VERSION >= (3, 6)


def _parse_option_lines(lines) -> dict:
    """Parse ``show-options -g`` output lines into a dict."""
    options = {}
    for line in lines:
        if " " in line:
            key, value = line.split(" ", 1)
            # Strip outer quotes and unescape inner quotes
            value = value.strip('"').replace('\\"', '"')
            options[key] = value
    return options


# Single options cache: primed by get_startup_info(), or filled lazily by
# _get_all_tmux_options() on first read.
_tmux_options: Optional[dict] = None


def _clear_options_cache() -> None:
    global _tmux_options
    _tmux_options = None


def _get_all_tmux_options() -> dict:
    """All global tmux options, fetched once (unless primed at startup)."""
    global _tmux_options
    if _tmux_options is None:
        try:
            result = subprocess.run(
                ["tmux", "show-options", "-g"],
                capture_output=True,
                text=True,
                check=False,
            )
            _tmux_options = _parse_option_lines(result.stdout.strip().split("\n"))
        except Exception:
            return {}
    return _tmux_options


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
    hint1_fg: str = field(default="1;31", metadata={"opt": "@easymotion-hint1-fg"})
    hint2_fg: str = field(default="1;32", metadata={"opt": "@easymotion-hint2-fg"})
    dim: str = field(default="2", metadata={"opt": "@easymotion-dim"})

    @classmethod
    def from_tmux(cls) -> "Config":
        """Load configuration from tmux options."""
        kwargs = {}
        for f in fields(cls):
            default = f.default
            default_str = str(default).lower() if f.type is bool else str(default)
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
    def transform_attr(self, attr) -> Any:
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

    def __init__(self, config: Optional["Config"] = None):
        config = config or Config()
        self.DIM = f"{self.ESC}[{config.dim}m"
        self.HINT1 = f"{self.ESC}[{config.hint1_fg}m"
        self.HINT2 = f"{self.ESC}[{config.hint2_fg}m"

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
            return self.HINT1
        elif attr == self.A_HINT2:
            return self.HINT2
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


_SGR_BASE_COLORS = {
    30: curses.COLOR_BLACK,
    31: curses.COLOR_RED,
    32: curses.COLOR_GREEN,
    33: curses.COLOR_YELLOW,
    34: curses.COLOR_BLUE,
    35: curses.COLOR_MAGENTA,
    36: curses.COLOR_CYAN,
    37: curses.COLOR_WHITE,
}


def _sgr_to_curses(codes: str):
    """Parse an SGR code string (e.g. "1;31" or "38;5;208") into a
    (foreground_color, attribute_flags) tuple for curses. Returns -1 for the
    foreground when no color is specified (keeps the terminal default).

    The curses backend supports a subset of SGR: bold (1), dim (2), underline
    (4), the basic (30-37) and bright (90-97) foregrounds, and 256-color
    foregrounds (38;5;N). Truecolor (38;2;r;g;b) and background codes are
    skipped; the default ANSI backend honors any SGR string."""
    fg = -1
    attr = 0
    parts = [p for p in codes.split(";") if p != ""]
    i = 0
    while i < len(parts):
        try:
            n = int(parts[i])
        except ValueError:
            i += 1
            continue
        if n == 1:
            attr |= curses.A_BOLD
        elif n == 2:
            attr |= curses.A_DIM
        elif n == 4:
            attr |= curses.A_UNDERLINE
        elif n in _SGR_BASE_COLORS:
            fg = _SGR_BASE_COLORS[n]
        elif 90 <= n <= 97:
            fg = _SGR_BASE_COLORS[n - 60]
            attr |= curses.A_BOLD
        elif n == 38 and i + 1 < len(parts) and parts[i + 1] == "5":
            if i + 2 < len(parts):
                try:
                    fg = int(parts[i + 2])
                except ValueError:
                    pass
            i += 2
        elif n == 38 and i + 1 < len(parts) and parts[i + 1] == "2":
            i += 4
        i += 1
    return fg, attr


class Curses(Screen):
    def __init__(self, config: Optional["Config"] = None):
        self.stdscr: Optional[curses.window] = None
        self.config = config or Config()

    @staticmethod
    def _init_pair(pair: int, fg: int):
        """Define a foreground/default color pair, falling back to the
        terminal default when fg is out of range for this terminal (e.g. a
        256-color code on an 8-color TERM, which would otherwise raise)."""
        if not 0 <= fg < curses.COLORS:
            fg = -1
        try:
            curses.init_pair(pair, fg, -1)
        except (curses.error, ValueError):
            pass

    def init(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        fg1, flags1 = _sgr_to_curses(self.config.hint1_fg)
        fg2, flags2 = _sgr_to_curses(self.config.hint2_fg)
        fgd, flagsd = _sgr_to_curses(self.config.dim)
        self._init_pair(1, fg1)
        self._init_pair(2, fg2)
        self._init_pair(3, fgd)
        self.attr_hint1 = curses.color_pair(1) | flags1
        self.attr_hint2 = curses.color_pair(2) | flags2
        self.attr_dim = curses.color_pair(3) | flagsd
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
            return self.attr_dim
        elif attr == self.A_HINT1:
            return self.attr_hint1
        elif attr == self.A_HINT2:
            return self.attr_hint2
        return curses.A_NORMAL

    def addstr(self, y: int, x: int, text: str, attr=0):
        if self.stdscr is None:
            return
        try:
            self.stdscr.addstr(y, x, text, self.transform_attr(attr))
        except curses.error:
            pass

    def refresh(self):
        if self.stdscr is None:
            return
        self.stdscr.refresh()

    def clear(self):
        if self.stdscr is None:
            return
        self.stdscr.clear()


def setup_logging(use_curses: bool = False):
    """Initialize logging configuration based on tmux options"""
    debug = get_tmux_option("@easymotion-debug", "false").lower() == "true"
    perf = get_tmux_option("@easymotion-perf", "false").lower() == "true"

    if not (debug or perf):
        logging.getLogger().disabled = True
        return

    log_file = os.path.expanduser("~/easymotion.log")
    # force=True: any logging call made before this point (e.g. sh() debug
    # logging inside the batched startup query) auto-installs a stderr
    # handler, which would turn this basicConfig into a silent no-op.
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format=f"%(asctime)s - %(levelname)s - {'CURSE' if use_curses else 'ANSI'} - %(message)s",
        force=True,
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


def calculate_tab_width(position: int, tab_size: int = 8) -> int:
    """Visual columns a tab consumes when starting at ``position``."""
    return tab_size - (position % tab_size)


# Zero-width code points beyond combining marks: ZWSP, ZWNJ, ZWJ, VS16.
_ZERO_WIDTH_CHARS = frozenset("​‌‍️")


@functools.lru_cache(maxsize=1024)
def _char_width_no_tab(char: str) -> int:
    if char in _ZERO_WIDTH_CHARS or unicodedata.combining(char):
        return 0
    # tmux merges combining marks into the preceding cell; zero-width
    # code points occupy no cell of their own
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


def get_char_width(char: str, position: int = 0) -> int:
    """Visual width of ``char``. ``position`` is the pane-local column
    and is only consulted for tabs — tmux expands tabs pane-locally.
    Pre-3.6 tmux always renders tabs as 8 cells; 3.6+ goes to the next
    pane-local 8-col tab stop.
    """
    if char == "\t":
        if _position_aware_tabs():
            return calculate_tab_width(position)
        return 8
    return _char_width_no_tab(char)


@functools.lru_cache(maxsize=1024)
def get_string_width(s: str) -> int:
    """Visual width of ``s`` (pane-local, accounting for wide chars and tabs)."""
    visual_pos = 0
    for char in s:
        visual_pos += get_char_width(char, visual_pos)
    return visual_pos


def get_true_position(line, target_col):
    """Convert visual column to string index, accounting for wide chars and tabs."""
    visual_pos = 0
    true_pos = 0
    while true_pos < len(line) and visual_pos < target_col:
        char_width = get_char_width(line[true_pos], visual_pos)
        visual_pos += char_width
        true_pos += 1
    return true_pos


def visual_slice(s: str, max_width: int) -> str:
    """Truncate/pad ``s`` to exactly ``max_width`` visible cells. Drops
    overflowing wide chars and pads with spaces. ``s`` must be tab-free."""
    visual_pos = 0
    out = []
    for char in s:
        w = get_char_width(char, visual_pos)
        if visual_pos + w > max_width:
            break
        out.append(char)
        visual_pos += w
    if visual_pos < max_width:
        out.append(" " * (max_width - visual_pos))
    return "".join(out)


def _expand_tabs(line: str) -> str:
    """Replace tabs with spaces using tmux's pane-local tab stops, so
    curses' screen-absolute tab handling can't disagree with tmux's
    rendering in split panes whose ``start_x`` is not a multiple of 8.
    """
    if "\t" not in line:
        return line
    out = []
    pos = 0
    for ch in line:
        if ch == "\t":
            w = get_char_width(ch, pos)
            out.append(" " * w)
            pos += w
        else:
            out.append(ch)
            pos += _char_width_no_tab(ch)
    return "".join(out)


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


def sh_tmux_batch(cmds: list) -> str:
    """Run several tmux commands in a single tmux invocation.

    tmux treats a literal ';' argv element as a command separator, so
    this costs one subprocess fork instead of one per command. Each
    sub-command still needs its own '-t' target.
    """
    argv = ["tmux"]
    for i, cmd in enumerate(cmds):
        if i:
            argv.append(";")
        argv.extend(cmd)
    return sh(argv)


_PANE_FORMAT = (
    "#{pane_id},#{window_zoomed_flag},#{pane_active},"
    "#{pane_top},#{pane_height},#{pane_left},#{pane_width},"
    "#{pane_in_mode},#{scroll_position},"
    "#{cursor_y},#{cursor_x},#{copy_cursor_y},#{copy_cursor_x},"
    "#{history_size},#{@easymotion_frozen_hist}"
)


def get_initial_tmux_info():
    """Get all needed tmux info in one optimized call"""
    output = sh(["tmux", "list-panes", "-F", _PANE_FORMAT]).strip()
    return _parse_pane_lines(output.split("\n"))


def _parse_pane_lines(lines) -> list:
    panes_info = []
    for line in lines:
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
            history_size,
            frozen_hist,
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
        pane.history_size = int(history_size or 0)
        pane.zoomed = zoomed == "1"
        # set while WE hold the pane frozen: history size at freeze time
        pane.frozen_hist = int(frozen_hist) if frozen_hist else None

        # Set cursor position
        if in_mode == "1":  # If in copy mode
            pane.cursor_y = int(copy_cursor_y)
            pane.cursor_x = int(copy_cursor_x)
        else:  # If not in copy mode, cursor is at bottom left
            pane.cursor_y = int(cursor_y)
            pane.cursor_x = int(cursor_x)

        panes_info.append(pane)

    return panes_info


# Separator line between variable-length sections of the batched startup
# query. Must not contain '%' (display-message expands format sequences)
# and only collides if a tmux option value equals it exactly.
_STARTUP_SEP = "EASYMOTION_SEP_e5a1"


@dataclass
class StartupInfo:
    panes_info: Optional[list]
    terminal_size: Optional[tuple]  # (width, height-1), None if no client
    window_id: str


def get_startup_info(window_target: Optional[str] = None) -> Optional[StartupInfo]:
    """Fetch everything easymotion needs at startup in ONE tmux invocation:
    version, client size, window id, global options, and pane geometry.

    Side effects: primes the tmux-options cache and the version-dependent
    tab behaviour, replacing the separate 'tmux -V' / 'show-options -g' /
    'display-message' / 'list-panes' subprocess calls.

    The batch is all-or-nothing: one failing sub-command (e.g. no client
    for display-message) or an unparsable section kills the whole call,
    so failure returns None and callers fall back to the lazy per-call
    queries.
    """
    try:
        return _fetch_startup_info(window_target)
    except Exception:
        # Logging isn't configured this early in the happy path (options
        # come from this very query); set it up now so the failure lands
        # in the log file instead of stderr. The lazy option fetch inside
        # setup_logging still works when only parsing failed.
        setup_logging()
        logging.error("Batched startup query failed", exc_info=True)
        return None


def _fetch_startup_info(window_target: Optional[str] = None) -> StartupInfo:
    global _tmux_options
    # In overlay-input mode this process runs in the FOCUSED overlay
    # window, so the source panes live in the last window: target '!'.
    panes_cmd = ["list-panes", "-F", _PANE_FORMAT]
    if window_target:
        panes_cmd += ["-t", window_target]
    out = sh_tmux_batch(
        [
            ["display-message", "-p", "#{version},#{client_width},#{client_height}"],
            _window_id_cmd(),
            ["show-options", "-g"],
            ["display-message", "-p", _STARTUP_SEP],
            panes_cmd,
        ]
    )
    lines = out.split("\n")
    version_str, client_w, client_h = lines[0].split(",")
    window_id = lines[1].strip()
    sep_idx = lines.index(_STARTUP_SEP, 2)

    set_tmux_version(version_str)
    _tmux_options = _parse_option_lines(lines[2:sep_idx])

    try:
        terminal_size = (int(client_w), int(client_h) - 1)
    except ValueError:  # no attached client (e.g. detached test server)
        terminal_size = None

    panes_info = _parse_pane_lines([ln for ln in lines[sep_idx + 1 :] if ln])
    return StartupInfo(panes_info, terminal_size, window_id)


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
        "history_size",
        "zoomed",
        "was_in_mode",
        "frozen",
        "frozen_hist",
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
        self.history_size = 0
        self.zoomed = False
        self.was_in_mode = False
        self.frozen = False
        self.frozen_hist = None


def get_terminal_size():
    """Get terminal size from tmux. Falls back to the window's size when
    no client is attached (headless test servers): window dimensions
    already exclude the status line, matching client_height - 1."""
    output = sh(["tmux", "display-message", "-p", "#{client_width},#{client_height}"])
    try:
        width, height = map(int, output.strip().split(","))
        return width, height - 1  # Subtract 1 from height
    except ValueError:
        output = sh(
            ["tmux", "display-message", "-p", "#{window_width},#{window_height}"]
        )
        width, height = map(int, output.strip().split(","))
        return width, height


def _window_id_cmd() -> list:
    """display-message argv (sans 'tmux') querying this script's window_id."""
    cmd = ["display-message", "-p"]
    pane_target = os.environ.get("TMUX_PANE")
    if pane_target:
        cmd.extend(["-t", pane_target])
    cmd.append("#{window_id}")
    return cmd


def get_current_window_id():
    """Return the window_id for the pane running this script"""
    return sh(["tmux", *_window_id_cmd()]).strip()


def getch(input_str=None, num_chars=1):
    """Get character(s) from the terminal (raw, via os.read — the
    buffered sys.stdin TextIO layer proved unreliable for raw pty reads
    on CI runners) or from ``input_str`` when provided.

    Args:
        input_str: Optional string. If None, read from stdin.
        num_chars: Number of characters to read (default: 1)
    """
    if input_str is None:
        import codecs

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        chars = ""
        try:
            tty.setraw(fd)
            while len(chars) < num_chars:
                data = os.read(fd, 64)
                if not data:
                    break
                chars += decoder.decode(data)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        ch = chars[:num_chars]
    else:
        ch = input_str[:num_chars]
    if "\x03" in ch:
        logging.info("Operation cancelled by user")
        exit(1)

    return ch


def _frozen_frame_path(pane_id: str) -> str:
    import tempfile

    return os.path.join(
        tempfile.gettempdir(),
        f"tmux_easymotion_{os.getuid()}_frame_{pane_id.lstrip('%')}",
    )


def tmux_capture_pane(pane):
    """Freeze the pane and capture its (now frozen) content.

    Entering copy-mode freezes the pane's view and coordinate system at
    that instant (semantics locked by test_copy_mode_freezes_view), so
    everything captured here stays valid for the whole overlay session.
    The capture reads the LIVE grid, so history_size is read before and
    after in the same invocation and the capture retried until stable.

    A pane can already be frozen by OUR previous jump (the target stays
    in copy-mode showing the frame the user jumped to). capture-pane
    cannot see a frozen view and the live grid may have moved on — but
    the frozen frame was ours to begin with, so it is cached to a
    per-pane temp file at freeze time and read back here (the
    @easymotion_frozen_hist pane option marks the freeze as ours). Panes
    the USER put in copy-mode themselves carry no marker; their frozen
    view is unknowable (documented limitation) and the live grid is
    captured.

    Panes frozen here must be released via release_frozen().
    """
    if not pane.height or not pane.width:
        return []

    if pane.copy_mode and pane.frozen_hist is not None:
        # re-trigger on a pane WE froze: serve the cached frozen frame
        pane.frozen = True
        pane.was_in_mode = False  # our freeze: release may cancel it
        try:
            with open(_frozen_frame_path(pane.pane_id)) as f:
                return f.read().split("\n")[: pane.height]
        except OSError:
            pass  # cache lost: fall through to a live capture

    base = ["capture-pane", "-p", "-t", pane.pane_id]
    if pane.scroll_position > 0:
        end_pos = -(pane.scroll_position - pane.height + 1)
        base.extend(["-S", str(-pane.scroll_position), "-E", str(end_pos)])

    hist_fmt = ["display-message", "-p", "-t", pane.pane_id, "#{history_size}"]
    mark_fmt = [
        "set-option", "-pF", "-t", pane.pane_id,
        "@easymotion_frozen_hist", "#{history_size}",
    ]
    rows: list = []
    for _ in range(3):
        cmds = []
        if not pane.frozen and not pane.copy_mode:
            cmds.append(["copy-mode", "-t", pane.pane_id])
            cmds.append(mark_fmt)
        cmds += [hist_fmt, base, hist_fmt]
        out = sh_tmux_batch(cmds)[:-1].split("\n")
        hist_a, rows, hist_b = out[0], out[1:-1], out[-1]
        if not pane.frozen:
            pane.was_in_mode = pane.copy_mode
            pane.frozen = True
            pane.copy_mode = True
        if hist_a == hist_b:
            break
    rows = rows[: pane.height]
    if not pane.was_in_mode:
        # cache the frozen frame for a later re-trigger on this pane.
        # Keep literal tabs: cursor-right steps through tmux's cell
        # buffer one char at a time, so true_col must count against
        # this same string.
        try:
            with open(_frozen_frame_path(pane.pane_id), "w") as f:
                f.write("\n".join(rows))
        except OSError:
            pass
    return rows


def release_frozen(panes, keep=None):
    """Leave copy-mode on every pane WE froze (not ones the user had in
    copy-mode already), except ``keep`` (the jump target stays put)."""
    cmds = []
    for p in panes:
        if p.frozen and p is not keep and not p.was_in_mode:
            cmds.append(["send-keys", "-X", "-t", p.pane_id, "cancel"])
            cmds.append(["set-option", "-p", "-t", p.pane_id,
                         "-u", "@easymotion_frozen_hist"])
            try:
                os.unlink(_frozen_frame_path(p.pane_id))
            except OSError:
                pass
        p.frozen = False
    if keep is not None:
        keep.frozen = False
    if cmds:
        sh_tmux_batch(cmds)


# Diagnostic trace of the last tmux_move_cursor run (tests dump it on
# failure so CI-only geometry issues carry their own evidence).
NAV_TRACE: list = []


def _cursor_steps(line: str, true_col: int) -> int:
    """copy-mode cursor-right steps to reach string index ``true_col``:
    the cursor moves one grid CELL per step, and zero-width chars
    (combining marks etc.) ride along with their base cell instead of
    costing a step of their own."""
    return sum(1 for ch in line[:true_col] if _char_width_no_tab(ch) > 0)


@perf_timer("Moving cursor")
def tmux_move_cursor(pane, line_num, true_col):
    """Move the copy-mode cursor to (line_num, true_col) of the captured
    view: guarded, anchored, verified, corrected.

    Copy-mode movement hazards this routes around (each reproduced in the
    test suite): start-of-line at the top of the view walks above it when
    that row continues a wrapped logical line, shifting scroll and every
    later row count; cursor-right/left wrap across lines instead of
    clamping; goto-line anchors at the last USED line, not the screen
    bottom. No single blind command sequence survives all of them, so the
    first shot uses the cheapest reliable path per state and a read-back
    loop repairs the rest — including restoring the original scroll so
    the user's view doesn't shift."""
    pid = pane.pane_id
    NAV_TRACE.clear()
    NAV_TRACE.append(
        f"target=({line_num},{true_col}) scroll={pane.scroll_position} "
        f"h={pane.height} hist={pane.history_size} copy={pane.copy_mode}"
    )

    line = pane.lines[line_num] if line_num < len(pane.lines) else ""

    # The pane was FROZEN at capture time (copy-mode pins the view and
    # its coordinates), so captured coordinates cannot go stale — no
    # retargeting or content re-checks needed. Only two things can break
    # the frozen state: zoom toggling (resets copy-mode scroll) and the
    # mode being exited underneath us; cancel in those cases.
    state = sh(
        ["tmux", "display-message", "-p", "-t", pid,
         "#{window_zoomed_flag},#{pane_in_mode}"]
    ).strip()
    zoomed, in_mode = state.split(",")
    NAV_TRACE.append(f"guard state: {state!r}")
    if (zoomed == "1") != pane.zoomed or in_mode != "1":
        NAV_TRACE.append("guard: CANCELLED (zoom/mode changed)")
        sh(["tmux", "display-message", "easymotion: pane changed, jump cancelled"])
        return

    steps = _cursor_steps(line, true_col)
    expected_cell = get_string_width(line[:true_col])

    cmds = [["select-pane", "-t", pid]]

    def x(*args):
        cmds.append(["send-keys", "-X", "-t", pid, *args])

    if pane.scroll_position > 0:
        # Scrolled pane: the view is necessarily full, so ``goto-line
        # <scroll>`` lands exactly on the bottom row of the wanted view
        # without disturbing scroll — immune to the top-of-view wrap
        # hazard. Climb from there.
        x("goto-line", str(pane.scroll_position))
        x("start-of-line")
        if pane.height - 1 > line_num:
            x("-N", str(pane.height - 1 - line_num), "cursor-up")
    else:
        # Unscrolled pane: top-line is exact (row 0). start-of-line may
        # still walk above the view when row 0 continues a wrapped line
        # in history — the verify loop repairs that case. The walk to the
        # first non-empty row primes tmux's lastcx/lastsx column bias so
        # cursor-down doesn't drag the cursor to line ends (tmux 3.6+).
        x("top-line")
        x("start-of-line")
        first_non_empty = next(
            (i for i, ln in enumerate(pane.lines) if ln), 0
        )
        rows_remaining = line_num
        if 0 < first_non_empty <= line_num:
            x("-N", str(first_non_empty), "cursor-down")
            x("start-of-line")
            rows_remaining -= first_non_empty
        if rows_remaining > 0:
            x("-N", str(rows_remaining), "cursor-down")
    if steps > 0:
        x("-N", str(steps), "cursor-right")
    NAV_TRACE.append(f"first shot: {cmds}")
    sh_tmux_batch(cmds)

    # Closed loop: verify the landing against measured state and repair.
    # Each round fixes ONE thing (scroll restore, then row, then column)
    # and re-measures — never start-of-line here: on a wrap-continuation
    # target row it walks to the logical line start and re-triggers the
    # very shift being repaired (reproduced on CI).
    for _ in range(4):
        out = sh(
            ["tmux", "display-message", "-p", "-t", pid,
             "#{copy_cursor_y},#{copy_cursor_x},#{scroll_position}"]
        ).strip()
        y_now, x_now, scroll_now = (int(v or 0) for v in out.split(","))
        NAV_TRACE.append(f"verify read: {out!r}")
        k = scroll_now - pane.scroll_position
        dy = line_num + k - y_now
        dx = expected_cell - x_now
        cmds = []
        if k > 0:
            # restore the user's view first; later rounds then work in
            # original view coordinates
            x("-N", str(k), "scroll-down")
        elif k < 0:
            x("-N", str(-k), "scroll-up")
        elif dy > 0:
            x("-N", str(dy), "cursor-down")
        elif dy < 0:
            x("-N", str(-dy), "cursor-up")
        elif dx > 0:
            # cell-count approximation of steps; wide chars make this an
            # overestimate that the next round shrinks
            x("-N", str(dx), "cursor-right")
        elif dx < 0:
            x("-N", str(-dx), "cursor-left")
        else:
            break
        NAV_TRACE.append(f"correction: {cmds}")
        sh_tmux_batch(cmds)


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
def init_panes(panes_info=None):
    """Initialize pane information with optimized info gathering"""
    panes = []
    max_x = 0

    if panes_info is None:
        panes_info = get_initial_tmux_info()

    # Optimize pane processing with list comprehension
    for pane in panes_info:
        # Only capture pane content when really needed
        if pane.height > 0 and pane.width > 0:
            pane.lines = tmux_capture_pane(pane)
            max_x = max(max_x, pane.start_x + pane.width)
            panes.append(pane)

    return panes, max_x


@perf_timer()
def draw_all_panes(
    panes,
    max_x,
    terminal_height,
    screen,
    vertical_border: str = "│",
    horizontal_border: str = "─",
):
    """Draw all panes and their borders"""
    sorted_panes = sorted(panes, key=lambda p: p.start_y + p.height)

    for pane in sorted_panes:
        visible_height = min(pane.height, terminal_height - pane.start_y)

        # Pre-expand tabs so curses can't re-expand them against screen-
        # absolute stops and shift content in non-aligned split panes.
        for y, line in enumerate(pane.lines[:visible_height]):
            sliced = visual_slice(_expand_tabs(line), pane.width)
            screen.addstr(pane.start_y + y, pane.start_x, sliced)

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


def _fold_for_search(line: str, case_sensitive: bool):
    """Return (haystack, fold_slices) for scanning ``line``.

    ``haystack`` is guaranteed index-aligned with ``line``. When lower()
    would change the string length (e.g. 'İ' -> 'i̇'), the original line
    is returned with ``fold_slices=True``, asking the caller to lower
    each slice before comparing instead.
    """
    if case_sensitive:
        return line, False
    lowered = line.lower()
    if len(lowered) == len(line):
        return lowered, False
    return line, True


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
    search_patterns = set(generate_smartsign_patterns(search_pattern, smartsign))
    if not case_sensitive:
        search_patterns = {p.lower() for p in search_patterns}

    for pane in panes:
        for line_num, line in enumerate(pane.lines):
            haystack, fold_slices = _fold_for_search(line, case_sensitive)
            # visual_col tracks the width of line[:width_pos]; advanced
            # lazily so match-free positions cost nothing extra.
            visual_col = 0
            width_pos = 0
            for pos in range(len(line) - pattern_length + 1):
                substring = haystack[pos : pos + pattern_length]
                if fold_slices:
                    substring = substring.lower()
                if substring in search_patterns:
                    while width_pos < pos:
                        visual_col += get_char_width(line[width_pos], visual_col)
                        width_pos += 1
                    matches.append((pane, line_num, visual_col))

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
def main(screen: Screen, config: Config, startup: Optional[StartupInfo] = None):
    setup_logging(config.use_curses)
    logging.info(
        f"Pre-main (startup query + config) took: "
        f"{time.perf_counter() - _SCRIPT_START:.3f} seconds"
    )
    # Null-object so every fallback below reads uniformly.
    startup = startup or StartupInfo(None, None, "")
    panes, max_x = init_panes(startup.panes_info)
    global _live_panes
    _live_panes = panes

    # Motion type and (optionally) the search chars from argv. Without
    # argv chars the overlay reads them from its OWN stdin: the binding
    # opens this window focused, panes are already frozen above, so the
    # user picks the target on a stable frame and early keystrokes just
    # buffer in our pty.
    motion_type = sys.argv[1] if len(sys.argv) > 1 else "s"
    if motion_type not in ("s", "s2"):
        logging.error(f"Invalid motion type: {motion_type}")
        release_frozen(panes)
        exit(1)
    num_chars = 2 if motion_type == "s2" else 1
    argv_chars = sys.argv[2] if len(sys.argv) > 2 else None

    terminal_width, terminal_height = (
        startup.terminal_size or get_terminal_size()
    )
    if argv_chars is None:
        # overlay-input mode: the window was created DETACHED — draw the
        # frozen frame in the background and only then switch the client
        # to it, so the user never sees a partially drawn overlay. Keys
        # pressed before the switch land in the frozen source pane's
        # copy-mode (harmless; worst case they cancel the freeze and the
        # jump guard aborts cleanly) — never in the user's shell.
        draw_all_panes(
            panes,
            max_x,
            terminal_height,
            screen,
            config.vertical_border,
            config.horizontal_border,
        )
        screen.refresh()
        overlay_window_id = startup.window_id or get_current_window_id()
        sh(["tmux", "select-window", "-t", overlay_window_id])

    logging.debug("awaiting search chars (stdin raw=%s tty=%s)"
                  % (argv_chars is None, sys.stdin.isatty()))
    raw = getch(argv_chars, num_chars)
    logging.debug(f"Raw input ({motion_type}): {repr(raw)}")
    search_pattern = raw.replace("\n", "").replace("\r", "")
    if len(search_pattern) < num_chars:
        release_frozen(panes)
        return
    matches = find_matches(
        panes,
        search_pattern,
        case_sensitive=config.case_sensitive,
        smartsign=config.smartsign,
    )

    # Check for matches
    if len(matches) == 0:
        sh(["tmux", "display-message", "no match"])
        release_frozen(panes)
        return
    # If only one match, jump directly
    if len(matches) == 1:
        pane, line_num, col = matches[0]
        true_col = get_true_position(pane.lines[line_num], col)
        release_frozen(panes, keep=pane)
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

    if argv_chars is not None:
        # legacy argv mode (command-prompt bindings): the frame wasn't
        # drawn yet and the overlay window was created detached
        draw_all_panes(
            panes,
            max_x,
            terminal_height,
            screen,
            config.vertical_border,
            config.horizontal_border,
        )
        overlay_window_id = startup.window_id or get_current_window_id()
        sh(["tmux", "select-window", "-t", overlay_window_id])
    draw_all_hints(positions, terminal_height, screen)

    # Handle user input
    key_sequence = ""
    while True:
        ch = getch()
        if ch not in config.hints:
            release_frozen(panes)
            return

        key_sequence += ch
        target = hint_mapping.get(key_sequence)

        if target:
            pane, line_num, col = target
            true_col = get_true_position(pane.lines[line_num], col)
            release_frozen(panes, keep=pane)
            tmux_move_cursor(pane, line_num, true_col)
            return  # Exit after finding and moving to target
        elif len(key_sequence) >= 2:  # If no target found after 2 chars
            release_frozen(panes)
            return  # Exit program
        else:
            # Update display to show remaining possible hints
            update_hints_display(screen, positions, key_sequence)


if __name__ == "__main__":
    # overlay-input mode (no search chars in argv): we run inside the
    # focused overlay window; the source panes are in the LAST window
    _source_window = None
    if "--source" in sys.argv:
        i = sys.argv.index("--source")
        _source_window = sys.argv[i + 1]
        del sys.argv[i : i + 2]
    _overlay_input = len(sys.argv) <= 2
    # Switch stdin to raw immediately so keys typed right after the
    # binding (before the frame is drawn) land in the input queue for
    # getch instead of being absorbed by the canonical line editor. Keys
    # in the first ~25ms (interpreter startup) can still be lost — below
    # any human keypress interval.
    _saved_termios = None
    if _overlay_input and sys.stdin.isatty():
        _saved_termios = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())
    startup = get_startup_info(
        _source_window or ("!" if _overlay_input else None)
    )
    config = Config.from_tmux()
    screen: Screen = Curses(config) if config.use_curses else AnsiSequence(config)
    try:
        screen.init()
        main(screen, config, startup)
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}", exc_info=True)
    finally:
        release_frozen(_live_panes)
        if _saved_termios is not None:
            termios.tcsetattr(
                sys.stdin.fileno(), termios.TCSADRAIN, _saved_termios
            )
        screen.cleanup()
