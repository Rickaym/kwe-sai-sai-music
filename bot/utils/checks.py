from discord.abc import User
from discord.member import Member
from discord.ext.commands import Context
from discord.commands.context import ApplicationContext
from typing import Union
from bot.constants import ADMINS_ID_LIST


def is_admin(indicator: Union[Context, Member, User]) -> bool:
    if isinstance(indicator, (Member, User)):
        return indicator.id in ADMINS_ID_LIST
    elif isinstance(indicator, (Context, ApplicationContext)):
        return indicator.author.id in ADMINS_ID_LIST


def has_higher_role(member_1, member_2):
    return member_1.top_role > member_2.top_role
