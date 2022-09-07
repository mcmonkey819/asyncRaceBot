# -*- coding: utf-8 -*-
from nextcord.ext import commands
import nextcord
import logging
from prettytable import PrettyTable, DEFAULT, ALL
import re
import asyncio
from datetime import datetime, date
from async_db_orm import *
from enum import Enum
from typing import NamedTuple
import config

# Collection of information about a supported server.
class ServerInfo(NamedTuple):
    # Global Info - Unless otherwise noted these fields are required
    server_id: int
    race_creator_role: int
    race_creator_channel: int
    bot_command_channels: list[int]

    # Weekly Async Info
    #-------------------
    # This is the channel where the seed link and submit, FF, Leaderboard buttons will be displayed.
    # This field is required for weekly async support
    weekly_submit_channel: int
    # This is the database race category ID for the weekly races. This category is treated special
    weekly_category_id: int
    # This field is optional. If populated (non-zero) the leaderboard for the current active race will be displayed
    # here and updated with each new submission
    weekly_leaderboard_channel: int
    # The following two fields are optional. If populated (non-zero) an announcement will be posted in this channel when a new weekly race is started
    # If the role is populated (non-zero) it will be pinged when the announcement is posted.
    announcements_channel: int
    weekly_racer_role: int
    # This field is optional. If populated (non-zero) this role will be given to a user after submitting or FF from the current race.
    # This can be used to control access to a spoiler channel for users who have completed the seed
    weekly_race_done_role: int

    # Tourney Async Info
    #--------------------
    # This is the channel where the seed link and submit, FF, Leaderboard buttons will be displayed for the active races. 
    # This field is required for tourney async support
    tourney_submit_channel: int

