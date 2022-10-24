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
import config

# Discord limit is 2000 characters, subtract a few to account for formatting, newlines, etc
DiscordApiCharLimit = 2000 - 10
ItemsPerPage = 5

# We use certain emojis and it's easier to refer to a variable name than use the emoji itself, particularly for the user specific ones
ThumbsUpEmoji = '👍'
ThumbsDownEmoji = '👎'

# Define some canned messages that are used in multiple places by some bot features
AlreadySubmittedMsg = "You've already submitted for this race, use the 'Edit Time' button to modify your submission"
NoPermissionMsg = "You do not have permissions to use this command in this channel"
SubmitChannelMsg = "Click below to submit/edit a time or FF from this week's race. Once you've submitted a time you can view the leaderboard."
SelfEditNoPermission = "Editing of assigned async race submissions is not allowed. Contact a race creator (mod) to edit"

DnfTime = "23:59:59"

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
    if game_time is not None and game_time != '':
        parts = game_time.split(':')
        hours = 0
        mins = 0
        sec = 0
        if len(parts) == 3:
            hours = int(parts[0])
            min = int(parts[1])
            sec = int(parts[2])
        else:
            min = int(parts[0])
            sec = int(parts[1])
        ret = (3600 * hours) + (60 * min) + sec
    return ret

