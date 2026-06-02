from __future__ import annotations

from dataclasses import dataclass
import random
import uuid

from .models import (
    EquipmentSlot,
    Enemy,
    EnemyState,
    GroundItem,
    Item,
    ItemKind,
    LevelState,
    MAP_HEIGHT,
    MAP_WIDTH,
    Tile,
)


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: "Room") -> bool:
        return not (
            self.x + self.w + 1 < other.x
            or other.x + other.w + 1 < self.x
            or self.y + self.h + 1 < other.y
            or other.y + other.h + 1 < self.y
        )

    def random_cell(self, rng: random.Random) -> tuple[int, int]:
        return rng.randrange(self.x + 1, self.x + self.w - 1), rng.randrange(self.y + 1, self.y + self.h - 1)


def starter_weapon() -> Item:
    return weapon("club")


def starter_armor() -> Item:
    return armor("cloth armor")


def weapon(name: str) -> Item:
    table = {
        "club": dict(glyph=")", attack_bonus=0, damage_min=1, damage_max=5, str_req=8),
        "dagger": dict(glyph=")", attack_bonus=1, damage_min=2, damage_max=6, str_req=10),
        "mace": dict(glyph=")", attack_bonus=0, damage_min=4, damage_max=10, str_req=12),
    }
    return Item(
        id=str(uuid.uuid4()),
        name=name,
        kind=ItemKind.WEAPON,
        slot=EquipmentSlot.WEAPON,
        **table[name],
    )


def armor(name: str) -> Item:
    table = {
        "cloth armor": dict(glyph="[", defense_bonus=0, dr=1, str_req=8),
        "leather armor": dict(glyph="[", defense_bonus=1, dr=2, str_req=10),
        "mail armor": dict(glyph="[", defense_bonus=1, dr=4, str_req=13),
    }
    return Item(
        id=str(uuid.uuid4()),
        name=name,
        kind=ItemKind.ARMOR,
        slot=EquipmentSlot.ARMOR,
        **table[name],
    )


def healing_potion() -> Item:
    return Item(
        id=str(uuid.uuid4()),
        name="healing potion",
        kind=ItemKind.HEALING_POTION,
        glyph="!",
        heal_amount=12,
    )


def strength_potion() -> Item:
    return Item(
        id=str(uuid.uuid4()),
        name="strength potion",
        kind=ItemKind.STRENGTH_POTION,
        glyph="!",
        strength_bonus=1,
    )


def upgrade_scroll(chance: int) -> Item:
    return Item(
        id=str(uuid.uuid4()),
        name=f"{chance}% upgrade scroll",
        kind=ItemKind.UPGRADE_SCROLL,
        glyph="?",
        upgrade_chance=chance,
    )


def random_upgrade_scroll(rng: random.Random) -> Item:
    roll = rng.random()
    if roll < 0.2:
        return upgrade_scroll(30)
    if roll < 0.6:
        return upgrade_scroll(60)
    return upgrade_scroll(100)


def gold(amount: int) -> Item:
    return Item(
        id=str(uuid.uuid4()),
        name="gold",
        kind=ItemKind.GOLD,
        glyph="$",
        quantity=amount,
        value=amount,
    )


def generate_level(depth: int, rng: random.Random, player_strength: int = 10) -> LevelState:
    if depth == 5:
        return _generate_boss_level(rng)
    return _generate_regular_level(depth, rng, player_strength)


