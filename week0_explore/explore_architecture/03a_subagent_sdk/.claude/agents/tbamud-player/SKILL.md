---
name: tbamud-player
description: Play the tbaMUD (CircleMUD-successor) text MUD server running at localhost:4000, logging in as the character "dummy" (password "helloworld") and issuing game commands over telnet via a bundled Python daemon script. Use this skill whenever the user asks to play, explore, fight, level up, or interact with "the MUD", "tbaMUD", "CircleMUD", a "telnet game" on localhost:4000, or asks Claude to control the "dummy" character — even if they just say something like "go kill some rats" or "check my score" without mentioning the skill by name. Also use it if the user asks to check the MUD connection, read game output, or disconnect from the game. This skill also tracks longer-running goals (like grinding to a target level or hunting down a specific monster) and persists character/world state in data/player.md and data/world.md so progress survives across separate conversations — use it too when the user wants to resume, check progress on, or continue an ongoing MUD goal.
---

# Playing tbaMUD

A MUD (Multi-User Dungeon) is a persistent, stateful text game reached
over a raw TCP/telnet socket — not a request/response API. You log in
once, then send one command at a time and react to what comes back
(a monster attacks, a door is locked, you starve). This skill wraps
that connection in a small background daemon so the session survives
across multiple tool calls, the same way a human would keep a telnet
client open in a terminal tab while they play.

## The tool

`scripts/mud_client.py` manages the whole lifecycle. Run it with `python3`:

```
python3 scripts/mud_client.py start                # connect + log in as dummy/helloworld
python3 scripts/mud_client.py send "look"           # send one command, prints the response
python3 scripts/mud_client.py send "north" --wait 1 # give slow responses more time before reading
python3 scripts/mud_client.py read                  # print any new output that arrived on its own
python3 scripts/mud_client.py status                # is it connected? show recent output
python3 scripts/mud_client.py stop                  # disconnect cleanly
```

Host, port, username, and password default to `localhost`, `4000`,
`dummy`, `helloworld` — exactly what this server needs, so you
normally don't pass any flags. All session state (transcript, pid,
control socket) lives under `session/` next to the script, not `/tmp`,
so you can `cat session/transcript.log` any time to see the full
history if something seems off.

## The play loop

1. **`start` once** at the beginning of a play session. It blocks
   until login actually completes (new-character menu vs. a
   reconnect-in-progress are both handled), then prints everything
   that arrived so far — read it before doing anything else, it
   usually already tells you what room you're in. Before you go any
   further, read `data/player.md` and `data/world.md` (see
   **Memory** below) — if this character has a goal in progress or a
   map from an earlier session, you want that context before you
   start acting.
2. **`send "<command>"` then look at the printed reply.** `send`
   waits ~0.6s by default before printing, which is enough for a
   normal room description or combat round; bump `--wait` for
   commands that trigger something slower (e.g. movement into a new
   zone, casting). Decide your next command from what actually came
   back — don't assume a move succeeded, check the room description
   or an error like "Alas, you cannot go that way."
3. **Use `read` for anything that happens without you typing** —
   other players talking, a mob wandering in, periodic tics. Call it
   if you're waiting to see what happens next rather than sending
   another command immediately.
4. **`stop` when you're done** so the character disconnects cleanly
   instead of sitting linkless. If you `start` again later while a
   previous daemon is still running, the script will tell you it's
   already connected — just keep using `send`/`read`, no need to
   restart. Before you stop, update `data/player.md` and
   `data/world.md` with whatever changed this session — that's what
   lets the next session (or the next loop iteration) pick up where
   this one left off instead of starting blind.

Don't reach for raw `telnet`/`nc`/a hand-rolled socket for this — the
daemon already handles the telnet IAC negotiation the server expects
(without it the connection gets closed almost immediately) and keeps
the session alive between your tool calls, which a one-shot connection
can't do.

## Memory: player.md and world.md

Some goals — grinding from level 1 to level 7, or hunting down one
specific monster somewhere in the world — take far more turns than
fit in a single conversation. Two files in `data/` (a sibling of this
skill's own directory, so `../data/player.md` and `../data/world.md`
relative to it) exist so that kind of goal survives across separate
conversations or automated loop passes, the same way a human player
keeps notes between sessions instead of re-learning the map and
forgetting what they were working toward.

- **`player.md`** is the character's record: level/HP/mana/move at
  last check, conditions (hungry/thirsty/etc.), location, gold, and a
  **Goals** section tracking anything long-running — e.g. `- [ ] Reach
  level 7 (currently level 4)` or `- [ ] Defeat the goblin chief (last
  seen: The Dark Cave, not yet fought)`.
- **`world.md`** is the shared map: rooms visited, their exits, NPCs
  and monsters seen, shop inventories — anything about the world
  itself rather than this one character.

**At the start of a session**, read both files if they exist (they
won't on a first-ever run — that's fine, just start them). If the
user hands you a new goal in their message ("let's push for level 7",
"go find and kill the goblin chief"), add it to player.md's Goals
section right away rather than waiting until the end, in case the
session ends early. Treat both files as notes rather than ground
truth — reconcile them against a fresh `score`/`look` once connected,
since the character or world may have moved on since the last update
(died, leveled, a room's occupants changed).

**While playing**, update world.md as you discover new rooms, exits,
NPCs, or monsters — merge new information into the existing map
rather than replacing it wholesale, the same way you'd add to a
hand-drawn map rather than redraw it from scratch. Update player.md
whenever something goal-relevant happens: a level-up, a death, or
progress toward a tracked goal (spotting the monster you're hunting
even before you've beaten it is worth recording).

**Before `stop`**, always write a final update to both files
summarizing where things stand and what's left. This is the step
that actually makes a multi-session grind possible — skip it and the
next session starts back at square one.

Keep both files as plain, readable Markdown — a future session (or
the user) should be able to read them like notes, not parse them like
data.

## Interpreting output

Every line ends with a status prompt like `23H 100M 84V (motd) >` —
that's current HP / mana / movement points. Watch it drop during
combat or if "You are hungry"/"You are thirsty" showed up in `score`
and you haven't dealt with it. Output also carries ANSI color codes
in the raw transcript; the CLI strips them before printing, so what
you see is already plain text.

For what commands exist and how tbaMUD-specific mechanics work
(combat flow, hunger, practicing skills, exits), see
`references/commands.md`. When in doubt, `help` (and `help <topic>`)
is always available in-game and is more authoritative than the cheat
sheet for anything server-specific.

## Reporting back to the user

Summarize what happened in plain language (where you are, what you
fought, what you found) rather than pasting the raw transcript with
its repeated prompts — but if the user asks to see exactly what the
game printed, `session/transcript.log` has the untouched record.
