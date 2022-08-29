from nextcord.ext import commands
import nextcord
import logging
import asyncio
from datetime import datetime
import random
import config

ServerId        = 0
RaceCreatorRole = 1
PermanentVcId   = 2
VcIgnoreList    = 3

# 40 Bonks Server Info
FortyBonksServerInfo = {
    ServerId: 485284146063736832,
    RaceCreatorRole: 782804969107226644,
    PermanentVcId: 873375035547607040,
    VcIgnoreList: [863951202738765846, 797911298171338772, 800072377693765693]
}

# Bot Testing Things Server Info
BttServerInfo = {
    ServerId: 853060981528723468,
    RaceCreatorRole: 888940865337299004,
    PermanentVcId: 853060982031908907,
    VcIgnoreList: [920371997874217021]
}

class ServerUtils(commands.Cog, name='ServerUtils'):
    '''Cog which handles commands related to Async Races.'''

    def __init__(self, bot):
        self.bot = bot
        self.test_mode = False
        self.server_info = FortyBonksServerInfo
        if config.TEST_MODE:
            self.setTestMode()
        self.on_demand_vc_ids = []

########################################################################################################################
# Utility Functions
########################################################################################################################
    def setTestMode(self):
        self.test_mode = True
        self.server_info = BttServerInfo

    def isVcJoin(self, before, after):
        if before.channel is None and after.channel is not None:
            return True
        return False

    def isVcLeave(self, before, after):
        if after.channel is None and before.channel is not None:
            return True
        return False

    def isVcSwitch(self, before, after):
        if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            return True
        return False

########################################################################################################################
# ON_READY
########################################################################################################################
    @commands.Cog.listener("on_ready")
    async def on_ready_handler(self):
        logging.info("Server Utils Ready")
        if self.test_mode:
            logging.info("  Running in test mode")

########################################################################################################################
# ON_VOICE_STATE_UPDATE
#
# When a user joins a voice channel, this will check to make sure there is at least one empty voice channel remaining,
# if not it will add a new one. It will also clean up extra voice channels that have been created on demand when they
# are empty.
########################################################################################################################
    @commands.Cog.listener("on_voice_state_update")
    async def on_vc_update_handler(self, member, before, after):
        logging.info("Running on_vc_update_handler")

        join_channel = None
        leave_channel = None
        if self.isVcJoin(before, after):
            join_channel = after.channel
        elif self.isVcLeave(before, after):
            leave_channel = before.channel
        elif self.isVcSwitch(before, after):
            leave_channel = before.channel
            join_channel = after.channel

        # If the member is joining a channel
        if join_channel is not None and join_channel.id not in self.server_info[VcIgnoreList]:
            # Check if there is at least one empty voice channels remaining (not including the ignore list or the permanent VC)
            found_empty = False
            logging.info("Channel join, checking for empty channels")
            perm_vc = join_channel.guild.get_channel(self.server_info[PermanentVcId])
            if not perm_vc.members:
                logging.info(f"Permanent Voice Channel '{perm_vc.name}' is empty")
            else:
                for vc in after.channel.guild.voice_channels:
                    if vc.id in self.server_info[VcIgnoreList] or vc.id == self.server_info[PermanentVcId]: continue
                    if not vc.members:
                        found_empty = True
                        logging.info(f"Found empty channel {vc.name}")
                        break
                # If not, create a new one by cloning the permananent one
                if not found_empty:
                    logging.info("No empty channels, creating a new one")
                    guild = after.channel.guild
                    perm_vc = guild.get_channel(self.server_info[PermanentVcId])
                    adj = random.choice(adjectives)
                    noun = random.choice(nouns)
                    new_channel = await perm_vc.clone(name=f"{adj} {noun}")
                    self.on_demand_vc_ids.append(new_channel.id)

        # If the member is leaving a channel
        if leave_channel is not None and leave_channel.id not in self.server_info[VcIgnoreList]:
            logging.info("Channel leave, checking for empty channels to clean up")
            # Sleep for a few seconds
            await asyncio.sleep(10)
            # Check for empty channels in the on demand list
            guild = leave_channel.guild
            perm_vc = guild.get_channel(self.server_info[PermanentVcId])
            # Skip removing the first empty on-demand channel if the permanent VC is not empty
            skip_first_empty = False if not perm_vc.members else True
            for vc in self.on_demand_vc_ids:
                channel = guild.get_channel(vc)
                if not channel.members:
                    if skip_first_empty:
                        skip_first_empty = False
                        continue
                    logging.info(f"Removing empty channel '{channel.name}'")
                    self.on_demand_vc_ids.remove(vc)
                    await channel.delete()

def setup(bot):
    bot.add_cog(ServerUtils(bot))

########################################################################################################################
# Zelda themed word lists used to generate on-demand VC names
adjectives = [
"Fast",
"Slow",
"Early",
"Late",
"Missing",
"Pointless",
"Required",
"Missing",
"Never-ending",
"Easy",
"Impossible",
"Clean",
"Terrible",
"Hidden",
"Obvious",
"Underrated",
"Convenient",
"Helpful",
"Annoying",
"Fun",
"Cute",
"Ok",
"Immediate",
"Worthless",
"Important",
"Scary",
"Beautiful",
"Funny",
"Interesting",
"Confusing",
"Unusual",
"Big",
"Swaggy",
"Fancy",
"Imaginary",
"Smart",
"Drunk",
"Angry",
"Embarrassing",
"Greedy",
"Brave",
"Suspicious",
"Satisfying",
"Organic",
"Hideous",
"Inconclusive",
"Absurd",
"Hapless",
"Successful",
"Dead"
]

nouns = [
"Sword",
"Shield",
"Moon Pearl",
"Bow",
"Boomerang",
"Hookshot",
"Bombs",
"Mushroom",
"Powder",
"Fire Rod",
"Ice Rod",
"Bombos",
"Ether",
"Quake",
"Lamp",
"Hammer",
"Shovel",
"Flute",
"Bug Net",
"Book",
"Bottle",
"Cane Of Somaria",
"Cane Of Byrna",
"Cape",
"Mirror",
"Boots",
"Gloves",
"Mitts",
"Flippers",
"Aga",
"Armos",
"Eastern",
"Lanmo",
"Desert",
"Moldorm",
"Hera",
"Helma",
"PoD",
"Arrghus",
"Swamp",
"Mothula",
"Skull Woods",
"Blind",
"Thieves Town",
"Kholdstare",
"Ice Palace",
"Vitty",
"Mire",
"Trinexx",
"Turtle Rock",
"GT",
"Ganon",
"Lost Woods",
"Kakariko",
"Bottle Vendor",
"Sick Kid",
"Smiths",
"Sanctuary",
"Zelda",
"Saha",
"Hyrule Castle",
"South Shore",
"Village of Outcasts",
"Lake Hylia",
"Death Mountain",
"Dark Death Mountain",
"Light World",
"Dark World",
"Library",
"Tavern",
"Well",
"Bonk Rocks",
"GYL",
"King's Tomb",
"Potion Shop",
"Catfish",
"Zora",
"Dam",
"Aginah",
"Maze Race",
"Dig Game",
"Stumpy",
"Big Bomb",
"Spike Cave",
"Hera Basement",
"Left Side Swamp",
"Tile Room"
]