# Bot Testing Things Server Info
BttServerInfo = ServerInfo(
    server_id = 853060981528723468,
    race_creator_role = 888940865337299004,
    weekly_submit_channel = 892861800612249680,
    weekly_category_id = 1,
    tourney_submit_channel = 952612873534836776,
    race_creator_channel = 896494916493004880,
    bot_command_channels = [ 853061634855665694, 854508026832748544, 896494916493004880 ],
    weekly_race_done_role = 895026847954374696,
    weekly_leaderboard_channel = 895681087701909574,
    announcements_channel = 896494916493004880,
    weekly_racer_role = 931946945562423369,

SupportedServerList = [ BttServerInfo.server_id ]

# To add a supported server, create a ServerInfo structure then override the list like so:
#if not config.TEST_MODE:
#     SupportedServerList = [ FortyBonksServerInfo.server_id ]
# Adding multiple servers to the list is NOT supported, it is formatted as a list to match nextcord interface. The AsyncHandler class assumes a single supported server at a time, set by the server_info class field

# Discord limit is 2000 characters, subtract a few to account for formatting, newlines, etc
DiscordApiCharLimit = 2000 - 10
ItemsPerPage = 5

# We use certain emojis and it's easier to refer to a variable name than use the emoji itself, particularly for the user specific ones
PoopEmoji = '💩'
ThumbsUpEmoji = '👍'
ThumbsDownEmoji = '👎'
ToiletPaperEmoji = '🧻'
PendantPodEmoteStr = '<:laoPoD:809226000550199306>'

# Define some canned messages that are used in multiple places by some bot features
AlreadySubmittedMsg = "You've already submitted for this race, use the 'Edit Time' button to modify your submission"
NoPermissionMsg = "You do not have permissions to use this command in this channel"
SubmitChannelMsg = "Click below to submit/edit a time or FF from this week's race. Once you've submitted a time you can view the leaderboard."

# Returns a dictionary of race category options from the database, where the key is the category name and the value is the category ID.
# This is used to create a Select UI element with the race categories as drop down options.
def getRaceCategoryChoices():
    cats = RaceCategory.select()
    choices = {}
    for c in cats:
        choices[c.name] = c.id
    return choices

# Returns a dictionary of inactive races from the race database, where the key is a string containing race ID and description and the value is the race ID.
# This is used to create a Select UI element with the races as drop down options.
def getInactiveRaceChoices():
    races = AsyncRace.select().where(AsyncRace.active == False)
    choices = {}
    for r in races:
        choices[f"{r.id} - {r.description}"] = r.id
    return choices

# Used to sort game times stored in the database (IGT or RTA)
def sort_game_time(submission):
    game_time = submission.finish_time_igt
    if config.RtaIsPrimary:
        game_time = submission.finish_time_rta
    # Convert the time to seconds for sorting
    ret = 0
    if game_time is not None:
        parts = game_time.split(':')
        ret = (3600 * int(parts[0])) + (60 * int(parts[1])) + int(parts[2])
    return ret

class AsyncHandler(commands.Cog, name='AsyncRaceHandler'):
    '''Cog which handles commands related to Async Races.'''

    def __init__(self, bot):
        self.bot = bot
        self.test_mode = False
        # Once server info is defined, it should be set here as follows:
        # self.server_info = FortyBonksServerInfo
        if config.TEST_MODE:
            self.setTestMode()
        self.pt = PrettyTable()
        self.resetPrettyTable()
        # Controls poop emoji cleanup behavior.
        self.replace_poop_with_tp = False

    def setTestMode(self):
        self.test_mode = True
        self.server_info = BttServerInfo

########################################################################################################################
# UI Elements
########################################################################################################################

    ########################################################################################################################
    # SUBMIT_TIME Elements
    class SubmitType(Enum):
        SUBMIT  = 1
        EDIT    = 2
        FORFEIT = 3

    # This modal will display a form that has fields matching the required info for a database submission or a forfeit. 
    # On completion it will call the AsyncHandler submit_time function to add the submission to the database.
    class SubmitTimeModal(nextcord.ui.Modal):
        def __init__(self, asyncHandler, race_id, isWeeklyAsync, submitType):
            super().__init__("Async Time Submit", timeout=None)
            self.asyncHandler = asyncHandler
            self.race_id = race_id
            self.isWeeklyAsync = isWeeklyAsync
            self.submitType = submitType

            self.igt = nextcord.ui.TextInput(
                label="Enter IGT in format `H:MM:SS`",
                required=not config.RtaIsPrimary,
                min_length=7,
                max_length=8)

            self.rta = nextcord.ui.TextInput(
                label="Enter RTA in format `H:MM:SS`",
                required=config.RtaIsPrimary,
                min_length=7,
                max_length=7)

            self.collection_rate = nextcord.ui.TextInput(
                label="Enter collection rate`",
                min_length=1,
                max_length=3)

            self.comment = nextcord.ui.TextInput(
                label="Enter Comment",
                required=False,
                min_length=1,
                max_length=1024)

            self.next_mode = nextcord.ui.TextInput(
                label="Enter Next Mode Suggestion",
                required=False,
                min_length=1,
                max_length=1024)

            if submitType is not AsyncHandler.SubmitType.FORFEIT:
                self.add_item(self.igt)
                self.add_item(self.collection_rate)
                self.add_item(self.rta)
            self.add_item(self.comment)
            if isWeeklyAsync and config.SuggestNextWeeklyMode:
                self.add_item(self.next_mode)

        async def callback(self, interaction: nextcord.Interaction) -> None:
            await self.asyncHandler.submit_time(self, interaction, self.race_id)
            if self.isWeeklyAsync:
                await self.asyncHandler.assignWeeklyAsyncRole(interaction.guild, interaction.user)

    ########################################################################################################################
    # ADD/EDIT_RACE Elements
    # Displays a modal form that collects information required to add or edit a race in the database.
    # On completion, saves the race in the database and calls the member callback function if it has been populated.
    # This callback mechanism is used by AsyncHandler to do special handling of weekly races (announcement, roles, etc).
    class AddRaceModal(nextcord.ui.Modal):
        def __init__(self, race=None):
            super().__init__("Add Race", timeout=None)
            self.start_race_callback = None
            self.race = race
            self.category_id = None

            self.mode = nextcord.ui.TextInput(
                label="Mode Description`",
                min_length=1,
                max_length=50)
            self.add_item(self.mode)

            self.seed = nextcord.ui.TextInput(label="Seed Link`")
            self.add_item(self.seed)

            self.instructions = nextcord.ui.TextInput(
                label="Additional Instructions`",
                required=False)
            self.add_item(self.instructions)

        async def callback(self, interaction: nextcord.Interaction):
            start_date = None
            is_create = False
            if self.race is None:
                # Create a new race
                race = AsyncRace()
                is_create = True
            else:
                race = self.race
            race.seed = self.seed.value
            race.description = self.mode.value
            race.additional_instructions = self.instructions.value
            race.category_id = self.category_id
            race.active = False if is_create else race.active
            race.save()
            verb = "Added" if is_create else "Edited"
            await interaction.send(f"{verb} race ID: {race.id}")
            if self.start_race_callback is not None:
                await self.start_race_callback(interaction, race)

    # Implements a Select (drop down list) with a list of available race categories in the database
    # On selection, calls the provided callback function
    class CategorySelect(nextcord.ui.Select):
        def __init__(self, callback_func, data):
            self.callback_func = callback_func
            self.user_data = data

            # Query the categories
            categories = RaceCategory.select()

            # Create the options list from the categories
            options = []
            for c in categories:
                options.append(nextcord.SelectOption(label=c.name, description=c.description, value=str(c.id)))

            # Initialize the base class
            super().__init__(
                placeholder="Select Race Category...",
                min_values=1,
                max_values=1,
                options=options)

        async def callback(self, interaction: nextcord.Interaction):
            await self.callback_func(interaction, int(interaction.data['values'][0]), self.user_data)

    # Discord View object that prompts the user with a CategorySelect and sends the selection to the AddRaceModal
    class AddRaceView(nextcord.ui.View):
        def __init__(self, add_race_modal):
            super().__init__(timeout=None)
            self.add_race_modal = add_race_modal
            self.category_select = AsyncHandler.CategorySelect(self.callback_func, add_race_modal)
            self.add_item(self.category_select)

        async def callback_func(self, interaction, category_id, add_race_modal):
            self.add_race_modal.category_id = category_id
            await interaction.response.send_modal(self.add_race_modal)

    # Discord View object that prompts the user with a CcategorySelect and sends the result to the provided callback function.
    class CategorySelectView(nextcord.ui.View):
        def __init__(self, callback_func, data):
            super().__init__(timeout=None)
            self.category_select = AsyncHandler.CategorySelect(callback_func, data)
            self.add_item(self.category_select)

    ########################################################################################################################
    # Select UI element that prompts the user if they are sure, with Yes or No options in a drop down. On selection, sends
    # the user choice to the provided callback function
    class YesNoSelect(nextcord.ui.Select):
        def __init__(self, callback_func, data):
            self.callback_func = callback_func
            self.data = data
            options = [
                nextcord.SelectOption(label="Yes", description="Yes", emoji=ThumbsUpEmoji),
                nextcord.SelectOption(label="No", description="No", emoji=ThumbsDownEmoji)]

            # Initialize the base class
            super().__init__(
                placeholder="Are you sure?",
                min_values=1,
                max_values=1,
                options=options)

        async def callback(self, interaction: nextcord.Interaction):
            await self.callback_func(interaction, (self.values[0]=="Yes"), self.data)

    # Discord view that shows a YesNoSelect and sends the chosen option to the provided callback
    class YesNoView(nextcord.ui.View):
        def __init__(self, callback_func, data):
            super().__init__(timeout=None)
            self.add_item(AsyncHandler.YesNoSelect(callback_func, data))

    ########################################################################################################################
    # Race Selection Elements
    # Select UI element that prompts the user to select a race from a list of active races. The result is sent to the
    # provided callback.
    class RaceSelect(nextcord.ui.Select):
        def __init__(self, callback_func):
            self.callback_func = callback_func

            # Query the active races
            races = AsyncRace.select()                         \
                             .where(AsyncRace.active == True)  \
                             .order_by(AsyncRace.start.desc()) \
                             .limit(25)

            # Create the options list from the races
            options = []
            for r in races:
                options.append(nextcord.SelectOption(label=f"Race ID {r.id} - {r.description}", description=r.description, value=str(r.id)))

            # Initialize the base class
            super().__init__(
                placeholder="Select Race. For full active race ID list use /races command.",
                min_values=1,
                max_values=1,
                options=options)

        async def callback(self, interaction: nextcord.Interaction):
            await interaction.response.defer()
            await self.callback_func(interaction, int(interaction.data['values'][0]))

    # Discord View that displays a RaceSelect and sends the user choice to the provided callback
    class RaceSelectView(nextcord.ui.View):
        def __init__(self, callback_func):
            super().__init__(timeout=None)
            self.callback_func = callback_func
            self.race_select = AsyncHandler.RaceSelect(self.callback_func)
            self.add_item(self.race_select)

    # Select UI element that allows the user to select multiple races from a single race category. The chosen result
    # is sent to the provided callback.
    class MultiRaceSelect(nextcord.ui.Select):
        def __init__(self, callback_func, data, category_id):
            self.callback_func = callback_func
            self.user_data = data

            # Query the active races
            races = AsyncRace.select()                                                                   \
                             .where((AsyncRace.active == True) & (AsyncRace.category_id == category_id)) \
                             .order_by(AsyncRace.start.desc())                                           \
                             .limit(25)

            # Create the options list from the races
            options = []
            for r in races:
                options.append(nextcord.SelectOption(label=f"Race ID {r.id} - {r.description}", description=r.description, value=str(r.id)))

            # Initialize the base class
            super().__init__(
                placeholder="Select Races...",
                min_values=1,
                max_values=len(options),
                options=options)

        async def callback(self, interaction: nextcord.Interaction):
            await interaction.response.defer()
            await self.callback_func(interaction, self.user_data, interaction.data['values'])

    # Discord View that displays a MultiRaceSelect and sends the chosen options to the provided callback.
    class MultiRaceSelectView(nextcord.ui.View):
        def __init__(self, callback_func, data, category_id):
            super().__init__(timeout=None)
            self.callback_func = callback_func
            self.race_select = AsyncHandler.MultiRaceSelect(self.callback_func, data, category_id)
            self.add_item(self.race_select)

    ########################################################################################################################
    # Show races elements
    class LeaderboardButton(nextcord.ui.Button):
        def __init__(self, race_id, asyncHandler, style=nextcord.ButtonStyle.green, label="Leaderboard", row=0):
            super().__init__(style=style, row=row, label=label)
            self.race_id = race_id
            self.asyncHandler = asyncHandler
        async def callback(self, interaction):
            await interaction.response.defer()
            await self.asyncHandler.leaderboard_impl(interaction, self.race_id)

    class RaceInfoButton(nextcord.ui.Button):
        def __init__(self, race_id, asyncHandler, style=nextcord.ButtonStyle.blurple, label="Race Info", row=0):
            super().__init__(style=style, row=row, label=label)
            self.race_id = race_id
            self.asyncHandler = asyncHandler
        async def callback(self, interaction):
            await self.asyncHandler.show_race_info_impl(interaction, self.race_id)

    # Discord view that shows race information for a provided set of race IDs
    class ShowRacesView(nextcord.ui.View):
        def __init__(self, asyncHandler, race_id_list, page_callback=None, page_data=None, show_leaderboard_buttons=True):
            super().__init__(timeout=None)
            base_row = 0
            assert(len(race_id_list) <= 5)
            for race_id in race_id_list:
                race_info_button = AsyncHandler.RaceInfoButton(
                    race_id,
                    asyncHandler,
                    label=f"Race Info___ {race_id}",
                    row=1)
                self.add_item(race_info_button)
                leaderboard_button = AsyncHandler.LeaderboardButton(
                    race_id,
                    asyncHandler,
                    label=f"Leaderboard {race_id}",
                    row=0)
                if show_leaderboard_buttons:
                    self.add_item(leaderboard_button)
            if page_callback is not None and page_data is not None:
                prev_page_button = AsyncHandler.PrevPageButton(page_callback, page_data, row=2)
                self.add_item(prev_page_button)
                next_page_button = AsyncHandler.NextPageButton(page_callback, page_data, row=2)
                self.add_item(next_page_button)

    class NextPageButton(nextcord.ui.Button):
        def __init__(self, callback_func, data, style=nextcord.ButtonStyle.grey, label="Next Page", row=0):
            super().__init__(style=style, row=row, label=label)
            self.callback_func = callback_func
            self.data = data

        async def callback(self, interaction):
            await interaction.response.defer()
            self.data.page += 1
            await self.callback_func(interaction, self.data)

    class PrevPageButton(nextcord.ui.Button):
        def __init__(self, callback_func, data, style=nextcord.ButtonStyle.grey, label="Previous Page", row=0):
            super().__init__(style=style, row=row, label=label)
            self.callback_func = callback_func
            self.data = data

        async def callback(self, interaction):
            await interaction.response.defer()
            self.data.page -= 1
            if self.data.page <= 0:
                await interaction.followup.send("No previous pages", ephemeral=True)
            else:
                await self.callback_func(interaction, self.data)

    class NextPrevButtonView(nextcord.ui.View):
        def __init__(self, callback_func, data):
            super().__init__(timeout=None)
            prev_page_button = AsyncHandler.PrevPageButton(callback_func, data)
            self.add_item(prev_page_button)
            next_page_button = AsyncHandler.NextPageButton(callback_func, data)
            self.add_item(next_page_button)


    ########################################################################################################################
    # Discord view which contains a row of buttons for Submit/Edit submission, Forfeit and Leaderboard
    class RaceInfoButtonView(nextcord.ui.View):
        def __init__(self, asyncHandler, race_id):
            super().__init__(timeout=None)
            race = asyncHandler.get_race(race_id)
            isWeeklyAsync = race.category_id == asyncHandler.server_info.weekly_category_id
            self.submit = AsyncHandler.SubmitTimeModal(asyncHandler, race_id, isWeeklyAsync, AsyncHandler.SubmitType.SUBMIT)
            self.edit = AsyncHandler.SubmitTimeModal(asyncHandler, race_id, isWeeklyAsync, AsyncHandler.SubmitType.EDIT)
            self.ff = AsyncHandler.SubmitTimeModal(asyncHandler, race_id, isWeeklyAsync, AsyncHandler.SubmitType.FORFEIT)
            self.race_id = race_id
            self.asyncHandler = asyncHandler
            leaderboard_button = AsyncHandler.LeaderboardButton(race_id, asyncHandler)
            self.add_item(leaderboard_button)

        @nextcord.ui.button(style=nextcord.ButtonStyle.blurple, label='Submit Time')
        async def submit_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
            submission = self.asyncHandler.getSubmission(self.race_id, interaction.user.id)
            if submission is None:
                await interaction.response.send_modal(self.submit)
            else:
                await interaction.send(AlreadySubmittedMsg, ephemeral=True)

        @nextcord.ui.button(style=nextcord.ButtonStyle.grey, label='Edit Time')
        async def edit_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
            # Get the user's current submission
            submission = self.asyncHandler.getSubmission(self.race_id, interaction.user.id)
            if submission is not None:
                # Update default values using the existing submission
                self.edit.igt.default_value = submission.finish_time_igt
                self.edit.collection_rate.default_value = str(submission.collection_rate)
                self.edit.rta.default_value = submission.finish_time_rta
                self.edit.comment.default_value = submission.comment
                self.edit.next_mode.default_value = submission.next_mode

            # Send the modal
            await interaction.response.send_modal(self.edit)

        @nextcord.ui.button(style=nextcord.ButtonStyle.red, label='FF')
        async def ff_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
            submission = self.asyncHandler.getSubmission(self.race_id, interaction.user.id)
            if submission is None:
                await interaction.response.send_modal(self.ff)
            else:
                await interaction.send(AlreadySubmittedMsg, ephemeral=True)

########################################################################################################################
# Utility Functions
########################################################################################################################
    def resetPrettyTable(self):
        self.pt.set_style(DEFAULT)
        self.pt.clear()

    def isRaceCreator(self, guild, user):
        ret = False
        role = guild.get_role(self.server_info.race_creator_role)
        if role in user.roles:
            ret =  True
        return ret

    def isRaceCreatorChannel(self, channel_id):
        return channel_id == self.server_info.race_creator_channel

    # Checks that the user sending an interaction is both a race creator and sending the command from a race creator channel
    def checkRaceCreatorCommand(self, interaction):
        return self.isRaceCreator(interaction.guild, interaction.user) and self.isRaceCreatorChannel(interaction.channel_id)

    ####################################################################################################################
    # Updates the Weekly Async Submit channel with the current race info and submit/ff/leaderboard buttons.
    # NOTE: This will remove all existing messages in the submit channel
    async def add_submit_buttons(self, race=None):
        if self.server_info.weekly_submit_channel != 0:
            # Get the weekly submit channel
            weekly_submit_channel = self.bot.get_channel(self.server_info.weekly_submit_channel)
            # Remove any existing submit messages
            await weekly_submit_channel.purge()
            if race is None:
                # Add the new messages
                race_id = self.queryLatestWeeklyRaceId()
                race = self.get_race(race_id)
            else:
                race_id = race.id
            await weekly_submit_channel.send(self.getRaceInfoTable(race), embed=self.getSeedEmbed(race))
            await weekly_submit_channel.send(SubmitChannelMsg, view=AsyncHandler.RaceInfoButtonView(self, race_id))

    ####################################################################################################################
    # This function breaks a response into multiple messages that meet the Discord API character limit
    def buildResponseMessageList(self, message):
        message_list = []
        # If we're under the character limit, just send the message
        if len(message) <= DiscordApiCharLimit:
            message_list.append(message)
        else:
            # Otherwise we'll build a list of lines, then build messages from that list
            # until we hit the message limit.
            line_list = message.split("\n")
            if line_list is not None:
                curr_message = ""
                curr_message_len = 0

                for line in line_list:
                    # If adding this line would put us over the limit, add the current message to the list and start over
                    if curr_message_len + len(line) > DiscordApiCharLimit:
                        if curr_message == "":
                            logging.error("Something went wrong in buildResponseMessageList")
                            continue
                        message_list.append(curr_message)
                        curr_message = ""
                        curr_message_len = 0

                    # If this single line is > 2000 characters, break it into sentences.
                    if len(line) > DiscordApiCharLimit:
                        sentences = re.split('[.?!;]', line)
                        for s in sentences:
                            if curr_message_len + len(s) > charLimit:
                                if curr_message == "":
                                    logging.error("Something went wrong in buildmessage_listFromLines")
                                    continue
                                message_list.append(curr_message)
                                curr_message = ""
                                curr_message_len = 0
                            curr_message += s
                            curr_message_len += len(s)
                    else:
                        curr_message += line + "\n"
                        curr_message_len += len(line) + 1
                if curr_message != "":
                    message_list.append(curr_message)
        return message_list

    ####################################################################################################################
    # Queries for a race by ID, returning None if it doesn't exist. Moved to a helper function to reduce the verbose
    # try/except syntax
    def get_race(self, race_id):
        try:
            race = AsyncRace.select().where(AsyncRace.id == race_id).get()
        except:
            race = None
        return race
    
    ####################################################################################################################
    # Returns the submissions for the given race ID sorted by finish time
    def get_leaderboard(self, race):
        submissions = AsyncSubmission.select()                                  \
                                     .where(AsyncSubmission.race_id == race.id)
        return sorted(submissions, key=sort_game_time)

    ####################################################################################################################
    # Returns a string containing which numeric place (e.g. 1st, 2nd, 3rd) a user came in a specific race
    def get_place(self, race, userid):
        place = 0

        leaderboard = self.get_leaderboard(race)

        if len(leaderboard) > 0:
            for idx, s in enumerate(leaderboard):
                if s.user_id == userid:
                    place = (idx+1) # Plus one because the list is zero based but places are 1 based
        return self.get_place_str(place)

    ####################################################################################################################
    # Given a numeric place, returns the ordinal string. e.g. 1 returns "1st", 2 "2nd" etc
    def get_place_str(self, place):
        place_str = ""
        if place == 0:
            # This is an error and should never be reached, if it is might as well have some fun with it
            place_str = "Worst"
        else:
            place_str += str(place)
            tens = 0
            while (tens + 10) < place:
                tens += 10
            ones_digit = place - tens
            if ones_digit == 1:
                if tens == 10:
                    place_str += "th"
                else:
                    place_str += "st"
            elif ones_digit == 2:
                if tens == 10:
                    place_str += "th"
                else:
                    place_str += "nd"
            elif ones_digit == 3:
                if tens == 10:
                    place_str += "th"
                else:
                    place_str += "rd"
            else:
                place_str += "th"

        return place_str

    ####################################################################################################################
    # Purges all messages sent by this bot in the given channel
    async def purge_bot_messages(self, channel):
        message_list = await channel.history(limit=25).flatten()
        bot_message_list = []
        for message in message_list:
            if message.author.id == self.bot.user.id:
                await message.delete()

    ####################################################################################################################
    # Determines if an IGT or RTA time string is in the proper H:MM:SS format
    def game_time_is_valid(self, time_str):
        valid_time_str = False
        parts = time_str.split(':')
        # Hours can be left off for short seeds
        if len(parts) >= 2 and len(parts) <= 3:
            hours = 0
            minutes = -1
            seconds = -1
            try:
                seconds = int(parts[-1])
                minutes = int(parts[-2])
                hours = 0
                if len(parts) == 3:
                    hours = int(parts[0])
            except ValueError:
                valid_time_str = False
            if hours >= 0 and hours <= 24 and minutes >= 0 and minutes <= 59 and seconds >= 0 and seconds <= 59:
               valid_time_str = True
        return valid_time_str

    ####################################################################################################################
    # Assigns the weekly async racer role, which unlocks access to the spoiler channel
    async def assignWeeklyAsyncRole(self, guild, author):
        if self.server_info.weekly_race_done_role != 0:
            role = nextcord.utils.get(guild.roles, id=self.server_info.weekly_race_done_role)
            await author.add_roles(role)

    ####################################################################################################################
    # Removes the weekly async racer role from all users in the server
    async def removeWeeklyAsyncRole(self, interaction):
        if self.server_info.weekly_race_done_role != 0:
            role = nextcord.utils.get(interaction.guild.roles, id=self.server_info.weekly_race_done_role)
            for m in interaction.guild.members:
                await m.remove_roles(role)

    ####################################################################################################################
    # Queries the most recent, active weekly async race ID
    def queryLatestWeeklyRaceId(self):
        race_id = 0
        if self.server_info.weekly_category_id != 0:
            race_id =  AsyncRace.select()                                                                               \
                                .where(AsyncRace.category_id == self.server_info.weekly_category_id & AsyncRace.active) \
                                .order_by(AsyncRace.id.desc())                                                          \
                                .get()                                                                                  \
                                .id
        return race_id

    ####################################################################################################################
    # Builds the leaderboard message list for a specific race ID
    def buildLeaderboardMessageList(self, race_id):
        # Query race info
        race = self.get_race(race_id)
        race_submissions = self.get_leaderboard(race)

        if race is not None:
            leaderboardStr = ""
            if len(race_submissions) == 0:
                leaderboard_str = f'No results yet for race {race_id} ({race.description}) which started on {race.start}'
            else:
                leaderboard_str = f'Leaderboard for race {race_id} which started on {race.start}'
                leaderboard_str += f'\n    **Mode: {race.description}**'
                leaderboard_str += "\n"
                self.resetPrettyTable()
                self.pt.field_names = ["#", "Name", "IGT", "RTA", "CR"]
                for idx, submission in enumerate(race_submissions):
                    self.pt.add_row([idx+1,
                                     submission.username,
                                     submission.finish_time_igt,
                                     submission.finish_time_rta,
                                     submission.collection_rate])

            message_list = self.buildResponseMessageList(leaderboard_str)
            table_message_list = []
            if len(race_submissions) > 0:
                table_message_list = self.buildResponseMessageList(self.pt.get_string())
                for idx, msg in enumerate(table_message_list):
                    table_message_list[idx] = "`{}`".format(msg)
            return message_list + table_message_list
        else:
            return [f'No race found matching race ID {race_id}']

    ####################################################################################################################
    # Updates the weekly leaderboard channel
    async def updateLeaderboardMessage(self, race_id, guild):
        if self.server_info.weekly_leaderboard_channel != 0:
            # Remove all messages from the leaderboard channel
            leaderboard_channel = guild.get_channel(self.server_info.weekly_leaderboard_channel)
            await leaderboard_channel.purge()

            # Then build and post the latest leaderboard
            message_list = self.buildLeaderboardMessageList(race_id)
            for msg in message_list:
                await leaderboard_channel.send(msg)

    ####################################################################################################################
    # Posts an announcement about a new weekly async, pinging the weekly async role
    async def post_announcement(self, race, interaction):
        if self.server_info.announcements_channel != 0:
            announcements_channel = self.bot.get_channel(self.server_info.announcements_channel)
            ping = ""
            if self.server_info.weekly_racer_role != 0:
                role = interaction.guild.get_role(self.server_info.weekly_racer_role)
                ping = role.mention
            announcement_text = f'{ping}The new weekly async is live! Mode is: {race.description}'
            msg = await announcements_channel.send(announcement_text)

    ####################################################################################################################
    # Fetches a users display name
    async def getDisplayName(self, guild, user_id):
        member = await guild.get_member(user_id)
        return member.display_name

    ####################################################################################################################
    # Checks if the provided member is in the asyc_racers table, adds them if not
    def checkAddMember(self, member):
        racer, created = AsyncRacer.get_or_create(user_id = member.id, username = member.name, wheel_weight=1)

    ####################################################################################################################
    # Checks if the provided emoji is a poop emoji....  sigh...
    def isPoopEmoji(self, emoji):
        if str(emoji) == PoopEmoji:
            return True
        else:
            return False

    ####################################################################################################################
    # Retrieves a submission from the database based on race and user IDs. Returns None if no matching submission exists
    def getSubmission(self, race_id, user_id):
        try:
            submission = AsyncSubmission.select()                                                                           \
                                        .where((AsyncSubmission.race_id == race_id) & (AsyncSubmission.user_id == user_id)) \
                                        .get()
        except:
            submission = None
        return submission

    ####################################################################################################################
    # Creates a nicely formatted table with race info
    def getRaceInfoTable(self, race, is_race_creator=False):
        info_str = None
        if race is not None:
            info_str =      f"`| Race Id:    |` {race.id}\n"
            info_str +=     f"`| Start Date: |` {race.start}\n"
            info_str +=     f"`| Seed:       |` {race.seed}\n"
            info_str +=     f"`| Mode:       |` {race.description}\n"
            if race.additional_instructions is not None and race.additional_instructions.strip() != "":
                info_str += f"`| Add'l Info: |` {race.additional_instructions}\n"
            if is_race_creator:
                info_str += f"`| Is Active:  |` {race.active}\n"
        return info_str

    ####################################################################################################################
    # Returns an embed object containing the seed link for the provided race
    def getSeedEmbed(self, race):
        seed_embed = nextcord.Embed(title="{}".format(race.description), url=race.seed, color=nextcord.Colour.random())
        seed_embed.set_thumbnail(url="https://alttpr.com/i/logo.png")
        return seed_embed

    ####################################################################################################################
    # Submits a time to the DB
    async def submit_time(self, modal: SubmitTimeModal, interaction: nextcord.Interaction, race_id):
        logging.info('Handling submit_time')

        # First check if the race exists
        race = self.get_race(race_id)
        if race is None or not race.active:
            await interaction.send(f"Error submitting time for race {race_id}. Race doesn't exist or is not active. Please notfiy the bot overlord(s)", ephemeral=True)
            return
    
        self.checkAddMember(interaction.user)
        user_id = interaction.user.id
        igt = "23:59:59" if modal.igt.value is None else modal.igt.value
        rta = "23:59:59" if modal.rta.value is None else modal.rta.value
        cr_int = "216" if modal.collection_rate.value is None else modal.collection_rate.value
        comment = modal.comment.value
        next_mode = modal.next_mode.value

        parse_error = not self.game_time_is_valid(igt)
        if not parse_error:
            parse_error = not self.game_time_is_valid(rta)
    
        if parse_error:
            await interaction.send("IGT or RTA is in the wrong format", ephemeral=True)
            return
    
        # Add a zero in the hour place if it's missing in IGT and RTA
        if len(igt.split(':')) == 2:
            igt = "0:" + igt
    
        if rta is not None and len(rta.split(':')) == 2:
            rta = "0:" + rta
    
        submission = self.getSubmission(race_id, user_id)
        if submission is None:
            # Create a brand new submission
            submission = AsyncSubmission(race_id= race_id, user_id= user_id, username= interaction.user.name, finish_time_igt= igt, collection_rate= cr_int, finish_time_rta=rta, comment=comment, next_mode=next_mode)
        else:
            # Update the fields of the existing submission
            submission.finish_time_igt= igt
            submission.collection_rate= cr_int
            submission.finish_time_rta=rta
            submission.comment=comment
            submission.next_mode=next_mode

        submission.submit_date = datetime.now().isoformat(timespec='minutes').replace('T', ' ')
        submission.save()
        await interaction.send("Submission complete", ephemeral=True)
    
        # Finally update the leaderboard if this is for the current weekly async
        if race_id == self.queryLatestWeeklyRaceId():
            await self.updateLeaderboardMessage(race_id, interaction.guild)

########################################################################################################################
# DASH
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Go ahead, see what happens when you try to go fast")
    async def dash(self, interaction):
        logging.info('Executing dash command')
        await interaction.send("!!!!BONK!!!!")

########################################################################################################################
# RACE_RESULTS
########################################################################################################################
    class RaceResultsData():
        def __init__(self, page, user_id):
            self.page = page
            self.user_id = user_id

    @nextcord.slash_command(guild_ids=SupportedServerList, description="Show Race Results for a User")
    async def race_results(self,
                           interaction,
                           user: nextcord.User = nextcord.SlashOption(description="User to view races for", required=False)):
        
        logging.info('Executing race_results command')
        await interaction.response.defer()
        if user is None:
            user = interaction.user
        self.checkAddMember(user)
        await self.race_results_impl(interaction, AsyncHandler.RaceResultsData(1, user.id))

    ####################################################################################################################
    # Displays race submissions for the given user_id
    async def race_results_impl(self, interaction, data):
        query_results = AsyncSubmission.select()                                       \
                                       .where(AsyncSubmission.user_id == data.user_id) \
                                       .order_by(AsyncSubmission.id.desc()) \
                                       .paginate(data.page, ItemsPerPage)

        latest_weekly_id = self.queryLatestWeeklyRaceId()
        if len(query_results) > 0:
            self.resetPrettyTable()
            self.pt.hrules = True
            self.pt.field_names = ["Race ID", "Submission ID", "Date", "Place", "IGT", "Collection Rate", "RTA", "Mode", "Comment"]
            self.pt._max_width = {"Mode": 50}
            race_id_list = []
            for result in query_results:
                # First find info about the race this submission is for
                race_id = result.race_id
                race_id_list.append(race_id)
                race = self.get_race(race_id)
                date        = result.submit_date
                mode        = race.description if race is not None else ""
                igt         = result.finish_time_igt
                cr          = result.collection_rate
                rta         = result.finish_time_rta
                submit_id   = result.id
                place       = self.get_place(race, data.user_id)
                comment     = result.comment if result.comment is not None else ""

                if rta is None: rta = ""

                # Hide completion info if this is the current weekly async
                if race_id == latest_weekly_id:
                    igt = "**:**:**"
                    rta = "**:**:**"
                    cr = "***"
                    place = "****"
                self.pt.add_row([race_id, submit_id, date, place, igt, cr, rta, mode, comment])

            total_submissions = AsyncSubmission.select(fn.COUNT(AsyncSubmission.id)).where(AsyncSubmission.user_id == data.user_id).get()
            await interaction.followup.send(f"Recent Async Submissions, page {data.page}:", ephemeral=True)
            table_message_list = self.buildResponseMessageList(self.pt.get_string())
            for table_message in table_message_list:
                await interaction.followup.send(f"`{table_message}`", ephemeral=True)
            await interaction.followup.send(view=AsyncHandler.ShowRacesView(self, race_id_list, self.race_results_impl, data), ephemeral=True)
        else:
            await interaction.followup.send("There are no submissions in that range", ephemeral=True)

########################################################################################################################
# LEADERBOARD
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Show Race Leaderboard")
    async def leaderboard(self,
                          interaction,
                          race_id: int = nextcord.SlashOption(
                            description="Race ID to view leaderboard of",
                            required=False,
                            min_value=1)):

        logging.info('Executing leaderboard command')
        await interaction.response.defer()
        self.checkAddMember(interaction.user)
        # If no race ID was provided, prompt the user to select one
        if race_id is None:
            race_select_view = AsyncHandler.RaceSelectView(self.leaderboard_impl)
            await interaction.followup.send(view=race_select_view, ephemeral=True)
        else:
            await self.leaderboard_impl(interaction, race_id)

    ####################################################################################################################
    # Does the actual work for the leaderboard command, moved to a separate function to be reusable with buttons
    async def leaderboard_impl(self, interaction, race_id):
        # check if the user has permission to view the leaderboard. They have permission if they submitted to it or have appropriate role
        can_view = self.isRaceCreator(interaction.guild, interaction.user) or self.getSubmission(race_id, interaction.user.id) is not None
        # Make sure this race exists
        try:
            race = AsyncRace.select()                       \
                            .where(AsyncRace.id == race_id) \
                            .get()
        except:
            race = None

        if race is not None and can_view:
            message_list = self.buildLeaderboardMessageList(race_id)
            for message in message_list:
                await interaction.followup.send(message, ephemeral=True)
        elif can_view:
            await interaction.send(f"Invalid Race ID: {race_id}", ephemeral=True)
        else:
            await interaction.send(f"You must submit a time or FF from the race before viewing the leaderboard", ephemeral=True)

########################################################################################################################
# RACES
########################################################################################################################
    class RacesData():
        def __init__(self, page, category):
            self.page = page
            self.category = category

    @nextcord.slash_command(guild_ids=SupportedServerList, description="Show Current Races")
    async def races(self, interaction):
        logging.info('Executing races command')
        await interaction.response.defer()
        await interaction.followup.send(view=AsyncHandler.CategorySelectView(self.races_first_impl, 1), ephemeral=True)

    ########################################################################################################################
    async def races_first_impl(self, interaction, category_id, page):
        await self.races_impl(interaction, AsyncHandler.RacesData(page=page, category=category_id))

    ########################################################################################################################
    # Implementation of the races command, moved to separate function to be able to reuse
    async def races_impl(self, interaction, data):
        self.checkAddMember(interaction.user)
        is_race_creator = self.isRaceCreator(interaction.guild, interaction.user)

        races = None
        if is_race_creator:
            races = AsyncRace.select()                                      \
                             .where(AsyncRace.category_id == data.category) \
                             .order_by(AsyncRace.id.desc())                 \
                             .paginate(data.page, ItemsPerPage)
        else:
            races = AsyncRace.select()                                                                     \
                             .where((AsyncRace.category_id == data.category) & (AsyncRace.active == True)) \
                             .order_by(AsyncRace.id.desc())                                                \
                             .paginate(data.page, ItemsPerPage)
        
        if races is not None and len(races) > 0:
            self.resetPrettyTable()
            
            if is_race_creator:
                self.pt.field_names = ["ID", "Start Date", "Mode", "Active"]
            else:
                self.pt.field_names = ["ID", "Start Date", "Mode"]

            self.pt._max_width = {"Mode": 50}
            self.pt.align["Mode"] = "l"

            race_id_list = []
            for race in races:
                race_id_list.append(race.id)
                if is_race_creator:
                    self.pt.add_row([race.id, race.start, race.description, race.active])
                else:
                    self.pt.add_row([race.id, race.start, race.description])
            message = self.pt.get_string()
            await interaction.send(f"`{message}`", view=AsyncHandler.ShowRacesView(self,
                                                                                   race_id_list,
                                                                                   self.races_impl,
                                                                                   data,
                                                                                   False), ephemeral=True)
        else:
            await interaction.send("No races found in that range", ephemeral=True)

########################################################################################################################
# RACE_INFO
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Show info for past weekly async races")
    async def race_info(self,
                        interaction,
                        race_id: int = nextcord.SlashOption(
                          description="Race ID to view race info for",
                          required=False,
                          min_value=1)):
        logging.info("Executing race_info command")
        await interaction.response.defer()
        self.checkAddMember(interaction.user)

        # If no race ID was provided, prompt the user to select one
        if race_id is None:
            race_select_view = AsyncHandler.RaceSelectView(self.show_race_info_impl)
            await interaction.send(view=race_select_view, ephemeral=True)
        else:
            await self.show_race_info_impl(interaction, race_id)

    ########################################################################################################################
    # Does the work of showing a race
    async def show_race_info_impl(self, interaction, race_id):
        try:
            race = AsyncRace.select()                       \
                            .where(AsyncRace.id == race_id) \
                            .get()
        except:
            race = None
        if race is None:
            interaction.send(f"No race found for ID {race_id}", ephemeral=True)
        else:
            message = self.getRaceInfoTable(race)
            await interaction.send(message, embed=self.getSeedEmbed(race))
            race_info_view = AsyncHandler.RaceInfoButtonView(self, race_id)
            await interaction.followup.send(f"Click below to submit/edit or view leaderboard for race {race_id}", view=race_info_view)


########################################################################################################################
########################################################################################################################
######################    RACE CREATOR COMMANDS    #####################################################################
########################################################################################################################
########################################################################################################################

########################################################################################################################
# ADD_RACE
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Add Async Race")
    async def add_race(
        self,
        interaction,
        start_race: int = nextcord.SlashOption(description="Start the race immediately?", choices={"Yes": True, "No": False})):

        logging.info('Executing add_race command')
        await interaction.response.defer()

        if self.checkRaceCreatorCommand(interaction):
            add_race_modal = AsyncHandler.AddRaceModal()
            if start_race:
                add_race_modal.start_race_callback = self.start_race_impl
            add_race_view = AsyncHandler.AddRaceView(add_race_modal)
            await interaction.followup.send(view=add_race_view, ephemeral=True)
        else:
            await interaction.followup.send(NoPermissionMsg, ephemeral=True)

########################################################################################################################
# EDIT_RACE
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Edit Async Race")
    async def edit_race(self, interaction, race_id: int):
        logging.info('Executing edit_race command')

        if not self.checkRaceCreatorCommand(interaction):
            await interaction.response.send(NoPermissionMsg, ephemeral=True)
            return

        race = self.get_race(race_id)
        if race is not None:
            add_race_modal = AsyncHandler.AddRaceModal(race=race)
            add_race_modal.mode.default_value = race.description
            add_race_modal.seed.default_value = race.seed
            add_race_modal.instructions.default_value = race.additional_instructions
            await interaction.response.send_modal(add_race_modal)
        else:
            await interaction.followup.send(f"Race ID {race_id} not found", ephemeral=True)

########################################################################################################################
# START_RACE
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Start Async Race")
    async def start_race(self,
                         interaction,
                         race_id: int = nextcord.SlashOption(
                            description="Race to Start",
                            required=False)):
        logging.info('Executing start_race command')
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.followup.send(NoPermissionMsg, ephemeral=True)
            return

        if race_id is not None:
            await interaction.response.defer()
            await self.start_race_impl(interaction, race_id)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.start_race_impl)
            await interaction.send(view=race_select_view, ephemeral=True)

    ########################################################################################################################
    # Starts a race
    async def start_race_impl(self, interaction, race_id):
        start_date = date.today().isoformat()
        race = self.get_race(race_id)
        if race is not None:
            race.start = start_date
            race.active = True
            race.save()
            await interaction.followup.send(f"Started race {race.id}")
            if race.category_id == self.server_info.weekly_category_id:
                await self.add_submit_buttons(race)
                await self.updateLeaderboardMessage(race.id, interaction.guild)
                await self.removeWeeklyAsyncRole(interaction)
                await self.post_announcement(race, interaction)
        else:
            await interaction.followup.send(f"No race found for race ID {race_id}", ephemeral=True)