class AsyncHandler(commands.Cog, name='AsyncRaceHandler'):
    '''Cog which handles commands related to Async Races.'''

    def __init__(self, bot):
        self.bot = bot
        self.test_mode = False
        # Once server info is defined, it should be set here as follows:
        self.server_info = config.PRODUCTION_SERVER
        if config.TEST_MODE:
            self.setTestMode()
        self.pt = PrettyTable()
        self.resetPrettyTable()

    def setTestMode(self):
        self.test_mode = True
        self.server_info = config.TEST_SERVER

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
            self.user_id = None

            self.igt = nextcord.ui.TextInput(
                label="Enter IGT in format `H:MM:SS`",
                required=(not config.RtaIsPrimary))

            self.rta = nextcord.ui.TextInput(
                label="Enter RTA in format `H:MM:SS`",
                required=(config.RtaIsPrimary))

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

            self.vod_link = nextcord.ui.TextInput(
                    label="VoD Link",
                    required=True,
                    min_length=1,
                    max_length=1024)

            if submitType is not AsyncHandler.SubmitType.FORFEIT:
                if config.RtaIsPrimary:
                    self.add_item(self.rta)
                    if config.ShowSecondaryTimeField:
                        self.add_item(self.igt)
                else:
                    self.add_item(self.igt)
                    if config.ShowSecondaryTimeField:
                        self.add_item(self.rta)
                self.add_item(self.collection_rate)

            self.add_item(self.comment)
            if isWeeklyAsync and config.SuggestNextWeeklyMode:
                self.add_item(self.next_mode)
            if not self.asyncHandler.is_public_race(race_id):
                self.add_item(self.vod_link)

        async def callback(self, interaction: nextcord.Interaction) -> None:
            await self.asyncHandler.submit_time(self, interaction, self.race_id)
            if self.asyncHandler.queryLatestWeeklyRaceId() == self.race_id:
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
            self.category_id = None if race is None else race.category_id

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
                logging.info(f"Adding category {c.name}")
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
        def __init__(self, callback_func, userdata):
            self.callback_func = callback_func
            self.userdata = userdata

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
            if self.userdata is None:
                await self.callback_func(interaction, int(interaction.data['values'][0]))
            else:
                await self.callback_func(interaction, int(interaction.data['values'][0]), self.userdata)

    # Discord View that displays a RaceSelect and sends the user choice to the provided callback
    class RaceSelectView(nextcord.ui.View):
        def __init__(self, callback_func, userdata=None):
            super().__init__(timeout=None)
            self.callback_func = callback_func
            self.race_select = AsyncHandler.RaceSelect(self.callback_func, userdata)
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
            self.data.page += 1
            await self.callback_func(interaction, self.data)

    class PrevPageButton(nextcord.ui.Button):
        def __init__(self, callback_func, data, style=nextcord.ButtonStyle.grey, label="Previous Page", row=0):
            super().__init__(style=style, row=row, label=label)
            self.callback_func = callback_func
            self.data = data

        async def callback(self, interaction):
            self.data.page -= 1
            if self.data.page <= 0:
                await interaction.send("No previous pages", ephemeral=True)
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
                # Only allow edits of public races
                if self.asyncHandler.is_public_race(submission.race_id):
                    # Update default values using the existing submission
                    self.edit.igt.default_value = submission.finish_time_igt
                    self.edit.collection_rate.default_value = str(submission.collection_rate)
                    self.edit.rta.default_value = submission.finish_time_rta
                    self.edit.comment.default_value = submission.comment
                    self.edit.next_mode.default_value = submission.next_mode
                else:
                    await interaction.send(SelfEditNoPermission, ephemeral=True)
                    return

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
########################################################################################################################
# Utility Functions
########################################################################################################################
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
        is_race_creator = self.isRaceCreator(interaction.guild, interaction.user)
        logging.info(f"User is race creator: {is_race_creator}")
        return is_race_creator and self.isRaceCreatorChannel(interaction.channel_id)

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
            started_on_str = f"which started on {race.start}"
            if len(race_submissions) == 0:
                leaderboard_str = f'No results yet for race {race_id} ({race.description}) '
                if self.is_public_race(race_id):
                    leaderboard_str += started_on_str
            else:
                leaderboard_str = f'Results for race {race_id} '
                if self.is_public_race(race_id):
                    leaderboard_str += started_on_str
                leaderboard_str += f'\n    **Mode: {race.description}**'
                leaderboard_str += "\n"
                self.resetPrettyTable()
                if config.ShowSecondaryTimeField:
                    self.pt.field_names = ["#", "Name", "IGT", "RTA", "CR"]
                else:
                    if config.RtaIsPrimary:
                        self.pt.field_names = ["#", "Name", "RTA", "CR"]
                    else:
                        self.pt.field_names = ["#", "Name", "IGT", "CR"]
                for idx, submission in enumerate(race_submissions):
                    rowNum = idx+1
                    igt_str = "DNF" if submission.finish_time_igt == DnfTime else submission.finish_time_igt
                    rta_str = "DNF" if submission.finish_time_rta == DnfTime else submission.finish_time_rta
                    if config.ShowSecondaryTimeField:
                        self.pt.add_row([rowNum, submission.username, igt_str, rta_str, submission.collection_rate])
                    else:
                        if config.RtaIsPrimary:
                            self.pt.add_row([rowNum, submission.username, rta_str, submission.collection_rate])
                        else:
                            self.pt.add_row([rowNum, submission.username, igt_str, submission.collection_rate])

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
            info_str =      f"`| Race Id:         |` {race.id}\n"
            info_str +=     f"`| Start Date:      |` {race.start}\n"
            info_str +=     f"`| Seed:            |` {race.seed}\n"
            info_str +=     f"`| Mode:            |` {race.description}\n"
            if race.additional_instructions is not None and race.additional_instructions.strip() != "":
                info_str += f"`| Add'l Info:      |` {race.additional_instructions}\n"
            # For assigned races, include the currently assigned racers
            if not self.is_public_race(race.id):
                roster = self.get_roster(race.id)
                roster_str = f"`| Assigned Racers: |`"
                first = True
                for r in roster:
                    user = self.get_user(r.user_id)
                    started = "" if r.race_info_time is None else " *[started]*"
                    started = started if self.getSubmission(r.race_id, r.user_id) is None else " *[submitted]*"
                    if user is not None:
                        if first:
                            first = False
                        else:
                            roster_str += "`|                  |`"
                        roster_str += f" {user.username}{started}\n"
                info_str += f"{roster_str}"
            if is_race_creator:
                info_str += f"`| Is Active:       |` {race.active}\n"
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

        user = interaction.user if modal.user_id is None else self.get_user(modal.user_id)

        # Then check if the user has permission to submit to this race
        if user is not None and self.has_permission(race_id, user.id):
            self.checkAddMember(user)
            user_id = user.id
            igt = "" if modal.igt.value is None else modal.igt.value
            rta = "" if modal.rta.value is None else modal.rta.value
            cr_int = "216" if modal.collection_rate.value is None else modal.collection_rate.value
            comment = modal.comment.value
            next_mode = modal.next_mode.value
            vod_link = modal.vod_link.value

            # A parse_error occurred if a required time is missing or an invalid non-empty time is submitted
            parse_error = False
            if config.RtaIsPrimary:
                if rta == "":
                    await interaction.send("Missing required RTA time", ephemeral=True)
                    return
            else:
                if igt == "":
                    await interaction.send("Missing required RTA time", ephemeral=True)
                    return

            parse_error = not self.game_time_is_valid(igt)
            rta_parse_error = not self.game_time_is_valid(rta)
                
            if igt != "" and not self.game_time_is_valid(igt):
                await interaction.send("IGT is in the wrong format", ephemeral=True)
                return

            if rta != "" and not self.game_time_is_valid(rta):
                await interaction.send("RTA is in the wrong format", ephemeral=True)
                return
        
            # Add a zero in the hour place if it's missing in IGT and RTA
            if igt is not None and len(igt.split(':')) == 2:
                igt = "0:" + igt
            if rta is not None and len(rta.split(':')) == 2:
                rta = "0:" + rta

            submission = self.getSubmission(race_id, user_id)
            if submission is None:
                # Create a brand new submission
                submission = AsyncSubmission(race_id= race_id, user_id= user_id, username= user.name,
                                             finish_time_igt= igt, collection_rate= cr_int, finish_time_rta=rta,
                                             comment=comment, next_mode=next_mode, vod_link=vod_link)
            else:
                # Update the fields of the existing submission
                submission.finish_time_igt= igt
                submission.collection_rate= cr_int
                submission.finish_time_rta=rta
                submission.comment=comment
                submission.next_mode=next_mode
                submission.vod_link = vod_link

            submission.submit_date = datetime.now().isoformat(timespec='minutes').replace('T', ' ')
            submission.save()
            await interaction.send("Submission complete", ephemeral=True)

            # Check if this submission completes the race
            if not self.is_public_race(race_id):
                is_race_complete = self.is_race_complete(race)
                # If all racers have now submitted, post the race results
                if is_race_complete:
                    logging.info(f"race complete, posting results")
                    await self.post_results(race)

            # Finally update the leaderboard if this is for the current weekly async
            if race_id == self.queryLatestWeeklyRaceId():
                await self.updateLeaderboardMessage(race_id, interaction.guild)
        else:
            await interaction.send("You are not assigned to this async race, submission cancelled")

    ####################################################################################################################
    # Checks if a race is complete. For assigned races, it is complete when all racers have submitted. For public races,
    # a race is complete when it is no longer active
    def is_race_complete(self, race):
        if race is not None:
            is_race_complete = True
            if self.is_public_race(race.id):
                is_race_complete = not race.active
            else:
                # Query for the race roster
                roster = self.get_roster(race.id)
                # For each assigned racer see if there's a submission
                for r in roster:
                    if self.getSubmission(race.id, r.user_id) is None:
                        # if anyone has not submitted, the race is not complete
                        is_race_complete = False
                        break
        else:
            is_race_complete = False
        return is_race_complete

    ####################################################################################################################
    # Returns a list of racers assigned to the provided race_id, or None if no racers are assigned
    def get_roster(self, race_id):
        roster = RaceRoster.select()                             \
                           .where(RaceRoster.race_id == race_id)
        if roster is None or len(roster) == 0:
            roster = None
        return roster

    ####################################################################################################################
    # Returns the race roster assignment row for this race ID/User ID combo, or None if it doesn't exist
    def get_assignment(self, race_id, user_id):
        try:
            assignment = RaceRoster.select()                                                                              \
                                   .where((RaceRoster.race_id == race_id) & (RaceRoster.user_id == user_id)) \
                                   .get()
        except:
            assignment = None
        return assignment

    ####################################################################################################################
    # Returns True if the provided race_id is a public race (has no assigned racers), False otherwise
    def is_public_race(self, race_id):
        roster = self.get_roster(race_id)
        return (roster is None)

    ####################################################################################################################
    # Retrieves a user by ID from the database
    def get_user(self, user_id):
        try:
            user = AsyncRacer.select().where(AsyncRacer.user_id == user_id).get()
        except:
            user = None
        return user

    ####################################################################################################################
    # Posts the results of the provided race
    async def post_results(self, race):
        # Add a FF for any missing racer info
        roster = self.get_roster(race.id)
        users = []
        for r in roster:
            user = self.get_user(r.user_id)
            users.append(user)
            s = self.getSubmission(race.id, r.user_id)
            if s is None:
                submission = AsyncSubmission(race_id= race.id, user_id= r.user_id, username= user.username, finish_time_igt= DnfTime, collection_rate= 216, finish_time_rta=DnfTime, comment=None, next_mode=None)
                submission.save()
        # Post leaderboard to async channel
        async_channel = self.bot.get_channel(self.server_info.tourney_async_channel)
        message_list = self.buildLeaderboardMessageList(race.id)
        for message in message_list:
            await async_channel.send(message)
        # Ping assigned racers
        ping_msg = ""
        guild = self.bot.get_guild(self.server_info.server_id)
        if config.PingRaceCreatorOnRaceEnd:
            role = guild.get_role(self.server_info.race_creator_role)
            ping_msg += f"{role.mention} "
        for u in users:
            member = guild.get_member(u.user_id)
            ping_msg += f"{member.mention} "
        await async_channel.send(ping_msg)

    ####################################################################################################################
    # Returns True if all assigned racers for the given race_id have submmissions, or if the race is public
    def is_race_complete(self, race_id):
        race_complete = True
        if not self.is_public_race(race_id):
            roster = self.get_roster(race_id)
            for r in roster:
                try:
                    s = AsyncSubmission.select().where(AsyncSubmission.race_id == race_id & AsyncSubmission.user_id == r.user_id).get()
                except:
                    s = None
                if s is None:
                    race_complete = False
                    break
        return race_complete

    ####################################################################################################################
    # Pings assigned racers and gives instructions on how to get seed and submit time for an async race
    async def notify_assigned_racers(self, race_id):
        guild = self.bot.get_guild(self.server_info.server_id)
        async_channel = guild.get_channel(self.server_info.tourney_async_channel)
        roster = self.get_roster(race_id)
        msg = ""
        for r in roster:
            member = guild.get_member(r.user_id)
            msg += f"{member.mention} "
        msg += f"You have been assigned to Async Race {race_id}. Use the command `/async_race info {race_id}` to get the seed and submit your time when complete"
        await async_channel.send(msg)

    ####################################################################################################################
    # Determines if a user has permission to view/submit to the given race ID
    def has_permission(self, race_id, user_id):
        has_permission = self.is_public_race(race_id)
        if not has_permission:
            a = self.get_assignment(race_id, user_id)
            if a is not None:
                has_permission = True
        return has_permission

    ####################################################################################################################
    # Logs a user command
    def log_command(self, user, command):
        logging.info(f"User {user.name} ran command `{command}`")

