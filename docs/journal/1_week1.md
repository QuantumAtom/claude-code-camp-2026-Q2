
Note: I didn't know that I was supposed  to be keeping records of what was going on at the time, so this was written after all steps were performed. 

# 

## 00 
### Technical Observations
This ran pretty smoothly, The config module example when ran, just worked. It showed how the connection information, and which model to use 

### Technical Conclusions
I learned about Ruby and that apparently it uses a Gem Bundle. Fun-o

## 01 
### Technical Observations
I did reformed this one and worked with Python using Sakana Fugu. Surprisingly, it worked well. It only cost $8.00 worth of tokens.

### Technical Conclusion


## 02 
### Technical Observations
This sets up the a registry for tools that can be called. Interestingly, I am having issues seeings what tools can be called.  

### Technical Conclusions
We only have a structure and tool registry. We will not be able to do much, but this provides a very loose skeleton of what can be done.
## 03 
### Technical Observations
Finally, some meat and potatoes. This helps build the prompt that will be passed to the API. It contains the context window limits, base URL, and the model to be selected. It would be curious if I could copy and paste the OpenAI API and with some modifications to the base URL and model if I could use the open weight models. I am moderately surprised that some of the more model-specific information is not stored in .boukensha directory for more modularity. But it does work, so there is that.
### Technical Conclusions

## 04 
### Technical Observations
This is where the actual API call is done for the SDK. It pulls from the .bokensha settings.yaml which pulls from the environmental variable. A major part of passing this comes from config.rb 
### Technical Conclusions

## 05 
### Technical Observations
This is where a lot of the modules are pulled together with the agent loop. This is where the agentic loop and decision making tend to be.
### Technical Conclusions

## 06 
### Technical Observations
This lets us keep logs of actions, tokens and so forth. It can be stored in a JSON file or using Log Viz which Andrew very helpfully provided.
### Technical Conclusions

## 07 
### Technical Observations
The DSL run let's all the manual wiring be done from one call, which is Boukensha.run. It pulls from tool method, apparently it can't reach internal plumbing (since this is all part of one SDK, not sure how this helps with security, but it does). It is one shot so no storing context windows. Runs once and forget it. Can be cheaper for token, but has less previous information to pull from.
### Technical Conclusions

## 08 
### Technical Observations
The REPL loop does what DSL does, but it keeps a context window and has built-in commands (primitives, I think they are called). 
### Technical Conclusions

## 09 
### Technical Observations
Global executable provides a Gem to run the SDK instead of just executing scripts. We did not covert the Ruby Gem to a Python equivalent like TOML.
### Technical Conclusions

## 10 
### Technical Observations
This allows file manipulation and external commands that are similar to what would be used in BASH. 
### Technical Conclusions

## 11 
### Technical Observations
TUI is the Terminal User Interface that we pulled from Charm Bubble Tea, bringing color and panache. It also providers keyboard shortcuts that many CLI users will appreciate. I changed the colors to something more regal and RPG like. There is lots of flexibility in Charm Bubble Tea
### Technical Conclusions

## 12 
### Technical Observations
Context allows real-time view of token usage and context window so users can make sure that they aren't splurging on excessive tokens. 
### Technical Conclusions
