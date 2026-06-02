from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import random
import time
from typing import Any

from .generation import generate_level, starter_armor, starter_weapon
from .models import (
    BACKPACK_SIZE,
    Enemy,
    EnemyState,
    EquipmentSlot,
    FOV_RADIUS,
    GameState,
    GroundItem,
    Item,
    ItemKind,
    MAX_DEPTH,
    Player,
    Tile,
)


Direction = tuple[int, int]


class SaveManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_save_path()

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, state: GameState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> GameState:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return GameState.from_dict(data)

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()


def default_save_path() -> Path:
    override = os.environ.get("TERMINAL_DESCENT_SAVE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "terminal-descent" / "save.json"


class GameEngine:
    def __init__(self, state: GameState, save_manager: SaveManager | None = None) -> None:
        self.state = state
        self.rng = random.Random()
        self.rng.setstate(_to_tuple(state.rng_state))
        self.visible: set[tuple[int, int]] = set()
        self.save_manager = save_manager
        self.update_fov()

    @classmethod
    def new(cls, seed: int | None = None, save_manager: SaveManager | None = None) -> "GameEngine":
        seed = seed if seed is not None else int(time.time())
        rng = random.Random(seed)
        level = generate_level(1, rng)
        player = Player(*level.entrance, weapon=starter_weapon(), armor=starter_armor())
        state = GameState(player=player, level=level, seed=seed, rng_state=rng.getstate(), log=[], turn=0)
        engine = cls(state, save_manager)
        engine.log("You enter the ruins.")
        engine.autosave()
        return engine

    @classmethod
    def load(cls, save_manager: SaveManager) -> "GameEngine":
        return cls(save_manager.load(), save_manager)

    def log(self, message: str) -> None:
        self.state.log.append(message)
        self.state.log = self.state.log[-8:]

    def autosave(self) -> None:
        self.state.rng_state = self.rng.getstate()
        if self.save_manager and not self.state.dead and not self.state.won:
            self.save_manager.save(self.state)

    def update_fov(self) -> None:
        level = self.state.level
        player = self.state.player
        self.visible = set()
        for y in range(level.height):
            for x in range(level.width):
                if _distance((player.x, player.y), (x, y)) <= FOV_RADIUS and self.line_of_sight(player.x, player.y, x, y):
                    self.visible.add((x, y))
                    level.explored[y][x] = True

    def move_player(self, dx: int, dy: int) -> bool:
        return self._player_action(lambda: self._move_or_attack(dx, dy))

    def wait(self) -> bool:
        return self._player_action(lambda: self.log("You wait.") or True)

    def pickup(self) -> bool:
        return self._player_action(self._pickup)

    def descend(self) -> bool:
        return self._player_action(self._descend, enemies_after=False)

    def use_inventory(self, index: int) -> bool:
        return self._player_action(lambda: self._use_inventory(index))

    def _player_action(self, action, enemies_after: bool = True) -> bool:
        if self.state.dead or self.state.won:
            return False
        acted = action()
        if not acted:
            return False
        self.state.turn += 1
        if enemies_after and not self.state.won:
            self._enemy_turns()
        self._cleanup()
        self.update_fov()
        self.autosave()
        return True

    def _move_or_attack(self, dx: int, dy: int) -> bool:
        player = self.state.player
        level = self.state.level
        nx, ny = player.x + dx, player.y + dy
        enemy = level.enemy_at(nx, ny)
        if enemy:
            self._attack_player_to_enemy(enemy)
            return True
        if not level.is_passable(nx, ny):
            self.log("You bump into a wall.")
            return False
        player.x, player.y = nx, ny
        return True

    def _pickup(self) -> bool:
        player = self.state.player
        ground = self.state.level.item_at(player.x, player.y)
        if not ground:
            self.log("There is nothing here.")
            return False
        item = ground.item
        if item.kind == ItemKind.GOLD:
            player.gold += item.value
            self.state.level.items.remove(ground)
            self.log(f"You pick up {item.value} gold.")
            return True
        if len(player.inventory) >= BACKPACK_SIZE:
            self.log("Your backpack is full.")
            return False
        player.inventory.append(item)
        self.state.level.items.remove(ground)
        self.log(f"You pick up a {item.display_name()}.")
        return True

    def _descend(self) -> bool:
        player = self.state.player
        level = self.state.level
        if (player.x, player.y) != level.exit:
            self.log("There are no stairs here.")
            return False
        if level.depth == MAX_DEPTH:
            if not level.boss_defeated:
                self.log("The stairway is blocked by the Slime.")
                return False
            self.state.won = True
            self.log("You escape with the relic shard. Victory!")
            return True
        next_depth = level.depth + 1
        self.state.level = generate_level(next_depth, self.rng, player.strength)
        player.x, player.y = self.state.level.entrance
        self.update_fov()
        if next_depth == MAX_DEPTH:
            self.log("The floor trembles. Slime waits below.")
        else:
            self.log(f"You descend to floor {next_depth}.")
        return True

    def _use_inventory(self, index: int) -> bool:
        player = self.state.player
        if index < 0 or index >= len(player.inventory):
            self.log("Invalid inventory slot.")
            return False
        item = player.inventory[index]
        if item.kind == ItemKind.HEALING_POTION:
            player.inventory.pop(index)
            old = player.hp
            player.hp = min(player.max_hp, player.hp + item.heal_amount)
            self.log(f"You drink a healing potion. HP {old}->{player.hp}.")
            return True
        if item.kind == ItemKind.STRENGTH_POTION:
            player.inventory.pop(index)
            player.strength += item.strength_bonus
            self.log(f"You feel stronger. STR is now {player.strength}.")
            return True
        if item.kind == ItemKind.UPGRADE_SCROLL:
            player.inventory.pop(index)
            self._use_upgrade_scroll(item)
            return True
        if item.slot == EquipmentSlot.WEAPON:
            old = player.weapon
            player.weapon = item
            player.inventory.pop(index)
            if old:
                player.inventory.append(old)
            self.log(f"You equip the {item.display_name()}.")
            return True
        if item.slot == EquipmentSlot.ARMOR:
            old = player.armor
            player.armor = item
            player.inventory.pop(index)
            if old:
                player.inventory.append(old)
            self.log(f"You wear the {item.display_name()}.")
            return True
        self.log("You cannot use that.")
        return False

    def _use_upgrade_scroll(self, scroll: Item) -> None:
        player = self.state.player
        target = player.weapon or player.armor
        if not target:
            self.log("The scroll fizzles.")
            return
        chance = scroll.upgrade_chance or 100
        if self.rng.random() >= chance / 100:
            self.log(f"The {scroll.name} crumbles with no effect.")
            return
        if target.slot == EquipmentSlot.WEAPON:
            self._upgrade_weapon(target, chance)
        else:
            self._upgrade_armor(target, chance)
        self.log(f"Your {target.name} glows briefly.")

    def _upgrade_weapon(self, target: Item, chance: int) -> None:
        if chance == 30:
            target.level += self.rng.randint(1, 2)
            target.damage_min += 1
            target.damage_max += 3
            target.attack_bonus += self.rng.randint(1, 3)
        elif chance == 60:
            target.level += 1
            target.damage_min += 1
            target.damage_max += 2
            target.attack_bonus += self.rng.randint(1, 2)
        else:
            target.level += 1
            target.damage_min += 1
            target.damage_max += 1
            target.attack_bonus += 1

    def _upgrade_armor(self, target: Item, chance: int) -> None:
        if chance == 30:
            target.level += self.rng.randint(1, 2)
            target.dr += self.rng.randint(1, 3)
            target.defense_bonus += self.rng.randint(1, 3)
        elif chance == 60:
            target.level += 1
            target.dr += self.rng.randint(1, 2)
            target.defense_bonus += self.rng.randint(1, 2)
        else:
            target.level += 1
            target.dr += 1
            target.defense_bonus += 1

    def _enemy_turns(self) -> None:
        for enemy in list(self.state.level.enemies):
            if enemy.hp <= 0 or self.state.dead or self.state.won:
                continue
            self._enemy_act(enemy)

    def _enemy_act(self, enemy: Enemy) -> None:
        player = self.state.player
        sees_player = _distance((enemy.x, enemy.y), (player.x, player.y)) <= FOV_RADIUS and self.line_of_sight(
            enemy.x, enemy.y, player.x, player.y
        )
        if enemy.state == EnemyState.SLEEPING:
            if sees_player:
                enemy.state = EnemyState.HUNTING
                self.log(f"The {enemy.name} wakes.")
            return
        if sees_player:
            enemy.state = EnemyState.HUNTING
        if enemy.state == EnemyState.HUNTING:
            if enemy.boss:
                self._boss_act(enemy, sees_player)
            elif _adjacent(enemy.x, enemy.y, player.x, player.y):
                self._attack_enemy_to_player(enemy)
            else:
                self._move_enemy_toward(enemy, player.x, player.y)
            return
        self._wander(enemy)

    def _boss_act(self, enemy: Enemy, sees_player: bool) -> None:
        player = self.state.player
        if self._boss_absorb_item(enemy):
            return
        if enemy.charging:
            enemy.charging = False
            if _adjacent(enemy.x, enemy.y, player.x, player.y) and sees_player:
                self._attack_enemy_to_player(enemy, damage_multiplier=2.5, verb="crushes")
                return
            self._boss_hunt(enemy, player.x, player.y)
            return
        if _adjacent(enemy.x, enemy.y, player.x, player.y):
            if self.rng.random() < 0.5:
                self._attack_enemy_to_player(enemy)
            else:
                enemy.charging = True
                self.log("Slime is gathering force.")
        else:
            self._boss_hunt(enemy, player.x, player.y)

    def _boss_absorb_item(self, enemy: Enemy) -> bool:
        ground = self.state.level.item_at(enemy.x, enemy.y)
        if not ground:
            return False
        self.state.level.items.remove(ground)
        recovered = self.rng.randint(1, 5)
        enemy.hp = min(enemy.max_hp, enemy.hp + recovered)
        thing = "some gold" if ground.item.kind == ItemKind.GOLD else "an item"
        self.log(f"Slime absorbs {thing} and recovers {recovered} HP.")
        return True

    def _boss_hunt(self, enemy: Enemy, x: int, y: int) -> None:
        if self.rng.random() < 0.1:
            self.log("Slime is resting.")
            return
        self._move_enemy_toward(enemy, x, y)

    def _wander(self, enemy: Enemy) -> None:
        dirs = [(0, 1), (1, 0), (0, -1), (-1, 0), (0, 0)]
        dx, dy = self.rng.choice(dirs)
        nx, ny = enemy.x + dx, enemy.y + dy
        if self._enemy_can_move_to(nx, ny):
            enemy.x, enemy.y = nx, ny

    def _move_enemy_toward(self, enemy: Enemy, x: int, y: int) -> None:
        step = self._next_step(enemy.x, enemy.y, x, y)
        if step:
            enemy.x, enemy.y = step

    def _next_step(self, sx: int, sy: int, tx: int, ty: int) -> tuple[int, int] | None:
        level = self.state.level
        blocked = {(enemy.x, enemy.y) for enemy in level.enemies if enemy.hp > 0 and (enemy.x, enemy.y) != (sx, sy)}
        blocked.add((self.state.player.x, self.state.player.y))
        queue = deque([(sx, sy)])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
        while queue:
            x, y = queue.popleft()
            if (x, y) == (tx, ty):
                break
            for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in came_from:
                    continue
                if (nx, ny) != (tx, ty) and ((nx, ny) in blocked or not level.is_passable(nx, ny)):
                    continue
                if (nx, ny) == (tx, ty) or level.is_passable(nx, ny):
                    came_from[(nx, ny)] = (x, y)
                    queue.append((nx, ny))
        if (tx, ty) not in came_from:
            return None
        cur = (tx, ty)
        while came_from[cur] != (sx, sy):
            cur = came_from[cur]
            if cur is None:
                return None
        return cur

    def _enemy_can_move_to(self, x: int, y: int) -> bool:
        level = self.state.level
        if not level.is_passable(x, y):
            return False
        if (x, y) == (self.state.player.x, self.state.player.y):
            return False
        return level.enemy_at(x, y) is None

    def _attack_player_to_enemy(self, enemy: Enemy) -> None:
        player = self.state.player
        if self._hits(player.attack_skill(), enemy.defense):
            lo, hi = player.damage_range()
            damage = max(0, self.rng.randint(lo, hi) - self.rng.randint(0, enemy.dr))
            enemy.hp -= damage
            self.log(f"You hit the {enemy.name} for {damage}.")
            if enemy.hp <= 0:
                self.state.kills += 1
                self.log(f"You defeat the {enemy.name}.")
                if enemy.boss:
                    self.state.level.boss_defeated = True
                    self.log("The seal breaks. The stairs are open.")
        else:
            self.log(f"The {enemy.name} dodges your attack.")

    def _attack_enemy_to_player(self, enemy: Enemy, damage_multiplier: float = 1.0, verb: str = "hits") -> None:
        player = self.state.player
        if self._hits(enemy.attack, player.defense_skill()):
            rolled = self.rng.randint(enemy.damage_min, enemy.damage_max)
            damage = max(0, round(rolled * damage_multiplier) - self.rng.randint(0, player.armor_dr()))
            player.hp -= damage
            self.log(f"The {enemy.name} {verb} you for {damage}.")
            if player.hp <= 0:
                player.hp = 0
                self.state.dead = True
                self.log(f"You were killed by the {enemy.name}.")
        else:
            self.log(f"The {enemy.name} misses.")

    def _hits(self, attack: int, defense: int) -> bool:
        return self.rng.random() * max(1, attack) >= self.rng.random() * max(1, defense)

    def _cleanup(self) -> None:
        self.state.level.enemies = [enemy for enemy in self.state.level.enemies if enemy.hp > 0]

    def line_of_sight(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        level = self.state.level
        for x, y in _bresenham(x0, y0, x1, y1):
            if (x, y) in {(x0, y0), (x1, y1)}:
                continue
            if level.tile_at(x, y) == Tile.WALL:
                return False
        return True


def _to_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_to_tuple(item) for item in value)
    return value


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _adjacent(x0: int, y0: int, x1: int, y1: int) -> bool:
    return abs(x0 - x1) + abs(y0 - y1) == 1


def _bresenham(x0: int, y0: int, x1: int, y1: int):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