########################################################################################################################
# ASYNC_RACE
########################################################################################################################
# This is the main slash command that will be the prefix of all commands below
    @nextcord.slash_command()
    async def async_race(self, interaction):
        pass

########################################################################################################################
########################################################################################################################
##########################    RACER SUBCOMMANDS    #####################################################################
########################################################################################################################
########################################################################################################################

########################################################################################################################
# RESULTS
########################################################################################################################
    class RaceResultsData():
        def __init__(self, page, user_id):
            self.page = page
            self.user_id = user_id

    @async_race.subcommand(description="Show Race Results for a User")
    async def results(self,
                      interaction,
                      user: nextcord.User = nextcord.SlashOption(description="User to view races for", required=False)):
        self.log_command(interaction.user, "RESULTS")
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
            await interaction.send(f"Recent Async Submissions, page {data.page}:", ephemeral=True)
            table_message_list = self.buildResponseMessageList(self.pt.get_string())
            for table_message in table_message_list:
                await interaction.send(f"`{table_message}`", ephemeral=True)
            await interaction.send(view=AsyncHandler.ShowRacesView(self, race_id_list, self.race_results_impl, data), ephemeral=True)
        else:
            await interaction.send("There are no submissions in that range", ephemeral=True)

########################################################################################################################
# LEADERBOARD
########################################################################################################################
    @async_race.subcommand(description="Show Race Leaderboard")
    async def leaderboard(self,
                          interaction,
                          race_id: int = nextcord.SlashOption(description="Race ID to view leaderboard of", required=False, min_value=1)):
        self.log_command(interaction.user, "LEADERBOARD")
        self.checkAddMember(interaction.user)
        # If no race ID was provided, prompt the user to select one
        if race_id is None:
            race_select_view = AsyncHandler.RaceSelectView(self.leaderboard_impl)
            await interaction.send(view=race_select_view, ephemeral=True)
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

        total_submissions = AsyncSubmission.select(fn.COUNT(AsyncSubmission.id)).where(AsyncSubmission.race_id == race_id).get()
        total_submissions = "No" if total_submissions == 0 else total_submissions
        await interaction.send(f"There have been {total_submissions} submissions to this race so far.", ephemeral=True)

        if race is not None and can_view:
            message_list = self.buildLeaderboardMessageList(race_id)
            for message in message_list:
                await interaction.send(message, ephemeral=True)
        elif can_view:
            await interaction.send(f"Invalid Race ID: {race_id}", ephemeral=True)
        else:
            await interaction.send(f"You must submit a time or FF from the race before the leaderboard can be displayed", ephemeral=True)

