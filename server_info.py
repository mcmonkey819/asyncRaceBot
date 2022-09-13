# -*- coding: utf-8 -*-
from typing import NamedTuple

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
    # This is the channel where tournament async races will be conducted. Racers can submit results here and results will be posted here.
    tourney_async_channel: int

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
    tourney_async_channel = 1017513696190287953)

FortyBonksTourneyInfo = ServerInfo(
    server_id = 828666862798635049,
    race_creator_role = 828671253342715924,
    weekly_submit_channel = 0,
    weekly_category_id = 0,
    tourney_submit_channel = 1015717682051563561,
    race_creator_channel = 1015725462896509119,
    bot_command_channels = [ 1015725462896509119, 1015717682051563561 ],
    weekly_race_done_role = 0,
    weekly_leaderboard_channel = 0,
    announcements_channel = 0,
    weekly_racer_role = 0,
    tourney_async_channel = 1018916661228740656)


SupportedServerList = [ BttServerInfo.server_id ]

# To add a supported server, create a ServerInfo structure then override the list like so:
#     SupportedServerList = [ FortyBonksServerInfo.server_id ]
# Adding multiple servers to the list is NOT supported, it is formatted as a list to match nextcord interface. The AsyncHandler class assumes a single supported server at a time, set by the server_info class field