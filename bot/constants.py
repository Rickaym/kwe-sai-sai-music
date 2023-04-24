"""
Global Constants are typed and defined here.

Constants that doesn't need to be available throughout the library
are defined locally where they're required.
"""
from typing import List
from yaml import load, SafeLoader
from os import getenv
from dotenv import load_dotenv

load_dotenv()

with open("config.yaml", "r") as file:
    CONFIGURATION = load(file, Loader=SafeLoader)

DEBUG_SERVER_ID: int = CONFIGURATION["bot"]["debug_server_id"]
ADMINS_ID_LIST: List[int] = CONFIGURATION["bot"]["admins"]
PREFIX: str = CONFIGURATION["bot"]["prefix"]
DISCORD_TOKEN: str = getenv("TOKEN")
DEBUG: bool = CONFIGURATION["bot"]["debug"]
