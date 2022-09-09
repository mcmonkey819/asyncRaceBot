# Names of the production and test databases to use
PRODUCTION_DB = "AsyncRaceInfo.db"
TEST_DB = "testDbUtil.db"

# Controls whether the bot will start in test mode
TEST_MODE = True

# Controls whether leaderboards should be sorted by IGT or RTA
RtaIsPrimary = False

# If True, the submission form will include a field for the user to suggest the next weekly mode.
SuggestNextWeeklyMode = True

# If True, the Race Creator role will be pinged on assigned race completion
PingRaceCreatorOnRaceEnd = True

# These are the coolest guys (no gender assumed). The user IDs of the users who are authorized to use the really sensitive features like text_talk which allows the user to talk as the bot
CoolestGuyIds = [ 178293242045923329 ]

# This is the list of cogs to be loaded when the bot is started up
cogs = [ 'cogs.async_handler', 'cogs.server_utils' ]
