import discord
import traceback
import sys

from discord.colour import Color
from discord.ext import commands
from discord import ExtensionNotFound, Forbidden, ExtensionNotLoaded, ExtensionAlreadyLoaded



class ExceptionHandler(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def raise_norm(self, ctx, error):
        print(f'Ignoring exception in command {ctx.command}:')
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr)

    def get_usage(self, ctx) -> str:
        """
        Get the context of the command used to get the usage of the
        command in the format of prefix:command_name:*arguments
        """
        return f'{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}'

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error: commands.CommandError):
        """
        Entry point to catch all errors
        """
        if hasattr(ctx.command, 'on_error'):
            return

        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = (commands.CommandNotFound,)
        error = getattr(error, 'original', error)
        if isinstance(error, ignored):
            return

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f'⚠️ {ctx.command} has been disabled.')

        if isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.author.send(f'⚠️ {str(ctx.command).upper()} cannot be used in Private Messages.')
            except discord.HTTPException:
                pass

        if isinstance(error, Forbidden):
            embed = discord.Embed(
                title='🖐️ Hold it...', description=f"⁉️ Required permission is missing or unattainable.",
                color=Color.dark_red())
            embed.set_footer(
                text="Unable to carry out this task. Chances are.. the bot does not have required permissions for this.")
            await ctx.send(embed=embed)

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(title="⚠️ Unable to proceed...",
                                  description=f"Vital argument `{error.param.name}` is missing.", color=Color.dark_red())
            embed.set_footer(text=self.get_usage(ctx))
            await ctx.send(embed=embed)

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"🖐️ Cooldown for {round(error.cooldown.per)} seconds!")
        else:
            if ctx.command.qualified_name.lower() in ('reload', 'unload', 'load'):
                if isinstance(error, ExtensionNotFound):
                    await ctx.send("⚠️ Extension is not found.")
                elif isinstance(error, ExtensionNotLoaded):
                    await ctx.send("⚠️ Extension is not loaded.")
                elif isinstance(error, ExtensionAlreadyLoaded):
                    await ctx.send("⚠️ Extension has been already loaded.")
                else:
                    await self.raise_norm(ctx, error)
            else:
                await self.raise_norm(ctx, error)


def setup(bot):
    bot.add_cog(ExceptionHandler(bot))
    print('Exception handler is loaded')
