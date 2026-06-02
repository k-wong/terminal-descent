from __future__ import annotations

import curses
import locale
import os
import unicodedata

from .game import GameEngine
from .models import EquipmentSlot, Item, Tile


class GlyphProfile:
    def __init__(self, name: str, glyphs: dict[str, str]) -> None:
        self.name = name
        self.glyphs = glyphs

    def __getitem__(self, key: str) -> str:
        return self.glyphs[key]


UNICODE_PROFILE = GlyphProfile(
    "unicode",
    {
        "wall": "█",
        "floor": "·",
        "door": "+",
        "stairs": "v",
        "unseen": "▓",
        "explored": "░",
        "hud_h": "═",
        "hud_v": "║",
        "hud_tl": "╔",
        "hud_tr": "╗",
        "hud_bl": "╚",
        "hud_br": "╝",
        "player": "ö",
        "boss": "Ω",
    },
)

ASCII_PROFILE = GlyphProfile(
    "ascii",
    {
        "wall": "#",
        "floor": ".",
        "door": "+",
        "stairs": "v",
        "unseen": " ",
        "explored": ".",
        "hud_h": "-",
        "hud_v": "|",
        "hud_tl": "+",
        "hud_tr": "+",
        "hud_bl": "+",
        "hud_br": "+",
        "player": "o",
        "boss": "Ø",
    },
)


YOU_DIED_ART = (
    "▓██   ██▓ ▒█████   █    ██    ▓█████▄  ██▓▓█████ ▓█████▄ ",
    " ▒██  ██▒▒██▒  ██▒ ██  ▓██▒   ▒██▀ ██▌▓██▒▓█   ▀ ▒██▀ ██▌",
    "  ▒██ ██░▒██░  ██▒▓██  ▒██░   ░██   █▌▒██▒▒███   ░██   █▌",
    "  ░ ▐██▓░▒██   ██░▓▓█  ░██░   ░▓█▄   ▌░██░▒▓█  ▄ ░▓█▄   ▌",
    "  ░ ██▒▓░░ ████▓▒░▒▒█████▓    ░▒████▓ ░██░░▒████▒░▒████▓ ",
    "   ██▒▒▒ ░ ▒░▒░▒░ ░▒▓▒ ▒ ▒     ▒▒▓  ▒ ░▓  ░░ ▒░ ░ ▒▒▓  ▒ ",
    " ▓██ ░▒░   ░ ▒ ▒░ ░░▒░ ░ ░     ░ ▒  ▒  ▒ ░ ░ ░  ░ ░ ▒  ▒ ",
    " ▒ ▒ ░░  ░ ░ ░ ▒   ░░░ ░ ░     ░ ░  ░  ▒ ░   ░    ░ ░  ░ ",
    " ░ ░         ░ ░     ░           ░     ░     ░  ░   ░    ",
    " ░ ░                           ░                  ░      ",
)


def choose_profile(preferred: str = "unicode", stdscr=None) -> GlyphProfile:
    env_choice = os.environ.get("TERMINAL_DESCENT_CHARSET")
    if env_choice in {"unicode", "ascii"}:
        preferred = env_choice
    if preferred == "ascii":
        return ASCII_PROFILE
    if locale.getpreferredencoding(False).upper() != "UTF-8":
        return ASCII_PROFILE
    if not glyph_profile_is_single_cell(UNICODE_PROFILE):
        return ASCII_PROFILE
    if stdscr is not None and not _curses_accepts_unicode(stdscr):
        return ASCII_PROFILE
    return UNICODE_PROFILE


def glyph_profile_is_single_cell(profile: GlyphProfile) -> bool:
    for glyph in profile.glyphs.values():
        if len(glyph) != 1:
            return False
        if unicodedata.category(glyph).startswith("C"):
            return False
    return True


def render(stdscr, engine: GameEngine, profile: GlyphProfile) -> None:
    stdscr.erase()
    level = engine.state.level
    player = engine.state.player
    for y in range(level.height):
        for x in range(level.width):
            glyph = _glyph_at(engine, profile, x, y)
            try:
                stdscr.addstr(y, x, glyph)
            except curses.error:
                pass

    hud_y = level.height
    weapon = player.weapon.display_name() if player.weapon else "none"
    armor = player.armor.display_name() if player.armor else "none"
    status = (
        f" F{level.depth}/5 HP {player.hp}/{player.max_hp} STR {player.strength} "
        f"ATK {player.attack_skill()} DEF {player.defense_skill()} "
        f"Gold {player.gold} Wpn {weapon} Arm {armor} Inv {len(player.inventory)} "
    )
    _draw_boxed_line(stdscr, hud_y, status[: level.width - 2], level.width, profile)
    controls = " arrows move  z get  i inv  v stairs  x wait  q save+quit "
    _safe_addstr(stdscr, hud_y + 3, 0, controls[: level.width])
    log_start = hud_y + 5
    for i, message in enumerate(engine.state.log[-6:]):
        _safe_addstr(stdscr, log_start + i, 0, message[: level.width])
    if engine.state.dead:
        _draw_death_message(stdscr, log_start + 7, level.width)
    if engine.state.won:
        _safe_addstr(stdscr, log_start + 7, 0, "Victory. Press any key to return to the menu.")
    stdscr.refresh()