########################################################################################################################
# END_RACE
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="End Async Race (Mark as Inactive)")
    async def end_race(self,
                         interaction,
                         race_id: int = nextcord.SlashOption(
                            description="Race to End",
                            required=False)):
        logging.info('Executing start_race command')
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.followup.send(NoPermissionMsg, ephemeral=True)
            return

        if race_id is not None:
            await self.end_race_impl(interaction, race_id)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.end_race_impl)
            await interaction.send(view=race_select_view, ephemeral=True)

    ########################################################################################################################
    # Ends a race
    async def end_race_impl(self, interaction, race_id):
        race = self.get_race(race_id)
        if race is not None:
            race.active = False
            race.save()
            await interaction.followup.send(f"Ended race {race.id}")
        else:
            await interaction.followup.send(f"No race found for race ID {race_id}", ephemeral=True)

########################################################################################################################
# REMOVE_RACE
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Remove Async Race")
    async def remove_race(self, interaction, race_id: int):
        logging.info('Executing remove_race command')

        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        race = self.get_race(race_id)
        if race is not None:
            # Check first to see if there are any submissions to this race
            try:
                submissions = AsyncSubmission.select().where(AsyncSubmission.race_id == race.id).get()
            except:
                submissions = None
            if submissions is not None:
                await interaction.send("This race has user submissions and cannot be removed via command, please contact the bot overlord to remove it.", ephemeral=True)
            else:
                confirm_view = AsyncHandler.YesNoView(self.remove_race_impl, race)
                await interaction.send(view=confirm_view, ephemeral=True)
        else:
            await interaction.send(f"Race ID {race_id} does not exist", ephemeral=True)

    ########################################################################################################################
    # Callback used by confirmation selection to do the work of removing the race
    async def remove_race_impl(self, interaction, user_confirmed, race):
        if user_confirmed:
            await interaction.send(f"Removing race {race.id}")
            race.delete_instance()
        else:
            await interaction.send("Remove cancelled")

