from __future__ import annotations

from collections import deque
import random
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from terminal_descent.game import GameEngine, SaveManager, default_save_path
from terminal_descent.generation import generate_level, healing_potion, upgrade_scroll, weapon
from terminal_descent.main import MOVES
from terminal_descent.models import Enemy, EnemyState, GroundItem, ItemKind, Tile
from terminal_descent.render import ASCII_PROFILE, UNICODE_PROFILE, YOU_DIED_ART, _center_x, glyph_profile_is_single_cell, item_stats


class GenerationTests(unittest.TestCase):
    def test_regular_level_has_reachable_exit(self) -> None:
        rng = random.Random(7)
        level = generate_level(1, rng)
        self.assertEqual(level.depth, 1)
        self.assertTrue(level.is_passable(*level.entrance))
        self.assertEqual(level.tile_at(*level.exit), Tile.STAIRS)
        self.assertTrue(_reachable(level, level.entrance, level.exit))
        self.assertGreaterEqual(len(level.enemies), 2)
        self.assertGreaterEqual(len(level.items), 4)

    def test_boss_level_has_slime_and_stairs(self) -> None:
        level = generate_level(5, random.Random(9))
        self.assertEqual(level.depth, 5)
        self.assertEqual(len(level.enemies), 1)
        self.assertTrue(level.enemies[0].boss)
        self.assertEqual(level.enemies[0].kind, "slime")
        self.assertEqual(level.enemies[0].name, "Slime")
        self.assertEqual(level.enemies[0].glyph, "Ω")
        self.assertEqual(level.tile_at(*level.exit), Tile.STAIRS)

    def test_starter_weapon_is_club(self) -> None:
        engine = GameEngine.new(seed=20)
        starter = engine.state.player.weapon
        self.assertIsNotNone(starter)
        self.assertEqual(starter.name, "club")
        self.assertEqual(starter.damage_min, 1)
        self.assertEqual(starter.damage_max, 5)


class TurnTests(unittest.TestCase):
    def test_one_player_action_wakes_each_visible_sleeping_enemy_once(self) -> None:
        engine = GameEngine.new(seed=1)
        level = engine.state.level
        player = engine.state.player
        level.enemies = [
            Enemy("e1", "rat", "rat", "r", player.x + 2, player.y, 5, 5, 5, 1, 1, 2),
            Enemy("e2", "rat", "rat", "r", player.x, player.y + 2, 5, 5, 5, 1, 1, 2),
        ]
        for enemy in level.enemies:
            enemy.state = EnemyState.SLEEPING
        engine.update_fov()
        self.assertTrue(engine.wait())
        self.assertEqual(engine.state.turn, 1)
        self.assertTrue(all(enemy.state == EnemyState.HUNTING for enemy in level.enemies))
        self.assertEqual(len(level.enemies), 2)


class CombatInventoryTests(unittest.TestCase):
    def test_armor_can_reduce_incoming_damage_to_zero(self) -> None:
        engine = GameEngine.new(seed=2)
        player = engine.state.player
        player.armor.dr = 99
        enemy = Enemy("e", "rat", "rat", "r", player.x + 1, player.y, 5, 5, 100, 0, 1, 3)
        before = player.hp
        engine._attack_enemy_to_player(enemy)
        self.assertEqual(player.hp, before)

    def test_pickup_and_equip_weapon(self) -> None:
        engine = GameEngine.new(seed=3)
        player = engine.state.player
        level = engine.state.level
        mace = weapon("mace")
        level.items = [GroundItem(mace, player.x, player.y)]
        self.assertTrue(engine.pickup())
        self.assertEqual(len(player.inventory), 1)
        self.assertTrue(engine.use_inventory(0))
        self.assertEqual(player.weapon.name, "mace")

    def test_healing_potion_restores_hp(self) -> None:
        engine = GameEngine.new(seed=4)
        player = engine.state.player
        player.hp = 5
        player.inventory.append(healing_potion())
        self.assertTrue(engine.use_inventory(0))
        self.assertEqual(player.hp, 17)
        self.assertFalse(any(item.kind == ItemKind.HEALING_POTION for item in player.inventory))

    def test_100_percent_upgrade_scroll_applies_fixed_weapon_upgrade(self) -> None:
        engine = GameEngine.new(seed=6)
        player = engine.state.player
        player.inventory.append(upgrade_scroll(100))
        self.assertTrue(engine.use_inventory(0))
        self.assertEqual(player.weapon.level, 1)
        self.assertEqual(player.weapon.damage_min, 2)
        self.assertEqual(player.weapon.damage_max, 6)
        self.assertEqual(player.weapon.attack_bonus, 1)

    def test_failed_upgrade_scroll_is_consumed(self) -> None:
        engine = GameEngine.new(seed=7)
        player = engine.state.player
        player.inventory.append(upgrade_scroll(30))
        with patch.object(engine.rng, "random", return_value=0.99):
            self.assertTrue(engine.use_inventory(0))
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.weapon.level, 0)
        self.assertIn("crumbles with no effect", engine.state.log[-1])

    def test_slime_absorbs_item_on_next_action(self) -> None:
        engine = GameEngine.new(seed=5)
        level = engine.state.level
        slime = Enemy("slime", "slime", "Slime", "Ω", 5, 5, 10, 20, 1, 1, 1, 1, boss=True)
        level.enemies = [slime]
        level.items = [GroundItem(healing_potion(), slime.x, slime.y)]
        engine._boss_act(slime, sees_player=True)
        self.assertEqual(level.items, [])
        self.assertGreaterEqual(slime.hp, 11)
        self.assertLessEqual(slime.hp, 15)
        self.assertIn("Slime absorbs an item", engine.state.log[-1])

    def test_charged_slime_attack_uses_damage_multiplier(self) -> None:
        engine = GameEngine.new(seed=1)
        player = engine.state.player
        player.armor = None
        player.base_defense = 0
        slime = Enemy("slime", "slime", "Slime", "Ω", player.x + 1, player.y, 10, 10, 100, 0, 4, 4, boss=True)
        before = player.hp
        engine._attack_enemy_to_player(slime, damage_multiplier=2.5, verb="crushes")
        self.assertEqual(player.hp, before - 10)
        self.assertIn("The Slime crushes you for 10.", engine.state.log[-1])

    def test_player_kills_increment_run_counter(self) -> None:
        engine = GameEngine.new(seed=8)
        enemy = Enemy("e", "rat", "rat", "r", engine.state.player.x + 1, engine.state.player.y, 1, 1, 1, 0, 1, 1)
        engine.state.level.enemies = [enemy]
        self.assertEqual(engine.state.kills, 0)
        with patch.object(engine, "_hits", return_value=True):
            engine._attack_player_to_enemy(enemy)
        self.assertEqual(engine.state.kills, 1)


