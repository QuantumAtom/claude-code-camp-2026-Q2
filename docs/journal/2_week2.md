
# 

## 00 Honeycomb.io setup
### Technical Observations
I was going to setup Jaeger, but Andrew seemed frustrated by it's limitations. I thought about Temporal, but apparently that's overkill. So I decided to use the honeycomb.io free tier. 
- I added the honeycomb.io environmental variables to .env file. 
- Then I added opemtelemetry sdk and config to the boukensha loader
- After, I added tracers to client rb file for running telemetry with the API calls to see telemetry
- Then I added to tool registry rb file as to see what tools were called.
- Apparently Honeycomb doesn't use the default port of 4318 for OTEL (OTLP). 

I fought with my coding agent and LLM to add it to my agent loop, but I was told this wouldn't not me as much as what tool was selected.

Incidentally, with the amount of API tokens that Boukensha is consuming, I am thinking of setting up an API client connection to Minimax 3, which is comparable to Sonnet 4.6 with less token consumption.
### Technical Conclusions
Although I appreciate Andrew's use of Garafana and Jaeger, with some minor adjustments in adding telemetry to the code, using a cloud based OTEL provider was fairly easy. Also I discovered that my .boukensha environment variables were user-wide instead of project-wide. 

## 01 Honeycomb.io additional observability and instrumentation
### Technical Observations
There are very few failures among API calls. That was because I spent my non-subscription API tokens. Simple commands seem to eat up quite a few tokens when asking to move. Observing surroundings take few less. Since I am limited in what telemetry is sent to honeycomb.io, I had more instrumentation added to honeycomb.io. I normally would only allow token count, but since I wanted to see more information and this isn't a sensitive project, I added more to see what API calls are being made. Normally, if this was a production environment with sensitive information, I would probably check what certification honeycomb.io has (i.e. SOC3, etc)

Apparently, every llm call is considered its own span.

The new instrumentation required changes to the following files:

- Agent.rb
- conversation_span_processor.rb - for adding conversation telemetry
- boukensha.rb - new Boukensha.tracer method that the ConversationSpanProcessor is included
- client.rb - replaced the previous Tracer constant with Boukensha.tracer.in_span
- registry.rb - Same, replaced the previous Tracer constant with Boukensha.tracer.in_span

Input tokens are oddly enough taking more tokens than output tokens
### Technical Conclusions
With the additional information, I can now drill down into deeper information about latency, token usage, and what commands eat up the most tokens.

## 02 Latency, errors, and tokens, oh my!
### Technical Observation
Honeycomb.io showed no errors aside from overspending my Claude API tokens. Looking at my current spend afterwards, it seems like simple commands seem to eat up quite a few tokens. I went from $20 additional token credits to $12.12 with eating, drinking, movement, and very occasional fighting. 

I checked which tools have the highest latency and by far it is `send_raw` That tool sends non-standard commands that aren't things like "look" or "move". So, since it is waiting for a socket timeout instead of knowing and expecting the response structure. 

The number one cause of that is opening or unlocking the door. I added "open" and "unlock" as tools to use (it is using the `p.door` primitive). Also, I added "read" as that is used too (it is using the `p.look` primitive).

After adding it, I reduced the execution time from 1,187 ms to 153.9 ms for doors. The change has no effect on token usage.

The span with the most depth is invoke-agent, because in the code, it is part of the telemetry that contains the agent code. 
 
As for token usage, the largest trace is when I asked to quench my thirst. All my bottles were empty and instead of checking that, it did a span of trying to drink each bottle and then headed to the fountain (directly south). That took 65,450 tokens to find out. A simple go to the fountain and drink would be around 7.4k tokens based on the token use to do just that. 

I just did some more exploring in the sewer. It cost a new whopping 68,289 tokens because it kept backtracking to return back to Midgaard. However, the latency was less because they were "move" only.

Also the OTEL telemetry noted that there was coin that was left untouched. I am thinking about adding some capabilities like building a sqlite database with location and what is in each location. 

### Technical Conclusions
I was able to weave a story of how latency and token usage can affect optimization of the AI SDK. Sometimes, by checking what processes are explicit instead of having instruction inference, we can save quite a few tokens and speed up the SDK by having it know exactly what to anticipate instead of waiting for the AI model to infer. It is also worth noting that by having less inference, it can save a lot on tokens and speed up latency by not having the span wait on a socket timeout in a trace. More explicit instructions instead of expecting common sense (i.e. checking whether the water bottle is empty) or have the AI figure it out (opening and unlocking a door) helps a lot. For my next trick, I will try to add an sqlite database of locations visited while documenting mobs (friend or enemy), items available, title of location, which area the location is part of (i.e. sewer, castle, town, newbie zone, etc), and the exits. 