########################################################################################################################
# ADD_CATEGORY
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Add async race category")
    async def add_category(self, interaction, name, description):
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        new_category = RaceCategory()
        new_category.name = name
        new_category.description = description
        new_category.save()
        await interaction.send(f"Created race category {new_category.name} with ID {new_category.id}")

########################################################################################################################
# NEXT_MODE_SUGGESTIONS
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Show suggestions for next mode from users who completed the most recent weekly asyncs")
    async def next_mode_suggstions(self, interaction):
        logging.info('Executing next_mode_suggstions command')
        await interaction.response.defer()

        racers = AsyncRacer.select()
        # Query the most recent weekly races
        recent_races = AsyncRace.select()                                                                                           \
                                .where((AsyncRace.category_id == self.server_info.weekly_category_id) & (AsyncRace.active == True)) \
                                .order_by(AsyncRace.start.desc())

        wheel_list = ["**Name** > **Mode Suggestion**\n"]
        for r in racers:
            # Query mode suggestions for this user, we will query each of the two most recent weekly async races. If the user has not completed
            # either async then the query will return None
            try:
                submission1 = AsyncSubmission.select()                                                                                        \
                                             .where((AsyncSubmission.race_id == recent_races[0].id) & (AsyncSubmission.user_id == r.user_id)) \
                                             .get()
            except:
                submission1 = None
            try:
                submission2 = AsyncSubmission.select()                                                                                        \
                                             .where((AsyncSubmission.race_id == recent_races[1].id) & (AsyncSubmission.user_id == r.user_id)) \
                                             .get()
            except:
                submission2 = None
            if submission1 is not None and submission1.next_mode is not None and submission1.next_mode != "":
                next_mode_str = submission1.next_mode.strip().replace('\n', ' ')
                if next_mode_str != "None":
                    wheel_list.append(f"{r.username} > {next_mode_str}")

            if submission2 is not None and submission2.next_mode is not None and submission2.next_mode != "":
                next_mode_str = submission2.next_mode.strip().replace('\n', ' ')
                if next_mode_str != "None":
                    wheel_list.append(f"{r.username} > {next_mode_str}")

        await interaction.followup.send('\n'.join(wheel_list), ephemeral=True)

