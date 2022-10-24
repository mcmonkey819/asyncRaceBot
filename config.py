from server_info import *

# Names of the production and test databases to use
PRODUCTION_DB = "GmpRaceInfo.db"
TEST_DB = "testDbUtil.db"

PRODUCTION_SERVER = GmpServerInfo
TEST_SERVER = BttServerInfo

# Controls whether the bot will start in test mode
TEST_MODE = False

# Controls whether leaderboards should be sorted by IGT or RTA
RtaIsPrimary = False

# If True, the submission form will include a field to capture the secondary time (IGT or RTA)
ShowSecondaryTimeField = False

# If True, the submission form will include a field for the user to suggest the next weekly mode.
SuggestNextWeeklyMode = False

# If True, the Race Creator role will be pinged on assigned race completion
PingRaceCreatorOnRaceEnd = True

# If True, race creators will be prompted to confirm starting a race to ensure the roster is correct
RosterPromptOnRaceStart = False

# These are the coolest guys (no gender assumed). The user IDs of the users who are authorized to use the really sensitive features like text_talk which allows the user to talk as the bot
CoolestGuyIds = [ 178293242045923329 ]

# This is the list of cogs to be loaded when the bot is started up
#cogs = [ 'cogs.async_handler', 'cogs.server_utils' ]
cogs = [ 'cogs.async_handler' ]
