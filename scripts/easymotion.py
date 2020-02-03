#!/usr/bin/env python3
import curses
import re
import os
import itertools

KEYS='asdghklqwertyuiopzxcvbnmfj'

def pyshell(cmd):
    return os.popen(cmd).read()

def tmux_pane_id():
    id_pattern = re.compile('%[0-9]+')
    pyshell('tmux last-window')
    id = pyshell('tmux display-message -p "#{pane_id}"').strip()
    pyshell('tmux last-window')
    if re.match(id_pattern, id):
        return id
    else:
        '%0'

def tmux_capture_pane(pane_id):
    return pyshell('tmux capture-pane -p -t {}'.format(pane_id))[:-1]

def fill_pane_content_with_space(pane_content, width):
    lines = pane_content.splitlines()
    return ''.join(['{text:<{length}}'.format(text=line, length=width) for line in lines])[:-1]

def tmux_move_cursor(pane_id, position):
    pyshell('tmux copy-mode -t {id}; tmux send-keys -X -t {id} top-line; tmux send-keys -X -t {id} -N {pos} cursor-right'
            .format(id=pane_id, pos=position))

def generate_hints(keys):
    def _generate_hints(keys):
        hints = [''.join(k) for k in itertools.product(keys, keys)]
        while hints:
            yield hints.pop(0)

    return [h for h in _generate_hints(keys)]

RED = 1
GREEN = 2

def main(stdscr):
    pane_id = tmux_pane_id()
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

    stdscr.addstr(0, 0, fixed_width_pane)
    stdscr.refresh()
    search_ch = chr(stdscr.getch())

    positions = [m.start() for m in re.finditer(search_ch, captured_pane.lower())]
    fixed_positions = [m.start() for m in re.finditer(search_ch, fixed_width_pane.lower())]

    for i, p in enumerate(fixed_positions):
        x = p % width
        y = p // width
        stdscr.addstr(y, x, hints[i][0], curses.color_pair(RED))
        if p+1 < len(fixed_width_pane):
            stdscr.addstr(y, x+1, hints[i][1], curses.color_pair(GREEN))
    stdscr.refresh()
    ch1 = chr(stdscr.getch())
    if  ch1 not in KEYS:
        exit(0)
    ch2 = chr(stdscr.getch())
    if  ch2 not in KEYS:
        exit(0)
    tmux_move_cursor(pane_id, positions[hints_dict[ch1+ch2]])

curses.wrapper(main)