########################################################################################################################
# MOD_UTIL
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Mod Utilities")
    async def mod_util(self,
                      interaction,
                      function: int = nextcord.SlashOption(
                            description="Utility Function to Run",
                            choices = { "Force Update Leaderboard Channel": 1, "Toggle TP": 2})):

        if not self.checkRaceCreatorCommand(interaction.guild):
            await interaction.response.send(NoPermissionMsg, ephemeral=True)
            return

        logging.info('Executing mod_util command')
        if function == 1:
            await self.updateLeaderboardMessage(self.queryLatestWeeklyRaceId(), ctx.guild)
            await interaction.response.send("Updated weekly leaderboard channel", ephemeral=True)
        elif function == 2:
            self.replace_poop_with_tp = not self.replace_poop_with_tp
            await interaction.response.send("Toilet paper replacement is now {}".format("Enabled" if self.replace_poop_with_tp else "Disabled"), ephemeral=True)

########################################################################################################################
# PARROT
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Bot want a cracker")
    async def parrot(self,
                     interaction,
                     text: str = nextcord.SlashOption(description="Text"),
                     channel: nextcord.abc.GuildChannel = nextcord.SlashOption(
                         description="Channel")):

        # If the user is authorized, have the bot post a message with the provided text in the indicated channel
        if interaction.user.id not in config.CoolestGuyIds:
            await interaction.response.send(NoPermissionMsg, ephemeral=True)
            return

        logging.info('Executing parrot command')
        await channel.send(text)
        await interaction.send("Done")