def render_inventory(stdscr, engine: GameEngine, profile: GlyphProfile) -> None:
    stdscr.erase()
    player = engine.state.player
    width = engine.state.level.width
    _draw_boxed_line(stdscr, 0, " Inventory ", width, profile)
    _safe_addstr(stdscr, 3, 0, "Equipment")
    _safe_addstr(stdscr, 4, 2, f"Weapon: {_equipment_line(player.weapon)}"[:width])
    _safe_addstr(stdscr, 5, 2, f"Armor : {_equipment_line(player.armor)}"[:width])
    _safe_addstr(stdscr, 7, 0, "Backpack")
    if not player.inventory:
        _safe_addstr(stdscr, 9, 2, "Your backpack is empty. Press any key.")
    else:
        _safe_addstr(stdscr, 9, 2, "Press a letter to use/equip an item, or Esc to cancel.")
        for i, item in enumerate(player.inventory[:26]):
            letter = chr(ord("a") + i)
            _safe_addstr(stdscr, 11 + i, 2, f"{letter}) {item.glyph} {item.display_name()} - {item_stats(item)}"[:width])
    stdscr.refresh()


def item_stats(item: Item) -> str:
    parts = [f"level +{item.level}"]
    if item.slot == EquipmentSlot.WEAPON:
        parts.extend(
            [
                f"dmg {item.damage_min}-{item.damage_max}",
                f"atk +{item.attack_bonus}",
                f"STR {item.str_req}",
            ]
        )
    elif item.slot == EquipmentSlot.ARMOR:
        parts.extend(
            [
                f"DR {item.dr}",
                f"def +{item.defense_bonus}",
                f"STR {item.str_req}",
            ]
        )
    elif item.heal_amount:
        parts.append(f"heals {item.heal_amount}")
    elif item.strength_bonus:
        parts.append(f"STR +{item.strength_bonus}")
    elif item.value:
        parts.append(f"value {item.value}")
    else:
        parts.append("consumable")
    return ", ".join(parts)


def _equipment_line(item: Item | None) -> str:
    if item is None:
        return "empty"
    return f"{item.glyph} {item.display_name()} - {item_stats(item)}"


def _glyph_at(engine: GameEngine, profile: GlyphProfile, x: int, y: int) -> str:
    level = engine.state.level
    if (x, y) not in engine.visible:
        return profile["explored"] if level.explored[y][x] else profile["unseen"]
    player = engine.state.player
    if player.x == x and player.y == y:
        return profile["player"]
    enemy = level.enemy_at(x, y)
    if enemy:
        return profile["boss"] if enemy.boss else enemy.glyph
    ground = level.item_at(x, y)
    if ground:
        return ground.item.glyph
    tile = level.tile_at(x, y)
    if tile == Tile.WALL:
        return profile["wall"]
    if tile == Tile.DOOR:
        return profile["door"]
    if tile == Tile.STAIRS:
        if level.depth == 5 and not level.boss_defeated:
            return profile["floor"]
        return profile["stairs"]
    return profile["floor"]


def _draw_boxed_line(stdscr, y: int, text: str, width: int, profile: GlyphProfile) -> None:
    top = profile["hud_tl"] + profile["hud_h"] * (width - 2) + profile["hud_tr"]
    mid = profile["hud_v"] + text.ljust(width - 2) + profile["hud_v"]
    bot = profile["hud_bl"] + profile["hud_h"] * (width - 2) + profile["hud_br"]
    _safe_addstr(stdscr, y, 0, top)
    _safe_addstr(stdscr, y + 1, 0, mid)
    _safe_addstr(stdscr, y + 2, 0, bot)


def _draw_death_message(stdscr, y: int, width: int) -> None:
    for i, line in enumerate(YOU_DIED_ART):
        _safe_addstr(stdscr, y + i, _center_x(line, width), line)
    prompt = "Press any key to return to the menu."
    _safe_addstr(stdscr, y + len(YOU_DIED_ART) + 1, _center_x(prompt, width), prompt)


def _center_x(text: str, width: int) -> int:
    if len(text) >= width:
        return 0
    return (width - len(text)) // 2


def _safe_addstr(stdscr, y: int, x: int, text: str) -> None:
    try:
        stdscr.addstr(y, x, text)
    except curses.error:
        pass


def _curses_accepts_unicode(stdscr) -> bool:
    try:
        stdscr.addstr(0, 0, "█░Ω")
        stdscr.refresh()
        return True
    except curses.error:
        return False
    except UnicodeEncodeError:
        return False
