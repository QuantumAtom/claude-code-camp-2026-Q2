# Hunger/thirst check on character "dummy"

**Bottom line: no action was needed.** The character was not hungry or thirsty, so nothing was eaten or bought. I logged in, checked, and logged back out.

## What I did

1. Wrote a small Python script (`work/mud_client.py`) that opens a raw TCP socket to `127.0.0.1:4000`, strips telnet negotiation bytes, and sends a scripted sequence of commands with short delays, logging everything to a transcript file. I used this instead of the interactive `telnet` binary so the session could be scripted and closed cleanly.
2. Connected and logged in as `dummy` / `helloworld`. The server reported "Reconnecting." (an existing/stale session on the server side), then dropped me into the game at the same spot the character was last left: **The Bakery**.
3. Ran `score`. tbaMUD's score screen only prints an explicit "You are hungry."/"You are thirsty." line when those conditions are low — neither line appeared, so hunger and thirst were both fine. The rest of the score (23/23 HP, level 1, "Dummy the Swordpupil", standing) confirmed the character was otherwise healthy.
4. Checked `inventory` (empty — carrying nothing) and, as an extra sanity check, tried `eat` and `drink` with no argument; the game just asked "Eat what?" / "Drink from what?", consistent with not being in a hunger/thirst emergency state.
5. Ran `look` to confirm surroundings (standing inside a bakery, a baker NPC present) in case food/drink needed to be bought — it wasn't needed, but the location was noted for future reference.
6. Sent `quit`, which the server acknowledged ("Goodbye, friend.. Come back soon!") and returned to the character selection menu, then I closed the socket. Verified afterward with `ss`/`ps` that no lingering connection or background process to port 4000 remained.

## Files

- Helper script: `work/mud_client.py` (+ `work/step1.txt`, `work/step2.txt` command scripts)
- Transcripts: `outputs/transcript_step1_score_check.log` (login + score + inventory), `outputs/transcript_step2_eat_drink_probe_and_quit.log` (login + eat/drink probe + look + quit)
