# tbaMUD / CircleMUD command reference

tbaMUD is a DikuMUD-family game (CircleMUD's successor). If a command
below doesn't do what you expect, send `help <topic>` or bare `help` to
the game itself — the running server is the ground truth, this file is
just a cheat sheet to avoid guessing blind.

## Movement
`north`/`n`, `south`/`s`, `east`/`e`, `west`/`w`, `up`/`u`, `down`/`d`,
`northeast`/`ne`, `northwest`/`nw`, `southeast`/`se`, `southwest`/`sw`.
The room description after each move lists valid `Exits:` — only move
in a listed direction, otherwise you'll get "Alas, you cannot go that way."

`look` (`l`) — redescribe the current room. `look <direction>` — peek
without moving. `look <item/mob>` — examine something specific.
`exits` — list exits without the full room description.

## Character info
`score` (`sc`) — HP/mana/move, level, exp, alignment, hunger/thirst.
`inventory` (`i`) — what you're carrying. `equipment` (`eq`) — what's worn.
`who` — players online. `time`, `weather`.

## Items
`get <item>` / `get <item> <container>`, `drop <item>`, `put <item> <container>`,
`wear <item>`, `wield <weapon>`, `remove <item>`, `give <item> <person>`.
`eat <food>`, `drink <liquid>`, `quaff <potion>` — resolve hunger/thirst
warnings shown in `score`; ignoring them for too long causes HP loss.

## Combat
`kill <target>` (`k`) — initiate combat. Once in combat you don't need
to repeat `kill` each round — attacks continue automatically each tick.
`flee` — escape combat (may fail and cost a turn). `consider <target>`
— gauge a mob's difficulty before engaging. Rest/recover with `rest`
then `stand` when done (you can't fight while resting).

## Communication
`say <message>` — talk to the current room. `tell <person> <message>`
— private message. `gossip <message>` / other chat channels vary by
server config — `help channels` lists what's available.

## Classes / skills (if applicable)
`practice` (`prac`) — see and train skills/spells at a guild.
`cast '<spell>' <target>` — cast a known spell (quotes matter).
`skills` / `spells` — list what you know.

## Common gotchas
- Commands are case-insensitive; most have short aliases (`n`, `l`, `i`, `sc`, `k`).
- The status line prompt looks like `23H 100M 84V (motd) >` — HP,
  mana, movement points. Watch it drop during combat or starvation.
- "You can't do that while sleeping/resting/fighting!" means change
  stance first (`stand`/`wake`) before trying the blocked action.
- Death or fleeing to safety are both normal outcomes — don't treat a
  death as a bug in the connection; the game will prompt to continue.
