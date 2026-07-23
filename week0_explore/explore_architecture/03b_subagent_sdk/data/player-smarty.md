# Character: Smarty (Smarty the Apprentice of Magic)

Last updated: 2026-07-23 (session 1 — orientation/status check-in)

## Status (via `score`, 2026-07-23)
- Level: 1 ("Smarty the Apprentice of Magic") — mage-type class
- Exp: 1 / needs 2499 more for level 2
- HP: 13/13, Mana: 100/100, Move: 84/84 (all full despite hunger/thirst)
- Gold: 0 coins, 0 questpoints
- Armor class: 100/10, Alignment: 0 (neutral)
- **Condition: hungry AND thirsty** (both flagged in `score` output;
  neither has been addressed yet this session)
- Age: 17
- Playtime: 0 days, 1 hour (some prior activity happened under this
  name before this check-in, given the played-time and 1 exp — this
  character isn't brand new, though effectively still level 1 start)
- Location: **The Mages' Laboratory** — "Magical Experiments
  Laboratory" with oaken tables, pentagrams on the floor, a partially
  cleaned blackboard. Exits: w. Guildmaster (mage trainer) present,
  studying a spellbook and preparing to cast a spell.

## Session notes (2026-07-23, session 1)
- Login was messy: the session-smarty daemon directory under this
  project copy (`03b_subagent_sdk`) had a **stale pid file** left over
  (no matching control socket existed), which made `mud_client.py
  start` falsely report "Already connected". Confirmed via
  `session_paths()` that the real control socket for this dir did not
  exist on disk, so the pidfile was garbage (likely inherited from a
  directory copy, coincidentally matching a live-but-unrelated pid on
  the system). Cleared the stale `daemon.pid`/`daemon.pid.ready`/
  `read.offset`/`transcript.log`/`daemon.log` files and reran `start`
  — connected cleanly this time.
- On login, the server said "You take over your own body, already in
  use!" — meaning some other connection (possibly a leftover daemon
  process elsewhere on the system, pid 22716, running against a
  sibling directory `03_subagent_sdk` rather than this one) was still
  logged in as smarty; this new connection took over the body as
  expected, kicking the old link.
- Character already existed (not newly created) — logged straight
  into the game, no new-character menu appeared.
- Checked `score`: level 1, 13/13 HP, 100/100 mana, 84/84 move, 0
  gold, 1 exp (2499 to next level), align 0, **hungry and thirsty**.
- Checked `look`: in **The Mages' Laboratory**, exit west only,
  guildmaster (mage trainer) present.
- Session kept idle/connected per instructions — no combat,
  exploration, or hunger/thirst fix attempted yet.

## Goals
- [ ] Address hunger and thirst (currently both flagged) — no food/
      drink on hand confirmed yet; needs an inventory check and a
      food/fountain source near the Mages' Guild.
- [ ] Get oriented: figure out where The Mages' Laboratory connects to
      the rest of Midgaard (only one exit, west, seen so far).
- [ ] General: start leveling this mage character (currently level 1,
      1 exp) — no combat/grinding goal set yet beyond basic survival.

## Next session should
- Check `inventory` for any food/drink already carried.
- Head west out of The Mages' Laboratory to start mapping the route
  back to known Midgaard landmarks (see shared `data/world.md`) and
  find a fountain (Temple Square is known to have one) and a bakery.
- Consider practicing spells at the guildmaster here if practice
  sessions are available (`practice`).

## Session notes (2026-07-23, session 1 continued — clean quit/reconnect)
- Coordinator asked for a clean logout-and-back-in cycle: sent `quit`
  (not a raw disconnect) — server responded "Goodbye, friend..  Come
  back soon!" and dropped to the main menu (0-5 choices), confirming
  a proper save-and-quit rather than a link-death.
- Ran `stop` to shut down the daemon, then `start` again with
  smarty/helloworld. This time login went through the normal "Enter
  the game" flow with **no** "already in use" message (unlike the
  first login this session) — confirms the previous quit really did
  release the character cleanly.
- Landed back in the same room, **The Mages' Laboratory**, as
  expected (quitting doesn't move you).
- Fresh `score` after reconnect: level 1, 13/13 HP, 100/100 mana,
  84/84 move, 0 gold, 1 exp (2499 to next level), align 0, still
  **hungry and thirsty** (unchanged — quitting/reconnecting doesn't
  fix conditions), playtime now shows "0 days and 0 hours" (reset
  display after the reconnect, cosmetic only).
- Session left connected/idle again after the reconnect, per
  instructions.