########################################################################################################################
# RACES
########################################################################################################################
    class RacesData():
        def __init__(self, page, category):
            self.page = page
            self.category = category

    @async_race.subcommand(description="List Current Races")
    async def list(self, interaction):
        self.log_command(interaction.user, "RACES")
        categoryCount = RaceCategory.select().count()
        logging.info(f"Category Count: {categoryCount}")
        if int(categoryCount) == 1:
            await self.list_races_impl(interaction, AsyncHandler.RacesData(page=1, category=1))
        else:
            await interaction.send(view=AsyncHandler.CategorySelectView(self.list_races_first_impl, 1), ephemeral=True)

    ########################################################################################################################
    async def list_races_first_impl(self, interaction, category_id, page):
        await self.list_races_impl(interaction, AsyncHandler.RacesData(page=page, category=category_id))

    ########################################################################################################################
    # Implementation of the races command, moved to separate function to be able to reuse
    async def list_races_impl(self, interaction, data):
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
                                                                                   self.list_races_impl,
                                                                                   data,
                                                                                   False), ephemeral=True)
        else:
            await interaction.send("No races found in that range", ephemeral=True)

########################################################################################################################
# RACE_INFO
########################################################################################################################
    @async_race.subcommand(description="Show info for an async race")
    async def info(self,
                   interaction,
                   race_id: int = nextcord.SlashOption(description="Race ID to view race info for", required=False, min_value=1)):
        self.checkAddMember(interaction.user)
        self.log_command(interaction.user, "RACE_INFO")
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

        is_race_creator = self.isRaceCreator(interaction.guild, interaction.user)
        if race is None:
            await interaction.send(f"No race found for ID {race_id}", ephemeral=True)
        elif not race.active and not is_race_creator:
            await interaction.send(f"Race {race_id} is not yet active", ephemeral=True)
        else:
            # Check if the user has permissions to view the race info. A user can view race info if any of the following:
            # A) It's a public race
            # B) They're assigned to the race
            # C) They're a race creator running the command in the race creation channel
            if self.has_permission(race_id, interaction.user.id) or self.checkRaceCreatorCommand(interaction):
                message = self.getRaceInfoTable(race, is_race_creator)
                await interaction.send(message, embed=self.getSeedEmbed(race), ephemeral=True)
                race_info_view = AsyncHandler.RaceInfoButtonView(self, race_id)
                await interaction.send(f"Click below to submit/edit or view leaderboard for race {race_id}", view=race_info_view, ephemeral=True)
                if not self.is_public_race(race_id):
                    # Log the time the user got the race info for assigned races
                    assignment = self.get_assignment(race_id, interaction.user.id)
                    if assignment is not None:
                        # We only care about the first time the user got the race info
                        if assignment.race_info_time is None:
                            assignment.race_info_time = datetime.now().isoformat(timespec='minutes').replace('T', ' ')
                            assignment.save()
            else:
                await interaction.send("You do not have permission to view this race info in this channel", ephemeral=True)

