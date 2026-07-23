# Character: Dummy (Dummy the Fighter)

Last updated: 2026-07-23 (session 5, check-in only)

## Status (last checked via `score`, 2026-07-23, session 5)
- Level: 4 ("Dummy the Fighter") — unchanged
- Exp: 9433 / needs 6567 more for level 5 (unchanged since session 3 —
  still no grinding done between check-ins)
- HP: 62/62, Mana: 100/100, Move: 90/90 (full despite conditions)
- Gold: 108 coins, 0 questpoints (unchanged)
- Alignment: +70 (good, unchanged)
- Condition: **thirsty only** (hunger already cured in session 4 and
  stayed cured while offline). Still no fountain at this location —
  needs Temple Square trip to cure thirst.
- Age: 17
- Class: warrior-type. Skills: kick (fair), rescue (poor), 0 practice
  sessions remaining — unchanged since session 3.
- Location: **The Tournament And Practice Yard** (exits: n, d;
  guildmaster present) — same as sessions 3-4, still not connected to
  the rest of the map.
- Inventory (checked this session): smelly hide of the Minotaur,
  horns of the Minotaur, shiny newbie dagger (glowing aura, still
  unidentified), brightly glowing jar (glowing aura, still
  unidentified). No food item on hand this time.

## Goals
- [ ] Reach level 7 (currently level 4, 9433 exp, need 6567 more for
      level 5)
- [x] Find and defeat a hostile monster (session 1) — beastly fido,
      killed x2.
- [x] Defeat the massive Minotaur in the Newbie Zone dungeon north of
      Midgaard (session 2) — DONE 2026-07-21.
- [ ] Identify/use the two glowing loot items (shiny newbie dagger,
      brightly glowing jar) — still unidentified as of last check.
- [x] Spend practice sessions at a guild trainer — DONE at some point
      between session 2 and this check-in (0 sessions remaining now,
      kick improved to fair, rescue learned to poor). Not logged in
      detail (happened outside a fully-tracked session).
- [ ] Cure hunger and thirst — hunger cured (session 4, ate stored
      pastry); still thirsty, need a fountain next time

## Session log (2026-07-21, session 1)
- Started fresh at The Temple Of Midgaard (southern temple hall).
- Drank from the fountain at Temple Square to cure thirst.
- Explored south through Market Square -> Common Square -> Poor Alley
  -> Grubby Inn, killing 2x "beastly fido" along the way (34 + 33 exp).
- Explored west along Wall Road, over the bridge, around the Concourse,
  up Emerald Avenue, to the Road Crossing (has a huge chain leading up
  — did not go up, looked dangerous/high-level), then to the park.
- In the park (path + pond), fought and killed a duck, a second duck,
  and a swan (33 exp each) — became hungry and alignment dropped from
  killing "peaceful-looking" animals, but no ill effects yet.
- Exp went from 305 -> 622 over the session. Still level 1 (leveling to
  7 will take a lot more grinding — thresholds are in the hundreds to
  low thousands of exp per level at this stage).
- Ended the session standing, full HP/mana, at "A Path In The Park",
  cleanly stopped the connection.

## Session log (2026-07-21, session 2)
- Reconnected to an already-running daemon session; character was
  found at level 3 (5305 exp), hungry, 25/49 HP, at "The North Stairs"
  in the Newbie Zone — a jump from session 1's level 1/622 exp, so
  progress happened outside this logged session too.
