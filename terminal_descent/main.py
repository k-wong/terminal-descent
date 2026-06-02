from __future__ import annotations

import argparse
import curses
import sys

from .game import GameEngine, SaveManager
from .render import choose_profile, render, render_inventory


MOVES = {
    curses.KEY_UP: (0, -1),
    curses.KEY_DOWN: (0, 1),
    curses.KEY_LEFT: (-1, 0),
    curses.KEY_RIGHT: (1, 0),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a terminal dungeon crawler.")
    parser.add_argument("--charset", choices=["unicode", "ascii"], default="unicode")
    args = parser.parse_args(argv)
    return curses.wrapper(lambda stdscr: _run(stdscr, args.charset))


def _run(stdscr, charset: str) -> int:
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    profile = choose_profile(charset, stdscr)
    save_manager = SaveManager()
    while True:
        choice = _menu(stdscr, save_manager.exists(), profile.name)
        if choice == "quit":
            return 0
        if choice == "continue":
            try:
                engine = GameEngine.load(save_manager)
            except Exception:
                save_manager.delete()
                engine = GameEngine.new(save_manager=save_manager)
                engine.log("The save was unreadable, so a new run began.")
        else:
            engine = GameEngine.new(save_manager=save_manager)
        _play(stdscr, engine, profile, save_manager)


def _menu(stdscr, has_save: bool, charset: str) -> str:
    options = ["continue", "new run", "quit"] if has_save else ["new run", "quit"]
    selected = 0
    while True:
        stdscr.erase()
        _add(stdscr, 1, 2, "Terminal Descent")
        _add(stdscr, 2, 2, f"charset: {charset}")
        for i, option in enumerate(options):
            prefix = ">" if i == selected else " "
            _add(stdscr, 5 + i, 4, f"{prefix} {option.title()}")
        stdscr.refresh()
        key = stdscr.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(options)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(options)
        elif key in {curses.KEY_ENTER, ord("\n"), ord("\r")}:
            return "new" if options[selected] == "new run" else options[selected]


def _play(stdscr, engine: GameEngine, profile, save_manager: SaveManager) -> None:
    while True:
        render(stdscr, engine, profile)
        if engine.state.dead or engine.state.won:
            stdscr.getch()
            save_manager.delete()
            return
        key = stdscr.getch()
        if key in MOVES:
            dx, dy = MOVES[key]
            engine.move_player(dx, dy)
        elif key == ord("x"):
            engine.wait()
        elif key == ord("z"):
            engine.pickup()
        elif key == ord("v"):
            engine.descend()
        elif key == ord("i"):
            _inventory(stdscr, engine, profile)
        elif key == ord("q"):
            engine.autosave()
            return


def _inventory(stdscr, engine: GameEngine, profile) -> None:
    render_inventory(stdscr, engine, profile)
    key = stdscr.getch()
    if key in {27, ord("q")}:
        return
    index = key - ord("a")
    if 0 <= index < 26:
        engine.use_inventory(index)


def _add(stdscr, y: int, x: int, text: str) -> None:
    try:
        stdscr.addstr(y, x, text)
    except curses.error:
        pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
