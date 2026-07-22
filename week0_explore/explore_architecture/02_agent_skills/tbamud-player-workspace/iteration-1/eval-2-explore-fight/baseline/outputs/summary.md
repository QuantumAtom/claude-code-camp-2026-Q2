# MUD Exploration Summary — character "dummy"

I connected to the tbaMUD server on localhost:4000 with a small Python script (raw TCP socket, telnet-negotiation bytes stripped), logged in as **dummy**, and picked up right where the character was last left: on **Main Street**.

## Rooms visited

1. **Main Street** (starting room) — a street with the weapon shop to the north, the Guild of Swordsmen to the south, town exit to the east, and the market square to the west.
2. **The Weapon Shop** (north) — smells of metal and quenching oil, gear packed onto every surface, a note on the counter, and a weaponsmith standing by. Only exit south, so I headed back.
3. **The Entrance Hall to the Guild of Swordsmen** (south of Main Street) — a cautious, formal sort of room. An ATM was bolted to the wall, a knight guarded the entrance, a cityguard stood watch, and a **beastly fido** was rooting through the garbage here — my monster encounter.
4. **Main Street (west stretch)** — a different, larger continuation of the street: general store to the north, the market place further west, and a small door south leading to the Pet Shop. A cityguard was posted here too.

## The fight

I attacked the beastly fido in the Guild entrance hall. After a short back-and-forth of misses and glancing hits, I landed the finishing blow — **the fido died and I earned 33 experience points.**

Unfortunately, the fido turned out to be under the protection of the cityguard and a Peacekeeper stationed nearby, and both jumped in to defend it once the fight started. They kept attacking after the fido went down, and my health dropped fast — from full down to just 1 hit point. I fled repeatedly, bouncing through the Tournament and Practice Yard and down into the sewers, before finally losing the guards in **The Junction**, a quiet sewer crossroads with no threats. I rested there to stabilize (health ticked up slightly to 4/23, though hunger and thirst were slowing recovery further).

Given the character was still fragile, I chose not to push my luck with more fights and instead logged off cleanly and safely from that quiet spot.

## Outcome

- **Monster fought:** beastly fido — killed, +33 XP.
- **Complication:** killing it drew in a cityguard and a Peacekeeper who nearly killed me in return (down to 1 HP); escaped by fleeing through several rooms.
- **Character status at logoff:** alive, level 1 "Dummy the Swordpupil", 4/23 HP, safely resting in the sewer Junction, no enemies nearby.
- **Logged off cleanly** with the `quit` command ("Goodbye, friend.. Come back soon!") — no lingering connection was left open.

A full raw transcript of the session is saved alongside this summary as `transcript_full.log`.
