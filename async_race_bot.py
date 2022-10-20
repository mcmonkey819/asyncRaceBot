import sys
import nextcord
from nextcord.ext import commands
from datetime import time
import config
import bot_tokens
import argparse
import logging
import asyncio

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description='Async Race Discord Bot')
parser.add_argument('-test', '-t', action='store_true', help='Runs the bot in test mode')
args = parser.parse_args(sys.argv[1:])

#bot_token = bot_tokens.PRODUCTION_TOKEN
bot_token = bot_tokens.GMP_TOKEN
test_mode = args.test == True or config.TEST_MODE
if test_mode:
    logging.info("Setting test mode for BOT")
    #bot_token = bot_tokens.TEST_TOKEN
    bot_token = bot_tokens.GMP_TOKEN

class Bot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(command_prefix=commands.when_mentioned_or('$'), **kwargs)
        for cog in config.cogs:
            try:
                self.load_extension(cog)
            except Exception as exc:
                logging.error(f"Could not load extension {cog} due to {exc.__class__.__name__}: {exc}")

    async def on_ready(self):
        logging.info('Logged on as {0} (ID: {0.id})'.format(self.user))

    async def close(self):
        await self.get_cog('AsyncRaceHandler').close()
        await super().close()


intents = nextcord.Intents.all()
intents.members = True
bot = Bot(intents=intents)
if test_mode:
    server_utils_cog = bot.get_cog('ServerUtils')
    server_utils_cog.setTestMode()
bot.run(bot_token)

