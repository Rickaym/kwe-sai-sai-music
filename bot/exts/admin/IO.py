import psutil

from discord.ext import commands
from discord.commands import slash_command
from discord.commands.context import ApplicationContext
from discord import Embed
from discord.commands.options import Option
from discord.utils import format_dt

from bot.utils.checks import is_admin
from bot.utils.extensions import EXTENSIONS


OPT_EXTS = [e.split('.')[-1] for e in EXTENSIONS]

class AdminIO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.extension_state = []

    @slash_command(name="reload")
    @commands.check(is_admin)
    async def reload_cog(
        self,
        ctx: ApplicationContext,
        extension: Option(str, choices=OPT_EXTS), # type:ignore
    ):
        """
        Reloads a loaded cog to the bot.
        """
        for ext in EXTENSIONS:
            if ext.split(".")[-1] == extension:
                try:
                    self.bot.reload_extension(ext)
                except:
                    pass
                await ctx.respond("☑️", ephemeral=True)
                return
        await ctx.respond("❎", ephemeral=True)

    @slash_command(name="restart")
    @commands.check(is_admin)
    async def restart(self, ctx: ApplicationContext):
        """
        Reloads every cog connected to the bot.
        """
        faulty = ""
        excep = None
        for ext in EXTENSIONS:
            try:
                self.bot.reload_extension(ext)
            except Exception as e:
                excep = e
                faulty += f"\n`{ext}`"
        if excep:
            await ctx.respond(f"❎ {faulty}", ephemeral=True)
            raise excep
        else:
            await ctx.respond("☑️", ephemeral=True)


def setup(bot):
    bot.add_cog(AdminIO(bot))
    print("IO.cog is loaded")