########################################################################################################################
# EDIT_SUBMISSION
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Edit User Submission")
    async def edit_submission(self, interaction, submission_id: int):
        logging.info('Executing edit_submission command')

        try:
            submission_to_edit = AsyncSubmission.select().where(AsyncSubmission.id == submission_id).get()
        except:
            submission_to_edit = None

        if submission_to_edit is None:
            await interaction.send(f"No submission found with ID {submission_id}", ephemeral=True)
            return

        is_race_creator = self.isRaceCreator(interaction.guild, interaction.user)
        if is_race_creator or submission_to_edit.user_id == interaction.user.id:
            race = self.get_race(submission_to_edit.race_id)
            submit_time_modal = AsyncHandler.SubmitTimeModal(self,
                                                             race.id,
                                                             (race.category_id == self.server_info.weekly_category_id),
                                                             AsyncHandler.SubmitType.EDIT)
            submit_time_modal.igt.default_value = submission_to_edit.finish_time_igt
            submit_time_modal.collection_rate.default_value = str(submission_to_edit.collection_rate)
            submit_time_modal.rta.default_value = submission_to_edit.finish_time_rta
            submit_time_modal.comment.default_value = submission_to_edit.comment
            submit_time_modal.next_mode.default_value = submission_to_edit.next_mode
            await interaction.response.send_modal(submit_time_modal)

            await interaction.followup.send(f"Updated submission ID {submission_id}", ephemeral=True)
        else:
            interaction.send("You don't have permission. Only race creators can edit other users' submissions", ephemeral=True)

