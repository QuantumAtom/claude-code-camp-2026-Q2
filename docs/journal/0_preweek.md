
# Exploring Claude Agent Architectures

## 01 Using an agent file that reference other files

### Observations

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

### Technical Conclusions

The expensive Fable model works very well for this task. However, it is expensive for doing a task like that. Likely a MUD SDK or MUD Manager would mitigate those costs. Also possibly being more explicit in the CLAUDE.md file or using a switch statement. The information was very well filled out however for player.md and world.md.

## 02 Agent skills used by primary agent (Claude)
### Technical Observations
We will be using agent skills (an open common format adopted by many coding harnesses and Agent SDKs for agent use). Our coding harness will be Claude Code. 

It took a while, but not as many tokens to generate the tbamud-player skill. It tested the skills with the running server and it worked.

I ran skill and only had to ask to find the bakery (which it was at from testing the skill when it was developing it before). Then I ask it show the menu. It only required one request for each. 

I checked going to the temple and back to the bakery (since we started at the bakery) and reading the bakery menu. Please note that I originally asked to read the menu and that confused the agent. When I asked to read the bakery menu, it worked. There was no unnecessary command executions as far as I could see. It understood the locaton and how to get there. Once I gave the correct request for the menu, it simply read back the menu.

- Sonnet
    - 1.8k tokens to walk to the temple and back to the bakery
    - 700 tokens to read the bakery menu
- Haiku
    - 800 tokens to go to the temple and back to the bakery
    - 500 tokens to read the bakery menui


- This portion was done with Claude Sonnet

I had the agent try to practice kick. It found some coins and tried to purchase practice sessions from the guildmaster. That didn't work. So it checked the bulletin board, which showed nothing. Then it checked how many practices it had left. It discovered it had none until it leveled up. So it killed two bats to get more experience, but discovered that wasn't enough. It gave up instead of searching for more experience, possibly due to lack of enemies nearby.

I had claude with the tbamud-skill document player and world information in a data folder. I am having it kill the minotaur and interesting enough, it is grinding to build up. It might just be fighting everything in it's path. It is certainly playing better than I would. Also, it just grinds without telling me what it is doing, so I can cancelled the command and reran it as well as telling me to print everything that happens. 

So the agent skill checks in with me as to what to do. I told it to do what it wants. It is taking a cautious approach by going to get food and drink. Interesting that it kept fighting when it was working on its own, but more cautious when having to describe what to do.

So with that caution, the massive minotaur was killed at level 3. This may have been due to luck as after reviewing the fight, the "dummy" character missed a lot of the Minotaur's blows. I am having it write the details in the player.md and world.md files
## Technical Conclusions

- Claude code generally takes a stronger approach when it is not documenting in real time. 
- Takes a more cautious approach when asked to print decisions in real time. It will also ask what to do despite not being directed to do so. Consistently told the agent to decide on it's own
- It was able to complete the task with probably 30k-40k tokens using Sonnet
- Giving specific instructions is key. When I told the agent to print to /data/world.md and /data/player.md, it tried to do generate and write those files within the agent skills folder. 
- Claude skills directory can be placed anywhere and then use a symbolic link to .claude/skills folder.

## 03a Subagent skill - file-based

- Noticable the agent started immediately dealing with hunger and upskilling.
- Concurrently running skills is a bit of a myth. It send Dummy to his swordmen guild and Smarty to magic guild afterward.
- Both agent skills and subagent provide similar functionality
- I can have both logged in at the same time, but Claude (and maybe other agents) will only run one command at a time, switching between subagents.
- The subagents can read both skills and then pass it to the main agent who will tell me both their ages, mana, and max movements
- Probably should get separate memory for each subagent
- This increases model usage and cost. Could be a major factor with frontier models like Fable.

### 03b Subagent skill - Claude SDK for Python
- Both agents are starting the same time, less asyncronous. 
- Originally it just did a check on the users. I had Claude redo the Python code to allow interactive experience
- Parallel agents work, but I had to reask several times using Python Claude Agent SDK. Perhaps need to be more specific
- The file-based system is cleaner and easier, but Python Agent SDK is good for complexity.
