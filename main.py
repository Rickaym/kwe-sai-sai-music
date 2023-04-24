from discord.ext import commands
from discord import Intents, Status
from datetime import datetime

from bot.utils.extensions import EXTENSIONS
from bot.constants import DEBUG_SERVER_IDS, PREFIX, DISCORD_TOKEN


class BotWrap(commands.Bot):
    EXTENSIONS = EXTENSIONS # type: ignore

    def __init__(self):
        intents = Intents.default()
        intents.voice_states = True

        super().__init__(
            intents=intents,
            case_insensitive=True,
            status=Status.online,
            debug_guilds=DEBUG_SERVER_IDS
        )

        self.active_since = datetime.now() # type: ignore

        for ext in EXTENSIONS:
            self.load_extension(ext)

    async def on_ready(self):
        print(f"{bot.user.name} is on ready.") # type: ignore

bot = BotWrap()

bot.run(DISCORD_TOKEN)