########################################################################################################################
# PIN RACE INFO
########################################################################################################################
    @nextcord.slash_command(guild_ids=SupportedServerList, description="Pins race info for a set of races in a specific channel")
    async def pin_race_info(self,
                            interaction,
                            channel: nextcord.abc.GuildChannel = nextcord.SlashOption(
                                description="Channel to pin the race info in")):
        logging.info("Executing pin_race_info command")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        await interaction.response.defer()
        # Send Select to choose which category
        await interaction.followup.send(view=AsyncHandler.CategorySelectView(self.pin_race_info_get_races, channel), ephemeral=True)

    ########################################################################################################################
    async def pin_race_info_get_races(self, interaction, category_id, channel):
        await interaction.response.defer()
        # Verify this category has active races to pin
        try:
            races = AsyncRace.select()                                                                   \
                             .where((AsyncRace.category_id == category_id) & (AsyncRace.active == True)) \
                             .get()
        except:
            races = None

        if races is not None:
            # Send Select to choose which races to pin
            await interaction.followup.send(view=AsyncHandler.MultiRaceSelectView(self.pin_race_info_impl, channel, category_id), ephemeral=True)
        else:
            await interaction.followup.send("There are no active races for that category")

    ########################################################################################################################
    async def pin_race_info_impl(self, interaction, channel, user_race_choices):
        await interaction.followup.send("Removing old pinned race messages")
        await self.purge_bot_messages(channel)
        await interaction.followup.send("Adding new race messages")
        for c in user_race_choices:
            race_id = int(c)
            race = self.get_race(race_id)
            await channel.send(self.getRaceInfoTable(race), embed=self.getSeedEmbed(race))
            await channel.send(view=AsyncHandler.RaceInfoButtonView(self, race_id))
            await channel.send("`------------------------------------------------------------------------`")
        await interaction.followup.send("Done")