########################################################################################################################
# VERIFY_RACE
########################################################################################################################
    @async_race.subcommand(description="Prints information about a race for verification")
    async def verify(self,
                     interaction,
                     race_id: int = nextcord.SlashOption(description="Race to Verify")):
        self.log_command(interaction.user, "VERIFY_RACE")
        if self.is_public_race(race_id):
            await interaction.send("Cannot verify a public (non-assigned) race", ephemeral=True)
            return

        race = self.get_race(race_id)
        if race is not None:
            # Only allow race creators to use verify prior to race completion
            if not self.is_race_complete(race):
                if not self.isRaceCreator(interaction.guild, interaction.user):
                    await interaction.send(f"Non-race creators can only verify races once they are complete")
                    return

            roster = self.get_roster(race_id)
            if roster is not None:
                # For each assigned racer print: username, start date/time (race_info_time), submit date/time, IGT or RTA, VoD link
                info_str = f"`|           Race Verification Info for race {race_id}            | `\n"

                for r in roster:
                    user = self.get_user(r.user_id)
                    s = self.getSubmission(race_id, r.user_id)
                    start_time = "Not Started"
                    submit_time = "Not Completed"
                    game_time_str = "RTA" if config.RtaIsPrimary else "IGT"
                    vod_link = ""
                    game_time_cr = ""
                    if s is not None:
                        start_time = r.race_info_time
                        submit_time = s.submit_date
                        vod_link = s.vod_link
                        if config.RtaIsPrimary:
                            game_time = s.finish_time_rta
                        else:
                            game_time = s.finish_time_igt
                        if game_time == DnfTime:
                            game_time_cr = "DNF"
                        else:
                            game_time_cr += f"{game_time} / {s.collection_rate}"
                    info_str += "`+==========================================================+`\n"
                    info_str += f"`| Racer Name:           |` **{user.username}**\n"
                    info_str += f"`| Start Date/Time:      |` {start_time}\n"
                    info_str += f"`| Submission Date/Time: |` {submit_time}\n"
                    info_str += f"`| VoD Link:             |` {vod_link}\n"
                    info_str += f"`| {game_time_str} / CR:             |` {game_time_cr}\n"
                await interaction.send(info_str, ephemeral=True)
            else:
                await interaction.send("No racers assigned to this race", ephemeral=True)
        else:
            await interaction.send(f"Race ID {race_id} does not exist", ephemeral=True)

########################################################################################################################
########################################################################################################################
######################    RACE MANAGEMENT SUBCOMMANDS    ###############################################################
########################################################################################################################
########################################################################################################################
    @async_race.subcommand()
    async def manage(self, interaction):
        # This defines the manage subcommand which groups all following race management subcommands together
        pass

