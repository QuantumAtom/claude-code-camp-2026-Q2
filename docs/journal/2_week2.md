
# 

## 00 
### Technical Observations
I was going to setup Jaeger, but Andrew seemed frustrated by it's limitations. I thought about Temporal, but apparently that's overkill. So I decided to use the honeycomb.io free tier. 
- I added the honeycomb.io environmental variables to .env file. 
- Then I added opemtelemetry sdk and config to the boukensha loader
- After, I added tracers to client rb file for running telemetry with the API calls to see telemetry
- Then I added to tool registry rb file as to see what tools were called.

I fought with my LLM to add it to my agent loop, but I was told this wouldn't not tell me as much as what tool was selected.
### Technical Conclusions