########################################################################################################################
# ON_MESSAGE
########################################################################################################################
    @commands.Cog.listener("on_message")
    async def message_handler(self, message):
        if message.author == self.bot.user:
            return

        # Whenever a user mentions pendant pod, add Lao's emoji
        if "pendant pod" in message.content.lower():
            logging.info("adding pendant pod emoji")
            guild = self.bot.get_guild(self.server_info.server_id)
            emoji = None
            for e in guild.emojis:
                if str(e) == PendantPodEmoteStr:
                    emoji = e
            if emoji is not None:
                await message.add_reaction(emoji)

########################################################################################################################
# STARTUP and SHUTDOWN
########################################################################################################################
    @commands.Cog.listener("on_ready")
    async def on_ready_handler(self):
        logging.info("Async Handler Ready")
        if self.test_mode:
            logging.info("  Running in test mode")
        await self.add_submit_buttons()

    async def close(self):
        logging.info("Shutting down Async Handler")
        # Remove any existing submit messages/buttons in the weekly and tourney submit channels. Async messages pinned
        # in other channels will be orphaned
        if self.server_info.weekly_submit_channel != 0:
            weekly_submit_channel = self.bot.get_channel(self.server_info.weekly_submit_channel)
            await self.purge_bot_messages(weekly_submit_channel)
        if self.server_info.tourney_submit_channel != 0:
            tourney_channel = self.bot.get_channel(self.server_info.tourney_submit_channel)
            await self.purge_bot_messages(tourney_channel)

########################################################################################################################
# REACTION ADD HANDLER
########################################################################################################################
    @commands.Cog.listener("on_raw_reaction_add")
    async def reaction_add_handler(self, payload):
        # There was a time that a server was being inundated by poop emojis on nearly every message. In an effort to
        # dissuade this behavior this functionality was added to remove the poop emoji and replace it with a
        # toilet paper one.
        if self.replace_poop_with_tp:
            if self.isPoopEmoji(payload.emoji):
                logging.info("Cleaning up some poop")
                guild = self.bot.get_guild(payload.guild_id)
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, payload.member)
                await message.add_reaction(ToiletPaperEmoji)


def setup(bot):
    bot.add_cog(AsyncHandler(bot))