########################################################################################################################
# ASSIGN_RACER
########################################################################################################################
    @manage.subcommand(description="Assigns a racer to an async race")
    async def assign(self,
                     interaction,
                     user: nextcord.User = nextcord.SlashOption(description="User to assign"),
                     race_id: int = nextcord.SlashOption(description="Race to Deactivate")):
        self.log_command(interaction.user, "ASSIGN_RACER")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        if user is not None:
            self.checkAddMember(user)
        else:
            await interaction.send("Invalid user", ephemeral=True)
            return

        if race_id is not None:
            await self.assign_racer_impl(interaction, race_id, user)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.assign_racer_impl, user)
            await interaction.send(view=race_select_view, ephemeral=True)

    async def assign_racer_impl(self, interaction, race_id, user):
        race = self.get_race(race_id)
        if race is not None:
            r = RaceRoster(race_id= race_id, user_id = user.id)
            r.save()
            await interaction.send(f"Assigned {user.name} to race {race_id}", ephemeral=True)
        else:
            await interaction.send(f"No race found for race ID {race_id}", ephemeral=True)

########################################################################################################################
# START_RACE
########################################################################################################################
    @manage.subcommand(description="Start Async Race")
    async def start(self,
                    interaction,
                    race_id: int = nextcord.SlashOption(description="Race to Start"),
                    notify_racers: int = nextcord.SlashOption(description="Notify the assigned racers?", choices={"Yes": True, "No": False}, required=False, default=True)):
        self.log_command(interaction.user, "START_RACE")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        if race_id is not None:
            await self.start_race_impl(interaction, race_id, notify_racers)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.start_race_impl, notify_racers)
            await interaction.send(view=race_select_view, ephemeral=True)

    ########################################################################################################################
    # Starts a race
    async def start_race_impl(self, interaction, race_id, notify_racers=False):
        race = self.get_race(race_id)
        if race is not None:
            if config.RosterPromptOnRaceStart:
                # Search for race roster entries for this race
                msg = ""
                roster = self.get_roster(race_id)
                if roster is None:
                    msg = f"Race ID {race_id} is currently set as a public race (no racers listed)"
                else:
                    msg = f"Race ID {race_id} currently has the following racers assigned:"
                    for r in roster:
                        racer = AsyncRacer.select().where(AsyncRacer.user_id == r.user_id).get()
                        msg += f"\n{racer.username}"
                await interaction.send(msg, ephemeral=True)
                # Show confirmation
                confirm_view = AsyncHandler.YesNoView(self.start_race_impl2, (race, notify_racers))
                await interaction.send(view=confirm_view, ephemeral=True)
            else:
                await self.start_race_impl2(interaction, True, (race, notify_racers))
        else:
            await interaction.send(f"No race found for race ID {race_id}", ephemeral=True)

    async def start_race_impl2(self, interaction, user_confirmed, data):
        if user_confirmed:
            race = data[0]
            notify_racers = data[1]
            start_date = date.today().isoformat()
            race.start = start_date
            race.active = True
            race.save()
            await interaction.send(f"Started race {race.id}")
            if race.category_id == self.server_info.weekly_category_id:
                await self.add_submit_buttons(race)
                await self.updateLeaderboardMessage(race.id, interaction.guild)
                await self.removeWeeklyAsyncRole(interaction)
                await self.post_announcement(race, interaction)
            if not self.is_public_race(race.id) and notify_racers:
                await self.notify_assigned_racers(race.id)
        else:
            await interaction.send("start_race cancelled", ephemeral=True)

########################################################################################################################
# END_RACE
########################################################################################################################
    @manage.subcommand(description="Manually Ends Async Race (Mark as Inactive, Post results)")
    async def end(self,
                  interaction,
                  race_id: int = nextcord.SlashOption(description="Race to End"),
                  post_result: int = nextcord.SlashOption(description="Fills in missing submissions with FF and posts the results in the async channel", choices={"Yes": True, "No": False}, required=False, default=True)):
        self.log_command(interaction.user, "END_RACE")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        if race_id is not None:
            await self.end_race_impl(interaction, race_id, post_result)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.end_race_impl, post_result)
            await interaction.send(view=race_select_view, ephemeral=True)

    async def end_race_impl(self, interaction, race_id, post_result):
        race = self.get_race(race_id)
        if race is not None:
            race.active = False
            race.save()
            if post_result and not self.is_public_race(race_id):
                await self.post_results(race)
            await interaction.send(f"Ended race {race.id}")
        else:
            await interaction.send(f"No race found for race ID {race_id}", ephemeral=True)

########################################################################################################################
# ADD_RACE
########################################################################################################################
    @manage.subcommand(description="Add Async Race")
    async def add(self,
                  interaction,
                  start_race: int = nextcord.SlashOption(description="Start the race immediately?", choices={"Yes": True, "No": False})):

        self.log_command(interaction.user, "ADD_RACE")

        if self.checkRaceCreatorCommand(interaction):
            add_race_modal = AsyncHandler.AddRaceModal()
            if start_race:
                add_race_modal.start_race_callback = self.start_race_impl
            if RaceCategory.select().count() == 1:
                add_race_modal.category_id = 1
                await interaction.response.send_modal(add_race_modal)
            else:
                add_race_view = AsyncHandler.AddRaceView(add_race_modal)
                await interaction.send(view=add_race_view, ephemeral=True)
        else:
            await interaction.send(NoPermissionMsg, ephemeral=True)

