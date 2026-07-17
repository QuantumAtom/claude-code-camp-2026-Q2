## Observations

I tried to have the coding agent locate the bakery as a regular player

- Used Claude Haiku
    - The agent generated mud_client.py and tried to repetitively log in
    - It said that it had trouble with character creation (since the character existed, that indicates a login issue)
    - When it failed, it would regenerate a new python script, asking each time. It would use the same name
    - Consistently, it failed with logging in. It was however able to connect without being told to use nc or telnet. It assumed it on it's own

- Used Claude Fable
    - It was able to succeed in connecting and logging.
    - Stated it was able to log in and bypass time-out by automating the login in a single background process
    - It tried to use the infrastructure/lib/world files to locate the bakery.
        - Since it is supposed to impersonate a player, I told the coding agent that it was not allowed to use it.
        - The agent then stopped the loop
    - I had it try again expressly stating that it was not use any extra files for help as it was to simulate a player.
    - It was able to connect, log in, and run to the bakery, having to backtrack only once
    - It took 51.6k tokens in Fable to accomplish this.

## Technical Conclusions

The expensive Fable model works very well for this task. However, it is expensive for doing a task like that. Likely a MUD SDK or MUD Manager would mitigate those costs. Also possibly being more explicit in the CLAUDE.md file or using a switch statement. The information was very well filled out however for player.md and world.md.
