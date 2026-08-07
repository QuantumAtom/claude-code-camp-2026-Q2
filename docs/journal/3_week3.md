#Capability 

## 00 
### Technical Observations
 So I am going to have Claude write code to add an sqlite database and a way to visualize the map. Apparently it will use a pointer to keep track of where it is and then write to the database. I had it do it for Python and Ruby, just in case. Afterwards, I will start doing specific tools using the primitives to to use the database for decision-making.

Also for adding HP to mobs, there is no HP listed in mob description. So we are basically calculating how many hits it takes on average with a certain weapon. Every fight updates the database.

For graphing the locations, we are going to use graphwiz, which is much cleaner than other options. The only unfortunate thing is that it requires graphwiz to be installed system-wide. But the trade off is a cleaner jpeg of locations.

We are also going to setup a new module in case this fails spectacularly and we need a fallback. 
### Technical Conclusions
Setting up the sqlite database required setting certain settings such as deciding whether "magic" is considered a weapon when deciding HP (it went into the weapons database as a pseudoweapon), deciding wether to use graphwiz or something internal to Python. Hopefully, I can use the sqlite database to save tokens and reduce latency. 

## 01 
### Technical Observations
I added z.ai API as I was running out of Claude tokens. I also had it add a tool to go to a location using the sqlite database to figure out where the location is. If it doesn't know the location, but knows which area (Midgaard, castle, chessboard, newbie zone, etc), it can head there. I also made sure that it did not automatically unlock locked door as there could be something dangerous on the other side. I also added a tool for when a player in hungry or thirsty, to look in the inventory and ask the user if they want to eat or drink it. If there is nothing in the inventory, it will ask if the user wants to head to the nearest place for food and drink. They will tell the user how far it is. The only exception are no-cost, no-movement options. (If the user is already in a location with a fountain, the tool will automatically drink from the fountain.) Afterwards, the user has the option of returning where they were.

### Technical Conclusions
Going directly to a location on command reduces token usage and latency. It also is faster. For the drink and eat tool, this will also reduce token usage and latency. The other bonus is that rather than waiting to find a place to squelch their thirst or hunger, they can go head over there, grab a bite or drink and then head back. It is a lot less irritating that way.