########################################################################################################################
# EDIT_RACE
########################################################################################################################
    @manage.subcommand(description="Edit Async Race")
    async def edit(self, interaction, race_id: int = nextcord.SlashOption(description="Race to Edit"),):
        self.log_command(interaction.user, "EDIT_RACE")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        race = self.get_race(race_id)
        if race is not None:
            # Only allow editing of inactive races with no submissions
            race_submissions = self.get_leaderboard(race)
            if race.active == False and len(race_submissions) == 0:
                add_race_modal = AsyncHandler.AddRaceModal(race=race)
                add_race_modal.mode.default_value = race.description
                add_race_modal.seed.default_value = race.seed
                add_race_modal.instructions.default_value = race.additional_instructions
                await interaction.response.send_modal(add_race_modal)
            else:
                await interaction.send(f"Edit not allowed. Race ID {race_id} is active and/or has existing race submissions")
        else:
            await interaction.send(f"Race ID {race_id} not found", ephemeral=True)

########################################################################################################################
# PAUSE_RACE
########################################################################################################################
    @manage.subcommand(description="Pause Async Race (Mark as Inactive)")
    async def pause(self,
                    interaction,
                    race_id: int = nextcord.SlashOption(description="Race to Deactivate")):
        self.log_command(interaction.user, "PAUSE_RACE")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        if race_id is not None:
            await self.pause_race_impl(interaction, race_id)
        else:
            race_select_view = AsyncHandler.RaceSelectView(self.pause_race_impl)
            await interaction.send(view=race_select_view, ephemeral=True)

    async def pause_race_impl(self, interaction, race_id):
        race = self.get_race(race_id)
        if race is not None:
            race.active = False
            race.save()
            await interaction.send(f"Deactivated race {race.id}")
        else:
            await interaction.send(f"No race found for race ID {race_id}", ephemeral=True)

########################################################################################################################
# REMOVE_RACE
########################################################################################################################
    @manage.subcommand(description="Remove Async Race")
    async def remove(self, interaction, race_id: int = nextcord.SlashOption(description="Race to Remove")):

        self.log_command(interaction.user, "REMOVE_RACE")
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
# PIN_RACE_INFO
########################################################################################################################
    @manage.subcommand(description="Pins race info for a set of races in a specific channel")
    async def pin(self,
                  interaction,
                  channel: nextcord.abc.GuildChannel = nextcord.SlashOption(description="Channel to pin the race info in"),
                  remove_existing: int = nextcord.SlashOption(description="Remove existing pinned races in channel?", choices={"Yes": True, "No": False}, required=False, default=True)):
        self.log_command(interaction.user, "PIN_RACE_INFO")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        # Send Select to choose which category
        await interaction.send(view=AsyncHandler.CategorySelectView(self.pin_race_info_get_races, (channel, remove_existing)), ephemeral=True)

    ########################################################################################################################
    async def pin_race_info_get_races(self, interaction, category_id, data):
        # Verify this category has active races to pin
        try:
            races = AsyncRace.select()                                                                   \
                             .where((AsyncRace.category_id == category_id) & (AsyncRace.active == True)) \
                             .get()
        except:
            races = None

        if races is not None:
            # Send Select to choose which races to pin
            await interaction.send(view=AsyncHandler.MultiRaceSelectView(self.pin_race_info_impl, data, category_id), ephemeral=True)
        else:
            await interaction.send("There are no active races for that category")

    ########################################################################################################################
    async def pin_race_info_impl(self, interaction, data, user_race_choices):
        channel = data[0]
        remove_existing = data[1]
        if remove_existing:
            await interaction.send("Removing old pinned race messages")
            await self.purge_bot_messages(channel)
        await interaction.send("Adding new race messages")
        for c in user_race_choices:
            race_id = int(c)
            race = self.get_race(race_id)
            await channel.send(self.getRaceInfoTable(race), embed=self.getSeedEmbed(race))
            await channel.send(view=AsyncHandler.RaceInfoButtonView(self, race_id))
            await channel.send("`------------------------------------------------------------------------`")
        await interaction.send("Done")

########################################################################################################################
########################################################################################################################
#############################    MOD MISC SUBCOMMANDS    ###############################################################
########################################################################################################################
########################################################################################################################
    @async_race.subcommand()
    async def mod(self, interaction):
        # This defines the mod subcommand which groups all following misc mod subcommands together
        pass