def _generate_regular_level(depth: int, rng: random.Random, player_strength: int) -> LevelState:
    tiles = [[Tile.WALL for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
    rooms: list[Room] = []

    for _ in range(120):
        if len(rooms) >= rng.randrange(7, 11):
            break
        w = rng.randrange(6, 13)
        h = rng.randrange(4, 8)
        x = rng.randrange(1, MAP_WIDTH - w - 1)
        y = rng.randrange(1, MAP_HEIGHT - h - 1)
        room = Room(x, y, w, h)
        if any(room.intersects(other) for other in rooms):
            continue
        _carve_room(tiles, room)
        if rooms:
            _connect(tiles, rooms[-1].center, room.center, rng)
        rooms.append(room)

    if len(rooms) < 3:
        return _generate_regular_level(depth, rng, player_strength)

    entrance = rooms[0].center
    exit_room = max(rooms, key=lambda room: _manhattan(entrance, room.center))
    exit_pos = exit_room.center
    tiles[exit_pos[1]][exit_pos[0]] = Tile.STAIRS

    occupied = {entrance, exit_pos}
    enemies = _place_enemies(depth, rng, rooms, occupied)
    items = _place_items(depth, rng, rooms, occupied, player_strength)
    explored = [[False for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
    return LevelState(depth, MAP_WIDTH, MAP_HEIGHT, tiles, explored, enemies, items, entrance, exit_pos)


def _generate_boss_level(rng: random.Random) -> LevelState:
    tiles = [[Tile.WALL for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
    arena = Room(14, 4, 32, 16)
    _carve_room(tiles, arena)
    for x in range(22, 38):
        if x % 5 != 0:
            tiles[9][x] = Tile.WALL
            tiles[14][x] = Tile.WALL
    entrance = (arena.x + arena.w // 2, arena.y + arena.h - 2)
    exit_pos = (arena.x + arena.w // 2, arena.y + 1)
    tiles[exit_pos[1]][exit_pos[0]] = Tile.STAIRS
    boss = Enemy(
        id=str(uuid.uuid4()),
        kind="slime",
        name="Slime",
        glyph="Ω",
        x=arena.x + arena.w // 2,
        y=arena.y + arena.h // 2,
        hp=55,
        max_hp=55,
        attack=14,
        defense=10,
        damage_min=3,
        damage_max=10,
        dr=2,
        state=EnemyState.HUNTING,
        boss=True,
    )
    items = [
        GroundItem(healing_potion(), arena.x + 4, arena.y + arena.h - 3),
        GroundItem(healing_potion(), arena.x + arena.w - 5, arena.y + arena.h - 3),
    ]
    explored = [[False for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
    return LevelState(5, MAP_WIDTH, MAP_HEIGHT, tiles, explored, [boss], items, entrance, exit_pos)


def _carve_room(tiles: list[list[Tile]], room: Room) -> None:
    for y in range(room.y, room.y + room.h):
        for x in range(room.x, room.x + room.w):
            tiles[y][x] = Tile.FLOOR


def _connect(tiles: list[list[Tile]], start: tuple[int, int], end: tuple[int, int], rng: random.Random) -> None:
    x1, y1 = start
    x2, y2 = end
    if rng.random() < 0.5:
        _carve_h(tiles, x1, x2, y1)
        _carve_v(tiles, y1, y2, x2)
    else:
        _carve_v(tiles, y1, y2, x1)
        _carve_h(tiles, x1, x2, y2)


def _carve_h(tiles: list[list[Tile]], x1: int, x2: int, y: int) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        tiles[y][x] = Tile.FLOOR


def _carve_v(tiles: list[list[Tile]], y1: int, y2: int, x: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        tiles[y][x] = Tile.FLOOR


def _place_enemies(depth: int, rng: random.Random, rooms: list[Room], occupied: set[tuple[int, int]]) -> list[Enemy]:
    count = 2 + depth % 5 + rng.randrange(3)
    enemies: list[Enemy] = []
    for _ in range(count):
        room = rng.choice(rooms[1:])
        pos = _free_cell(room, rng, occupied)
        occupied.add(pos)
        enemies.append(_enemy_for_depth(depth, rng, *pos))
    return enemies


def _enemy_for_depth(depth: int, rng: random.Random, x: int, y: int) -> Enemy:
    choices = {
        1: [("rat", 1.0)],
        2: [("rat", 1.0), ("spider", 1.0)],
        3: [("rat", 1.0), ("spider", 2.0), ("bat", 1.0)],
        4: [("rat", 1.0), ("spider", 2.0), ("bat", 3.0)],
    }
    kind = _weighted_choice(rng, choices[depth])
    table = {
        "rat": dict(name="rat", glyph="r", hp=7, attack=7, defense=2, damage_min=1, damage_max=4, dr=0),
        "spider": dict(name="spider", glyph="s", hp=10, attack=9, defense=4, damage_min=2, damage_max=5, dr=1),
        "bat": dict(name="bat", glyph="b", hp=14, attack=11, defense=7, damage_min=2, damage_max=7, dr=2),
    }
    stats = table[kind]
    return Enemy(id=str(uuid.uuid4()), kind=kind, x=x, y=y, max_hp=stats["hp"], state=EnemyState.SLEEPING, **stats)


def _place_items(
    depth: int,
    rng: random.Random,
    rooms: list[Room],
    occupied: set[tuple[int, int]],
    player_strength: int,
) -> list[GroundItem]:
    count = 3
    while rng.random() < 0.4:
        count += 1
    items: list[GroundItem] = []
    guaranteed = [healing_potion()]
    if depth in {2, 4}:
        guaranteed.append(strength_potion())
    if depth in {2, 3}:
        guaranteed.append(random_upgrade_scroll(rng))
    for item in guaranteed + [_random_loot(rng, player_strength) for _ in range(count)]:
        room = rng.choice(rooms[1:])
        x, y = _free_cell(room, rng, occupied)
        occupied.add((x, y))
        items.append(GroundItem(item, x, y))
    return items


def _random_loot(rng: random.Random, player_strength: int) -> Item:
    roll = rng.random()
    if roll < 0.36:
        return gold(rng.randrange(8, 31))
    if roll < 0.56:
        return healing_potion()
    if roll < 0.66:
        return strength_potion()
    if roll < 0.78:
        return random_upgrade_scroll(rng)
    if roll < 0.9:
        return _biased_weapon(rng, player_strength)
    return _biased_armor(rng, player_strength)


def _biased_weapon(rng: random.Random, player_strength: int) -> Item:
    options = [weapon("club"), weapon("dagger"), weapon("mace")]
    return min(rng.sample(options, 2), key=lambda item: abs(item.str_req - player_strength))


def _biased_armor(rng: random.Random, player_strength: int) -> Item:
    options = [armor("cloth armor"), armor("leather armor"), armor("mail armor")]
    return min(rng.sample(options, 2), key=lambda item: abs(item.str_req - player_strength))


def _free_cell(room: Room, rng: random.Random, occupied: set[tuple[int, int]]) -> tuple[int, int]:
    for _ in range(100):
        pos = room.random_cell(rng)
        if pos not in occupied:
            return pos
    return room.center


def _weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    total = sum(weight for _, weight in choices)
    point = rng.random() * total
    upto = 0.0
    for value, weight in choices:
        upto += weight
        if point <= upto:
            return value
    return choices[-1][0]


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
