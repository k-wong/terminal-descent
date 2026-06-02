from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


MAP_WIDTH = 60
MAP_HEIGHT = 24
MAX_DEPTH = 5
FOV_RADIUS = 8
BACKPACK_SIZE = 19


class Tile(str, Enum):
    WALL = "wall"
    FLOOR = "floor"
    DOOR = "door"
    STAIRS = "stairs"


class ItemKind(str, Enum):
    GOLD = "gold"
    HEALING_POTION = "healing_potion"
    STRENGTH_POTION = "strength_potion"
    UPGRADE_SCROLL = "upgrade_scroll"
    WEAPON = "weapon"
    ARMOR = "armor"


class EquipmentSlot(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"


class EnemyState(str, Enum):
    SLEEPING = "sleeping"
    WANDERING = "wandering"
    HUNTING = "hunting"


@dataclass
class Item:
    id: str
    name: str
    kind: ItemKind
    glyph: str
    quantity: int = 1
    slot: EquipmentSlot | None = None
    value: int = 0
    attack_bonus: int = 0
    defense_bonus: int = 0
    damage_min: int = 1
    damage_max: int = 2
    dr: int = 0
    str_req: int = 0
    level: int = 0
    heal_amount: int = 0
    strength_bonus: int = 0
    upgrade_chance: int = 0

    def display_name(self) -> str:
        suffix = f"+{self.level}" if self.level > 0 else ""
        qty = f" x{self.quantity}" if self.quantity > 1 else ""
        return f"{self.name}{suffix}{qty}"

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["kind"] = self.kind.value
        data["slot"] = self.slot.value if self.slot else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Item":
        raw = data.copy()
        raw["kind"] = ItemKind(raw["kind"])
        raw["slot"] = EquipmentSlot(raw["slot"]) if raw.get("slot") else None
        return cls(**raw)


@dataclass
class Player:
    x: int
    y: int
    hp: int = 20
    max_hp: int = 20
    strength: int = 10
    base_attack: int = 10
    base_defense: int = 5
    gold: int = 0
    weapon: Item | None = None
    armor: Item | None = None
    inventory: list[Item] = field(default_factory=list)

    def attack_skill(self) -> int:
        weapon_bonus = self.weapon.attack_bonus if self.weapon else 0
        encumbrance = max(0, (self.weapon.str_req if self.weapon else 0) - self.strength)
        return max(1, self.base_attack + weapon_bonus - encumbrance * 2)

    def defense_skill(self) -> int:
        armor_bonus = self.armor.defense_bonus if self.armor else 0
        encumbrance = max(0, (self.armor.str_req if self.armor else 0) - self.strength)
        return max(0, self.base_defense + armor_bonus - encumbrance * 2)

    def damage_range(self) -> tuple[int, int]:
        if self.weapon:
            penalty = max(0, self.weapon.str_req - self.strength)
            return max(1, self.weapon.damage_min - penalty), max(1, self.weapon.damage_max - penalty)
        return 1, 3

    def armor_dr(self) -> int:
        if not self.armor:
            return 0
        penalty = max(0, self.armor.str_req - self.strength)
        return max(0, self.armor.dr + self.armor.level - penalty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "strength": self.strength,
            "base_attack": self.base_attack,
            "base_defense": self.base_defense,
            "gold": self.gold,
            "weapon": self.weapon.to_dict() if self.weapon else None,
            "armor": self.armor.to_dict() if self.armor else None,
            "inventory": [item.to_dict() for item in self.inventory],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        return cls(
            x=data["x"],
            y=data["y"],
            hp=data["hp"],
            max_hp=data["max_hp"],
            strength=data["strength"],
            base_attack=data["base_attack"],
            base_defense=data["base_defense"],
            gold=data["gold"],
            weapon=Item.from_dict(data["weapon"]) if data.get("weapon") else None,
            armor=Item.from_dict(data["armor"]) if data.get("armor") else None,
            inventory=[Item.from_dict(item) for item in data.get("inventory", [])],
        )


@dataclass
class Enemy:
    id: str
    kind: str
    name: str
    glyph: str
    x: int
    y: int
    hp: int
    max_hp: int
    attack: int
    defense: int
    damage_min: int
    damage_max: int
    dr: int = 0
    state: EnemyState = EnemyState.SLEEPING
    boss: bool = False
    charging: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Enemy":
        raw = data.copy()
        raw["state"] = EnemyState(raw["state"])
        return cls(**raw)


@dataclass
class GroundItem:
    item: Item
    x: int
    y: int

    def to_dict(self) -> dict[str, Any]:
        return {"item": self.item.to_dict(), "x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundItem":
        return cls(item=Item.from_dict(data["item"]), x=data["x"], y=data["y"])


@dataclass
class LevelState:
    depth: int
    width: int
    height: int
    tiles: list[list[Tile]]
    explored: list[list[bool]]
    enemies: list[Enemy]
    items: list[GroundItem]
    entrance: tuple[int, int]
    exit: tuple[int, int]
    boss_defeated: bool = False

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile_at(self, x: int, y: int) -> Tile:
        return self.tiles[y][x]

    def is_passable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.tile_at(x, y) != Tile.WALL

    def enemy_at(self, x: int, y: int) -> Enemy | None:
        for enemy in self.enemies:
            if enemy.hp > 0 and enemy.x == x and enemy.y == y:
                return enemy
        return None

    def item_at(self, x: int, y: int) -> GroundItem | None:
        for item in self.items:
            if item.x == x and item.y == y:
                return item
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "width": self.width,
            "height": self.height,
            "tiles": [[tile.value for tile in row] for row in self.tiles],
            "explored": self.explored,
            "enemies": [enemy.to_dict() for enemy in self.enemies],
            "items": [item.to_dict() for item in self.items],
            "entrance": list(self.entrance),
            "exit": list(self.exit),
            "boss_defeated": self.boss_defeated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LevelState":
        return cls(
            depth=data["depth"],
            width=data["width"],
            height=data["height"],
            tiles=[[Tile(tile) for tile in row] for row in data["tiles"]],
            explored=data["explored"],
            enemies=[Enemy.from_dict(enemy) for enemy in data["enemies"]],
            items=[GroundItem.from_dict(item) for item in data["items"]],
            entrance=tuple(data["entrance"]),
            exit=tuple(data["exit"]),
            boss_defeated=data.get("boss_defeated", False),
        )


@dataclass
class GameState:
    player: Player
    level: LevelState
    seed: int
    rng_state: Any
    turn: int = 0
    kills: int = 0
    log: list[str] = field(default_factory=list)
    dead: bool = False
    won: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "player": self.player.to_dict(),
            "level": self.level.to_dict(),
            "seed": self.seed,
            "rng_state": self.rng_state,
            "turn": self.turn,
            "kills": self.kills,
            "log": self.log[-8:],
            "dead": self.dead,
            "won": self.won,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        return cls(
            player=Player.from_dict(data["player"]),
            level=LevelState.from_dict(data["level"]),
            seed=data["seed"],
            rng_state=data["rng_state"],
            turn=data["turn"],
            kills=data.get("kills", 0),
            log=data.get("log", []),
            dead=data.get("dead", False),
            won=data.get("won", False),
        )