########################################################################################################################
# MOD_UTIL
########################################################################################################################
    @mod.subcommand(description="Mod Utilities")
    async def util(self,
                   interaction,
                   function: int = nextcord.SlashOption(description="Utility Function to Run", choices = { "Force Update Leaderboard Channel": 1, "Post Race Results": 2, "Notify Racers": 3, "Add Submit Buttons": 4}),
                   race_id: int = nextcord.SlashOption(description="Race ID", required=False)):

        self.log_command(interaction.user, "MOD_UTIL")
        if not self.checkRaceCreatorCommand(interaction):
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        if function == 1:
            await self.updateLeaderboardMessage(self.queryLatestWeeklyRaceId(), interaction.guild)
            await interaction.send("Updated weekly leaderboard channel", ephemeral=True)
        elif function == 2:
            race = self.get_race(race_id)
            if race is not None:
                await self.post_results(race)
                await interaction.send("Done")
        elif function == 3:
            await self.notify_assigned_racers(race_id)
            await interaction.send("Done")
        elif function == 4:
            await self.add_submit_buttons()
        await interaction.send("Done", ephemeral=True)

########################################################################################################################
# ADD_CATEGORY
########################################################################################################################
    @mod.subcommand(description="Add async race category")
    async def add_category(self, interaction, name, description):
        self.log_command(interaction.user, "ADD_CATEGORY")
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
    @mod.subcommand(description="Show suggestions for next mode from users who completed the most recent weekly asyncs")
    async def next_mode_suggstions(self, interaction):
        self.log_command(interaction.user, "NEXT_MODE_SUGGESTIONS")
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

        await interaction.send('\n'.join(wheel_list), ephemeral=True)

########################################################################################################################
# PARROT
########################################################################################################################
    @mod.subcommand(description="Bot want a cracker")
    async def parrot(self,
                     interaction,
                     text: str = nextcord.SlashOption(description="Text"),
                     channel: nextcord.abc.GuildChannel = nextcord.SlashOption(
                         description="Channel")):
        self.log_command(interaction.user, "PARROT")
        # If the user is authorized, have the bot post a message with the provided text in the indicated channel
        if interaction.user.id not in config.CoolestGuyIds:
            await interaction.send(NoPermissionMsg, ephemeral=True)
            return

        await channel.send(text)
        await interaction.send("Done", ephemeral=True)

########################################################################################################################
# EDIT_SUBMISSION
########################################################################################################################
    @mod.subcommand(description="Edit User Submission")
    async def edit_submission(self, interaction, submission_id: int = nextcord.SlashOption(description="Submission to Edit"),):
        self.log_command(interaction.user, "EDIT_SUBMISSION")
        try:
            submission_to_edit = AsyncSubmission.select().where(AsyncSubmission.id == submission_id).get()
        except:
            submission_to_edit = None

        if submission_to_edit is None:
            await interaction.send(f"No submission found with ID {submission_id}", ephemeral=True)
            return

        is_race_creator = self.isRaceCreator(interaction.guild, interaction.user)
        is_public_race = self.is_public_race(submission_to_edit.race_id)
        # In order to edit a submission the user must be a race creator or editing their own submission for a public race
        if is_race_creator or (submission_to_edit.user_id == interaction.user.id and is_public_race):
            race = self.get_race(submission_to_edit.race_id)
            submit_time_modal = AsyncHandler.SubmitTimeModal(self,
                                                             race.id,
                                                             (race.category_id == self.server_info.weekly_category_id),
                                                             AsyncHandler.SubmitType.EDIT)
            submit_time_modal.user_id = submission_to_edit.user_id
            submit_time_modal.igt.default_value = submission_to_edit.finish_time_igt
            submit_time_modal.collection_rate.default_value = str(submission_to_edit.collection_rate)
            submit_time_modal.rta.default_value = submission_to_edit.finish_time_rta
            submit_time_modal.comment.default_value = submission_to_edit.comment
            submit_time_modal.next_mode.default_value = submission_to_edit.next_mode
            await interaction.response.send_modal(submit_time_modal)

            await interaction.send(f"Updated submission ID {submission_id}", ephemeral=True)
        else:
            if interaction.user.id != submission_to_edit.user_id:
                interaction.send("You don't have permission. Only race creators can edit other users' submissions", ephemeral=True)
            else:
                interaction.send(SelfEditNoPermission, ephemeral=True)

########################################################################################################################
########################################################################################################################
# Event Handlers
########################################################################################################################
########################################################################################################################

########################################################################################################################
# STARTUP and SHUTDOWN
########################################################################################################################
    @commands.Cog.listener("on_ready")
    async def on_ready_handler(self):
        logging.info("Async Handler Ready")
        if self.test_mode:
            logging.info("  Running in test mode")
        check_add_db_tables()
        await self.bot.sync_application_commands()

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

def setup(bot):
    bot.add_cog(AsyncHandler(bot))
