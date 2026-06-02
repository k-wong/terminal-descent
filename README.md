# Terminal Descent

A dungeon crawler roguelike game that can be played within your terminal. Play while you wait for your agents :)

## Core gameplay

A compact turn-based roguelike with one player action followed by enemy actions. It includes random dungeons, permadeath, loot, equipment, stats, and bosses.

## Run

```sh
python3 -m terminal_descent
```

Use strict ASCII rendering if your terminal does not handle block glyphs cleanly:

```sh
python3 -m terminal_descent --charset ascii
```

The game uses Unicode block and shade characters by default, mapping CP437-style visual ideas like full block and light shade to portable UTF-8 glyphs. It does not write raw extended-ASCII bytes.

## Controls

- Arrow keys: move or attack
- `z`: pick up
- `i`: inventory / equipment
- `v`: descend stairs
- `x`: wait
- `q`: save and quit

## Saving

Progress autosaves after every completed player action and after floor transitions.

Default save path:

```text
~/.local/share/terminal-descent/save.json
```

Override it with:

```sh
TERMINAL_DESCENT_SAVE=/path/to/save.json python3 -m terminal_descent
```

Death is permadeath: the active save is deleted after the death screen.

## Tests

```sh
python3 -m unittest discover -v
```

## Upcoming improvements
Coming soon: shops, status effects, more weapons/items, hunger, quests, traps, achievements, crafting.
