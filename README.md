# Async Race Bot
Async Race Bot (ARB) is a Discord bot written in python primarily using the nextcord library and a sqlite database (accessed via peewee ORM). The bot supports commands related to starting, managing and submitting times for async races for [A Link to the Past Randomizer](www.alttpr.com). It makes heavy use of Discord Interactions and the limited set of UI elements supported by that system, namely Select (drop down list), Modal (forms) and Button. The data captured in in the forms and database tables is specific to ALTTPR, however can likely be modified for other games/race types if desired.

# Setting Up ARB in a New Discord Server
There are several steps required to setup ARB to run in a new discord server. Currently ARB only supports a single server at a time which means that each new server needs several things:
  1. New Discord Bot Application (bot name/account)
  2. Fork/branch/local copy of this source code, with config and server info populated for the desired server
  3. Server hosting to run the bot and database on

These are all detailed in sections below. Future versions of ARB may support multiple servers in a single bot instance, if this is a desired feature please add a GitHub issue (or comment on an existing one) to let me know so I can prioritize appropriately.

## New Discord Bot Application
ARB does not come with its own associated discord account. Anyone who wants to setup a new instance of ARB will need to create a Discord Bot account. Instructions for this can be found here: [Creating a Bot Account](https://discordpy.readthedocs.io/en/stable/discord.html)
The bot permissions that have been used for other instances of ARB are listed below. I have made no real effort to trim the list down to the absolute minimum, required permissions and some are forward looking for future features. If any of these are a concern for your server, don't enable that permission and see if things still work. :)
### General Permissions
  * Manage Roles
  * Manage Channels
  * Create Instant Invite
  * Change Nickname
  * Manage Nicknames
  * Manage Webhooks
  * Read Messages/View Channels
  * Manage Events
  * Moderate Members

### Text Permissions
  * Send Messages
  * Create Public Threads
  * Create Private Threads
  * Send Messages in Threads
  * Manage Messages
  * Manage Threads
  * Embed Links
  * Attach Files
  * Read Message History
  * Mention Everyone
  * Use External Emojis
  * Add Reactions
  * Use Slash Commands

### Voice Permissions
  * Mute Members
  * Deafen Members
  * Move Members
  * Use Voice Activity

Once the bot application has been created and added to the server, make a note of the bot token. This token will be added to the bot_tokens.py file when deploying the bot as described in the Bot Config section below. Please note, however, that you SHOULD NEVER ADD THIS TOKEN TO A FILE BEING COMMITTED TO GITHUB. This will publish your token for all the world to see. Conveniently, Discord has added a feature that scans for bot tokens and will disable your bot if you do this. It's then a pain to re-generate and update the config, so save yourself a headache and just don't do it to begin with.

If you are looking to develop features for ARB, it is recommended to create a second bot application for testing purposes. Configuration of ARB includes the ability to run in test mode which will run the bot with a test bot token and run/respond in a separate test server.

## Bot Config
### Getting the Source Code
The first step to configuring the bot is to clone this repo. Even if you only plan to run the bot without any modification, it is recommended to make a new branch or fork the repository so you can save your server and config info. Step-by-step instructions are provided for those relatively new to git.
  1. Install git, on Windows you'll open "Git Bash" when install is complete to run the rest of the commands.
  2. Change to the directory where you'd like to clone the source code. Note: Windows drives are addressed in the unix style (e.g. /c/ instead of C:/)
    `cd /c/git/`
  3. Clone the repo: `git clone https://github.com/mcmonkey819/asyncRaceBot.git`
  4. Once the clone is complete, change to the directory created and pull the latest from the master branch
    `cd asyncRaceBot`
    `git checkout master && git pull`
  5. Create your branch: `git checkout -b <branch_name>`
  
If you plan to push your branch to GitHub in the asyncRaceBot repository, note that the server info will be visible to anyone. I also ask that you use the following naming convention for your branch: <username>/<server_nickname>/ so something like `mcmonkey/forty_bonks`

After making the changes described in the following sections, save your changes by doing `git add -u && git commit -m "Config info for <server nickname>"`

When updates are published to ARB, you can grab the latest changes without losing your server info by following these steps:
  1. From Git Bash, change to you local repo directory: `cd /c/git/asyncRaceBot`
  2. Checkout the master branch and pull latest changes: `git checkout master && git pull`
  3. Change back to your server info branch and use the rebase command to merge in the changes from master: `git checkout <branch_name> && git rebase master`

### Config.py
*TBD Add detail about how to edit config.py*

### Server Info
*TBD Add detail about how to fill in server info*

### Bot Tokens
*TBD add detail about bot_tokens.py*

## Server Hosting
*TBD Add info about server hosting and running the bot (in both production and test modes, locally and on hosting server)*