class SaveLoadTests(unittest.TestCase):
    def test_default_save_path_uses_terminal_descent_name(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(default_save_path().name, "save.json")
            self.assertEqual(default_save_path().parent.name, "terminal-descent")

    def test_terminal_descent_save_env_overrides_default(self) -> None:
        with patch.dict("os.environ", {"TERMINAL_DESCENT_SAVE": "/tmp/td-save.json"}, clear=True):
            self.assertEqual(default_save_path(), Path("/tmp/td-save.json"))

    def test_save_load_round_trip_preserves_mid_run_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = SaveManager(Path(tmp) / "save.json")
            engine = GameEngine.new(seed=12, save_manager=manager)
            engine.wait()
            engine.state.player.gold = 42
            engine.state.kills = 3
            engine.autosave()
            loaded = GameEngine.load(manager)
            self.assertEqual(loaded.state.seed, 12)
            self.assertEqual(loaded.state.turn, engine.state.turn)
            self.assertEqual(loaded.state.player.gold, 42)
            self.assertEqual(loaded.state.kills, 3)
            self.assertEqual(loaded.state.level.depth, engine.state.level.depth)
            self.assertEqual(loaded.state.level.tiles, engine.state.level.tiles)
            self.assertEqual(len(loaded.state.level.enemies), len(engine.state.level.enemies))


class RenderingTests(unittest.TestCase):
    def test_glyph_profiles_are_single_codepoint_glyphs(self) -> None:
        self.assertTrue(glyph_profile_is_single_cell(UNICODE_PROFILE))
        self.assertTrue(glyph_profile_is_single_cell(ASCII_PROFILE))

    def test_player_and_stair_glyphs_match_profiles(self) -> None:
        self.assertEqual(UNICODE_PROFILE["player"], "ö")
        self.assertEqual(ASCII_PROFILE["player"], "o")
        self.assertEqual(UNICODE_PROFILE["stairs"], "v")
        self.assertEqual(ASCII_PROFILE["stairs"], "v")
        self.assertEqual(UNICODE_PROFILE["boss"], "Ω")
        self.assertEqual(ASCII_PROFILE["boss"], "Ø")

    def test_death_art_is_centered_within_map_width(self) -> None:
        self.assertEqual(max(len(line) for line in YOU_DIED_ART), 57)
        self.assertEqual(_center_x(YOU_DIED_ART[0], 60), 1)

    def test_equipment_stats_include_upgrade_level_and_stats(self) -> None:
        mace = weapon("mace")
        mace.level = 2
        mace.damage_min += 2
        mace.damage_max += 2
        text = item_stats(mace)
        self.assertIn("level +2", text)
        self.assertIn("dmg 6-12", text)
        self.assertIn("STR 12", text)


class ControlsTests(unittest.TestCase):
    def test_hjkl_are_not_movement_keys(self) -> None:
        for key in "hjkl":
            self.assertNotIn(ord(key), MOVES)


def _reachable(level, start: tuple[int, int], goal: tuple[int, int]) -> bool:
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return True
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen or not level.is_passable(nx, ny):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return False


if __name__ == "__main__":
    unittest.main()
