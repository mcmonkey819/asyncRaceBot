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

Once the bot application has been created and added to the server, make a note of the bot token. This token will be add

### Voice Permissions
  * Mute Members
  * Deafen Members
  * Move Members
  * Use Voice Activityed to the bot_tokens.py file when deploying the bot as described in the Bot Config section below. Please note, however, that you SHOULD NEVER ADD THIS TOKEN TO A FILE BEING COMMITTED TO GITHUB. This will publish your token for all the world to see. Conveniently, Discord has added a feature that scans for bot tokens and will disable your bot if you do this. It's then a pain to re-generate and update the config, so save yourself a headache and just don't do it to begin with.

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
Config.py has a few options and fields that should be reviewed before launching ARB.
  | Field | Description | Example/Format |
  | -------------- | ------------- | -------------- |
  | PRODUCTION_DB | Name of the production database to use. Should be in the same directory as the main bot file `async_race_bot.py` | "AsyncRaceInfo.db" |
  | TEST_DB | Name of the database to use in test mode. Should be in the same directory as the main bot file `async_race_bot.py` | "testDbUtil.db" |
  | TEST_MODE | Flag that controls whether the bot is started in test mode | True or False |
  | RtaIsPrimary | Flag that controls whether leaderboards should be sorted by in-game time (IGT) or real time (RTA) | True or False |
  | SuggestNextWeeklyMode | If True, the submission modal will include a field for the user to suggest the next weekly mode | True or False |
  | CoolestGuyIds | Python list of discord IDs corresponding to the users who are authorized to use the really sensitive features like text_talk which allows the user to talk as the bot | `[ 178293242045923329, 853066341502156870 ]` |
  | cogs | This is the list of cogs to be loaded when the bot is started up. Server utils contains VC create/destroy functionality, async_handler contains async race and misc functions | `[ 'cogs.async_handler', 'cogs.server_utils' ]` |

Example sqlite database files are provided for the production and test database that contain the required tables/fields. You can create your own, referencing the table names/layout in `async_db_orm.py`

### Server Info
There is also some server specific information that needs to be added to async_handler.py. The ServerInfo class contains comments describing each field and an example of a filled-in instance of this class follows the class definition along with a comment about how to add that instance to the `SupportedServerList`. All channel, user and role IDs are discord IDs. The easiest way to get these IDs is to use the desktop Discord application, right click on the user/channel/role in question and select `Copy Id`.

### Bot Tokens
There is one required file that is explicitly NOT included in this repository and will need to be manually created to run ARB. This file should be named bot_tokens.py and will contain two variables with the bot tokens of your Discord production and test bot applications. These can be the same token if you don't plan to do any development work. It is mentioned above, but bears repeating: DO NOT ADD bot_tokens.py TO THE GIT REPO. This will potentially publish your secret bot tokens for all the world to see. The following is an example of what the contents of bot_tokens.py should look like:
```
PRODUCTION_TOKEN = 'ThisIsAFakeProductionBotToken__ASF^D&*FASHR!(*HKLFASFJKLhjfsahjk'
TEST_TOKEN = 'ThisIsAFakeTestBotToken_ItCanBeTheSameOne_FASHKJLFASJL:ujlksfa'
```

## Server Hosting & Launching ARB
### Running Locally
ARB can be run locally from a command prompt. This is useful for testing configuration setup and if doing feature development or bug fixing. These instructions assume running on Windows. ARB should run just fine on another OS that supports Python and the required libraries, and if you're on one of those I'm going to assume you can figure it out with this info anyway.

  1. [Install Python](https://www.python.org/downloads/). You don't need the absolute latest version, as long as it's 3.6 or above you should be fine.
  2. Install the required python packages. You'll want to open a command prompt or git bash window and run the following command for each required package, for example `pip install nextcord`
     * nextcord
     * nextcord.ext
     * logging
     * prettytable
     * datetime
     * random
     * peewee
  3. From the root of the ARB repo (e.g. /c/git/async_race_bot/) run: `python async_race_bot.py`
  4. The bot should now be running, any log or error messages will be displayed on the terminal. To stop the bot use Ctrl-C. This is sometimes delayed, you can speed it up by sending any message in a discord channel the bot listens to.

### Remote Hosting
This section describes how I have hosted ARB to run in the past. There are *many* other options for hosting a discord bot, so feel free to shop around. I use [PebbleHost](https://pebblehost.com/bot-hosting) for hosting and have been satisfied with their service. It is currently $3 US per month for hosting. Once an account has been created with a server, you'll first want to Select Languages & Preinstalls and select the Python Bot option. Next, go to File Manager and upload the following files from your local repo:
  * async_db_orm.py
  * async_race_bot.py
  * <PRODUCTION DB> (e.g. AsyncRaceInfo.db)
  * bot_tokens.py
  * config.py (don't forget to change TEST_MODE to False when deploying for production)
  * the cogs folder

Once the files are uploaded you should next go to Python Package Manager and copy the list of required packages from the Running Locally section to the requirements.txt displayed. Finally, back on the main server page, enter `async_race_bot.py` in the Start File field. You can now click the Start button to launch the bot. The Console page is useful to see bot output.