- Explored the Newbie Zone's upper tower area (North/South Stairs, A
  Narrow Passage) down to the Alchemist's Room, which guards a
  stairway down behind a warning sign ("below level 4 alone: bugger
  off"). Scouted the dungeon below cautiously rather than diving in
  underprepared.
- Found a wall carving + writing in the dungeon reading "beware the
  Minotaur..." confirming the target was down there somewhere.
- Retreated to Midgaard to resupply: drank from the Temple Square
  fountain (cures thirst, free), bought and ate a danish pastry from
  the Bakery (Main St west of Market Square, 7g, cures hunger). Walking
  through "By The Temple Altar" in the Temple of Midgaard also fully
  restored HP — worth remembering as a free heal stop.
- Returned to the dungeon via a shortcut (door south from The Dirty
  Hallway -> A Small Room -> door east -> More Of The Hallway -> south
  -> Another Corner -> door east -> straight back to Alchemist's Room),
  much faster than the original path.
- Went back down, and this time took `north` from The Entrance (rather
  than the long south/east loop used while scouting) — this leads
  directly to **A Crossing Of Corridors**, where **the massive
  Minotaur** was waiting and immediately attacked.
- Fought and killed the Minotaur: took it down from full HP without
  ever dropping below 40/49 HP — a clean, winnable "Do you feel lucky,
  punk?"-tier fight, not overtuned for a level 3-4 character. Got 2467
  exp and leveled up to 4 (max HP jumped 49 -> 62).
- Looted the corpse: 70 gold, "the horns of the Minotaur", "the smelly
  hide of the Minotaur" (both look like trophy/quest items, not yet
  identified for further use).
- Also killed a "zombiefied newbie" mob along the way (603 exp, easy
  fight) while route-finding through "A Passage".

## Session log (2026-07-23, session 3 — status check-in only)
- Task was explicitly a check-in: log in, look around, check score,
  report, then disconnect. No grinding/fighting/goal pursuit done.
- Found the daemon's pid file stale (leftover from a crashed previous
  connection whose control socket no longer existed); cleared it and
  ran `start` again, which reconnected cleanly ("You take over your
  own body, already in use!").
- `look`: character is at **The Tournament And Practice Yard**
  (exits n/d, guildmaster present) — a new room not in world.md yet.
- `score`: level 4, 62/62 HP, 100/100 mana, 90/90 move, 108 gold,
  9433 exp (6567 to next level), align +70, **hungry and thirsty**.
- `practice`: 0 sessions remaining, kick (fair), rescue (poor) — both
  improved since session 2's "4 unused practice sessions" note, and
  rescue is now known (was "not learned"). This happened at some
  point outside a logged session.
- Sent `quit` and `stop` to disconnect cleanly; character logged out
  to the main menu before the daemon was stopped.

## Session log (2026-07-23, session 4 — status check-in only)
- Task was again explicitly a check-in: log in, check score, report,
  disconnect. No grinding/fighting/exploration done.
- `start` reconnected cleanly at **The Tournament And Practice Yard**
  (same location as session 3 — character had been left there,
  logged out, since last check-in; nothing changed in the world
  while offline).
- `score`: level 4, 9433 exp (6567 to next level), 108 gold, align
  +70 — all identical to session 3's numbers, confirming no activity
  happened between the two check-ins.
- `inventory`: still carrying Minotaur trophies (hide, horns) and the
  two unidentified glowing items (dagger, jar); also had a danish
  pastry in stock.
- Ate the danish pastry (`eat pastry`) to cure hunger since one was
  already on hand — quick, safe action within a check-in. Thirst
  remains uncured (no fountain at this location).
- Disconnected cleanly: `quit` (returned to main menu) then `stop`
  (daemon disconnected). `status` afterward confirmed
  Connected: False.

## Session log (2026-07-23, session 5 — status check-in only)
- Task was again explicitly a check-in: log in, check score/look,
  report, keep session open (do NOT disconnect this time).
- `start` reconnected cleanly, already logged in at **The Tournament
  And Practice Yard** — same spot as sessions 3-4, confirming the
  character sat idle/logged-out between sessions with no world change.
- `score`: level 4, 9433 exp (6567 to next level), 108 gold, align
  +70, 62/62 HP, 100/100 mana, 90/90 move — all identical to sessions
  3-4, confirming zero activity happened between check-ins.
- Condition: only **thirsty** flagged this time (hunger stayed cured
  from session 4's pastry).
- `inventory`: still carrying Minotaur trophies (hide, horns) and the
  two unidentified glowing items (dagger, jar); no food item this
  time.
- Per instructions, left the session **connected/idle** rather than
  disconnecting — did not send `quit` or `stop`.

## Next session should
- Cure hunger and thirst first (fountain + bakery, or ask around The
  Tournament And Practice Yard / bar to the north for food/drink).
- Figure out where "The Tournament And Practice Yard" connects to the
  rest of the known map (it's new territory — probably a Fighters'
  Guild area reachable from somewhere in Midgaard already explored).
- Identify or try using/wearing the two glowing loot items (shiny
  newbie dagger, brightly glowing jar), if still in inventory.
- Keep grinding exp toward level 5 (6567 needed) then onward to 7 —
  consider the Minotaur's dungeon (mobs may have respawned) or
  session 1's southern Midgaard/park targets.
- Consider exploring the sewer entrance (`down` from The Dump, south
  of Common Square) — still not yet visited.
