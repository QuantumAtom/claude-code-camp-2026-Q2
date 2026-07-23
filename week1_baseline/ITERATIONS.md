# What is the goal for Week1

We want to build a baseline agent that all the ingredients for building any sort of agent

What should it have
- an agentic loop
- a tool registry along with the tools
- it should handle multiple backends
- it should be able to write logs
- It should have a Domain Specific Language (DSL) so that the agent can be used like an SDK
- It needs a global binary execution for CLI interactions
- It should have an option CLI model so that the user can select which model to use
- It needs to manage context and compact messages when reaching set limit or put into a markdown file for external retrieval
- it should have its own config directory

Other features to setup
- log visualizer for better log UI in our browser

## What should baseline be able to do?
It should be able to play the mud with specific commands

## What should the baseline not able to do?
It will have poor perception since it won't be able to manage memory, have poor decision-making ability or a way to be cost-effective with tokens

## Techincal Design Considerations
- We will use REST API directly. This is so we learning how simple it is to interact with managed APIs and how much they vary
- Some SDKs (even the official ones) do not show all the features, so REST API is the way to get full access to some secret feature sets
- Andrew decided on Ruby, but we are porting to Python
- Due to original design, we are using ruby MudManager to interact with MUD
- Preferences for standard libraries when possible over 3rd part libraries

### What should we not use
- We should avoid Agent SDKs since:
    - they implement features what we are implementing by scratch
    - They could limit our ability to execute exactly what we need
    - Examples include OpenRouter, Amazon Strands, CoreAgent, or LangChain
- We should avoid using a code harness to drive the agent since that is a shortcut for our agent task purpose

## Explain Structure Approach
The 'ruby/' folder contains the step-by-step iternation for the agent

### Considerations
- We will need to make manual changes since the original code was not in a ruby sub-folder
- AI affected the handwitten code and so we will find parts that should be rewritten, however we may decide to leave intact as to not disturb future layers
- We will port the code to Python
    - We will have to make sure that the Mudmanager works with Ruby and Python

## Student Completion Approaches
As the student, I have some flexibility in how this is performed:
- Use Andrew's examples verbatim and make the ruby changes on his instructions
    - Can treat ruby implementation as the main implementation
- Ignore Python porting instructionsi
    - If project is not ported to Ruby, then it will be the language of choice for Week 2
- Watch instructions and then do a single port of the last Ruby iteration into the language of my choosing


