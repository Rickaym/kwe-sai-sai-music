import time
import discord
import platform
import asyncio

from discord.errors import ClientException
from discord.member import Member
from discord.utils import get as utils_get
from typing import Dict, List, Any
from discord.voice_client import VoiceClient
from youtube_dl import YoutubeDL
from discord import Guild
from discord.commands import slash_command, Option
from discord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy import Spotify

from bot.exts.music.player import LOOP, SEEK, Track, MusicSession, YDL_PRESET, TrackType

"""
By Ricky MY
"""

NUMBER_MAP = {
    0: ":zero:",
    1: ":one:",
    2: ":two:",
    3: ":three:",
    4: ":four:",
    5: ":five:",
    6: ":six:",
    7: ":seven:",
    8: ":eight:",
    9: ":nine:",
}


def get_voice_checker(within_same_channel=True, connection=True):
    async def inner(ctx):
        author: Member = ctx.author  # type: ignore
        guild: Guild = ctx.guild  # type: ignore

        if not author.voice:
            await ctx.respond(
                "❕ You need to be in a voice channel to do this action!",
            )
            return False
        elif within_same_channel and (
            guild.me.voice and author.voice.channel != guild.me.voice.channel
        ):
            await ctx.respond(
                "❕ You need to be in a same voice channel to do this action!.",
            )
            return False

        if connection:
            voice: VoiceClient = utils_get(ctx.bot.voice_clients, guild=guild)  # type: ignore
            if voice is None or not voice.is_connected():
                await ctx.respond(
                    "❕ Bot is not connected to any channels",
                )
                return False
        return True

    return inner


def in_channel(ctx):
    return ctx.channel.id == 702714945124696067


class Music(commands.Cog):
    ffmpeg_executable = (
        "bot/utils/ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    )
    ffmpeg_pre = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn",
    }
    embed = discord.Embed()
    embed.set_footer(text="Use the queue commmand to see the queue.")

    def __init__(self, bot) -> None:
        self.bot = bot

        self.queues: Dict[int, MusicSession] = {}

        client_id = "6b51a0d83e2a44a098b4d4b6c7041f18"
        client_secret = "a9fc0ddac96c4dac8f4e9abda8c31bec"

        client_credentials_manager = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )

        self.spotify = Spotify(client_credentials_manager=client_credentials_manager)

    async def search_spotify(self, commander: Member, track: str) -> List[Track]:
        """
        Spotify link sample;
        # https://open.spotify.com/album/0U8DeqqKDgIhIiWOdqiQXE?si=k3P47q3QQw688_BgoiF_1A&dl_branch=1
        # https://open.spotify.com/track/18zzR5w624JxWnSZEKeoHA?si=4b1fdf8a79cb492e
        """

        def search_spotify_inner():
            queue: List[Dict[str, Any]]
            print(f"[Spotify] Fetching {track} items.")
            if track.startswith("https://open.spotify.com/playlist"):
                queue = self.spotify.playlist_items(playlist_id=track)["items"]  # type: ignore
            elif track.startswith("https://open.spotify.com/album"):
                queue = self.spotify.album_tracks(track)["items"]  # type: ignore
            else:
                queue = [self.spotify.track(track)]  # type: ignore

            print(f"[Spotify] Fetched {len(queue)} from {track}.")

            return [Track.spotify(track, commander) for track in queue]

        return await self.bot.loop.run_in_executor(None, search_spotify_inner)

    async def search_yt(self, commander: Member, track_ids: List[str]) -> List[Track]:
        """
        track_ids: List[str] - can be track name, youtube url, and spotify url
        """

        def search_yt_inner() -> List[Track]:
            """
            Search a song with keywords on youtube and returns a list of track(s).
            """
            _ydl_preset = YDL_PRESET
            queue = []
            with YoutubeDL(_ydl_preset) as ydl:
                for item in track_ids:
                    print(f"[YouTube] Searching for {item}")
                    info = ydl.extract_info("ytsearch:" + item, download=False)["entries"][0]  # type: ignore
                    queue.append(info)
                    print(
                        f"[YouTube] Found results for {item}, fetching first response '{info['title']}'"
                    )

            if not queue:
                return []

            # if its supposed to stem from externally obtained info
            # returning in _source because `source` is a property and should not
            # be messed with lol
            return [Track.youtube(track, commander) for track in queue]

        return await self.bot.loop.run_in_executor(None, search_yt_inner)

    @slash_command(name="skip")
    @commands.check(get_voice_checker())
    async def skip(self, ctx):
        """
        ကျောခြင်းခွခြင်း။
        """
        await ctx.defer()
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("skip ဖို့သီချင်းအရင်ဖွင့်လေကွာ။")
            return

        try:
            session.queue[session.at + 1]
        except IndexError:
            await ctx.respond("Skip စရာမရှိပါ။")
            return

        session.voice_client.stop()
        await ctx.respond("အိုကေ။")

    async def check_session_queue(self, session: MusicSession):
        if session.auto_queue and session.at + 2 >= len(session.queue):
            print(
                f"[{session.ctx.guild.name}] Currently at {session.at}/{len(session.queue)} so adding 3 recommendations."
            )

            session.add(
                *(await self.get_recommendations(session.commander, session.queue))
            )
            await session.update_controller()
            print(
                f"[{session.ctx.guild.name}] Added 3 recommendations, tracks totalling {len(session.queue)} now."
            )

    async def play_next(self, guild: Guild):
        """
        Walking through the queue of songs
        """
        session = self.queues.get(guild.id)

        if session is None:
            return
        elif (
            len(session.remaining_tracks) > 1
            or session.style == LOOP
            or session._schedule[0] is not None
        ):  # There are still songs left to be played.
            await session.ensure_voice_connection()

            _ffmpeg_pre = dict(self.ffmpeg_pre)
            if session._schedule[0] == SEEK:
                _ffmpeg_pre["options"] = f"-vn -ss {session._schedule[1]}"
                session._schedule = [None, None]
            else:
                session.next_track()
                asyncio.run_coroutine_threadsafe(
                    self.check_session_queue(session), self.bot.loop
                )
                asyncio.run_coroutine_threadsafe(
                    session.update_controller(), self.bot.loop
                )
                upcoming = session.upcoming_track
                if upcoming and upcoming.type is TrackType.SPOTIFY:
                    # prefetching upcoming track source
                    self.bot.loop.run_in_executor(None, upcoming.prefetch)

            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(
                    source=session.now_playing.source,
                    **_ffmpeg_pre,
                    executable=self.ffmpeg_executable,
                ),
                volume=session.volume,
            )

            try:
                session.voice_client.play(
                    source,
                    after=lambda e: asyncio.run_coroutine_threadsafe(
                        self.play_next(guild), self.bot.loop
                    ),
                )
            except ClientException:
                if self.queues.get(guild.id) is not None:
                    del self.queues[guild.id]

                print(f"[Move] Job {guild.id} got forcefully closed")
                return
            else:
                print(
                    f"[Move] Now playing {session.now_playing.title} for job {session.guild.name}"
                )
        else:  # There are no more songs left to be played.
            time.sleep(10)
            if not (len(session.remaining_tracks) > 1 or session.style == LOOP):
                print(f"[Move] Job {guild.id} finished")
                await session.disconnect()
                if self.queues.get(guild.id) is not None:
                    del self.queues[guild.id]
            else:
                await self.play_next(guild)

    async def start_queue(self, guild: Guild):
        """
        Start queue function that mitigates voice channel and plays the
        first song in queue followed by the move queue function
        """
        session: MusicSession = self.queues[guild.id]
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                session.now_playing.source,
                **self.ffmpeg_pre,
                executable=self.ffmpeg_executable,
            ),
            volume=session.volume,
        )
        session.start_queue()
        session.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(guild), self.bot.loop
            ),
        )
        print(f"[Start] Now playing {session.now_playing.title} for job {guild.name}")

    async def get_recommendations(
        self, commander: Member, tracks: List[Track], limit=3
    ) -> List[Track]:
        def sync_get_recommendations():
            if len(tracks) > 100:
                # Get the first 100 tracks
                # setting back to "tracks" causes unbound problems
                _tracks = tracks[:100]
            else:
                _tracks = tracks

            track_ids = [track.id for track in _tracks]
            print(
                f"[Spotify] Getting recommendations for auto-queue based on {len(track_ids)} tracks."
            )

            tlist = [self.spotify._get_id("track", t) for t in track_ids]
            audio_features = self.spotify._get("audio-features?ids=" + ",".join(tlist))["audio_features"]  # type: ignore

            # Get the average audio features of the tracks in the playlist
            avg_features = {}
            for feature in audio_features[0]:
                if isinstance(audio_features[0][feature], float):
                    avg_features[feature] = sum(
                        [track[feature] for track in audio_features]
                    ) / len(audio_features)

            if len(track_ids) > 5:
                track_ids = track_ids[:5]
            queue = self.spotify.recommendations(  # type: ignore
                seed_tracks=track_ids,
                target_danceability=avg_features["danceability"],
                target_energy=avg_features["energy"],
                target_valence=avg_features["valence"],
                limit=limit,
            )["tracks"]
            # Generate song recommendations based on the average audio features of the tracks in the playlist
            print(f"[Spotify] Recommending {len(queue)} tracks as auto-queue.")

            return [
                Track.spotify(track, commander, auto_queued=True) for track in queue
            ]

        return await self.bot.loop.run_in_executor(None, sync_get_recommendations)

    @slash_command(name="play")
    @commands.check(get_voice_checker(within_same_channel=False, connection=False))
    async def play(self, ctx, *, track: Option(str, description="သံစဉ်အမည် သို့မဟုတ် သံစဉ်လင့်ခ်က်"), auto_queue: Option(bool, description="Spotify Playlist သံစဉ်များအရ စက်စပ် တီးဆိုခြင်း။", default=False)):  # type: ignore
        """
        ကွီးရဲ့သံစဉ်နားထောင်ရန်
        """
        print(f"[{ctx.guild.name}] {ctx.author.name} is playing {track}")
        await ctx.defer()
        if track.startswith("https://open.spotify.com/"):
            prelude = await self.search_spotify(ctx.author, track)
            # setup session with a recommendation based queue
            if auto_queue:
                print("[Spotify] Starting auto-queue mode. Getting recommendations.")
                prelude = await self.get_recommendations(ctx.author, prelude)
        else:
            if track.startswith("https"):
                if not any(
                    track.startswith(url)
                    for url in ["https://youtu.be/", "https://www.youtube.com/watch"]
                ):
                    await ctx.respond(
                        "သံစဉ်လင့်ခ်က် မှန်မှန်ထည့်စမ်းပါကွာ ငတုံးရာ။ ကွီးလက်ခံတာ YouTube ၊ Spotify ပဲလေ။"
                    )
                    return

            prelude = await self.search_yt(ctx.author, [track])

        if not prelude:
            await ctx.respond(f"ရှာမတွေ့ဘူး `{track}` အတွက်။")
            return

        queue = self.queues.get(ctx.guild.id)
        if queue is None:
            print(
                f"[{ctx.guild.name}] Started session with {len(prelude)} tracks, auto_queue: {auto_queue}."
            )
            session = MusicSession(prelude, ctx, auto_queue)
            await session.ensure_voice_connection()

            self.queues[ctx.guild.id] = session
            await self.start_queue(ctx.guild)
        else:
            print(
                f"[{ctx.guild.name}] Music session updated with {len(prelude)} tracks with."
            )
            self.queues[ctx.guild.id].add(*prelude)
            session = self.queues[ctx.guild.id]

        if session.controller is None:
            session.controller = await ctx.respond(embed=session.get_queue_embed())
        else:
            await session.update_controller()
            await ctx.respond("အိုကေ။")

    @slash_command(name="queue")
    @commands.check(get_voice_checker(within_same_channel=False, connection=False))
    async def queue(self, ctx):
        """
        အစဉ်။
        """
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("ငါ့မှာပြစရာမရှိပါ။")
            return

        embed = session.get_queue_embed()
        session.controller = await ctx.respond(embed=embed)

    @slash_command(name="save")
    @commands.check(get_voice_checker())
    async def save_song(self, ctx):
        """
        သံစဉ်ကိုသိမ်းရန်။
        """
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("ငါ့မှာသိမ်းစရာမရှိပါ။")
            return

        embed = discord.Embed(
            description=f"⏲️ Duration: `{':'.join(session.format_duration(session.now_playing.duration))}`\n📡 Requested By: `{session.now_playing.commander.name}#{session.now_playing.commander.discriminator}`",
            color=0xFFD983,
        )
        embed.set_thumbnail(
            url="https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4bd.png"
        )
        embed.set_author(name=session.now_playing.title, url=session.now_playing.url)
        embed.set_image(url=session.now_playing.thumbnail)
        try:
            await ctx.author.send(embed=embed)
        except discord.errors.Forbidden:
            await ctx.respond(content="DM အရင်ဖွင့်ပြီးမှငါ့လာပြော။")
        else:
            await ctx.respond(
                content="📬 မင်းရဲ့ DM ထဲ့ကို slide ထိုးသိမ်းလိုက်ပြီ။",
            )

    @slash_command(name="disconnect")
    @commands.check(get_voice_checker())
    async def leave(self, ctx):
        """
        ကွီးကိုပလစ်ခြင်း။
        """
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("ငါ့မှာထွက်စရာနေရာမရှိပါ။")
            return

        await session.disconnect()
        self.queues.pop(ctx.guild.id)
        await ctx.respond("ဘိုင်းဘိုင်း ငမွှထိုး။")

    @slash_command(name="pause")
    @commands.check(get_voice_checker())
    async def pause(self, ctx):
        """
        ရပ်ဆိုင်းခြင်း။
        """
        session = self.queues.get(ctx.guild.id)
        voice = utils_get(self.bot.voice_clients, guild=ctx.guild)
        if voice.is_playing():
            if ctx.author.voice.channel != ctx.guild.me.voice.channel:
                await ctx.respond(
                    "❕ You need to be in a same voice channel to pause the song",
                )
                return
            session.pause()
        elif not voice.is_playing():
            await ctx.respond("❕ The bot is not playing anything at the moment")

    @slash_command(name="resume")
    @commands.check(get_voice_checker())
    async def resume(self, ctx):
        session = self.queues.get(ctx.guild.id)
        voice: VoiceClient = utils_get(self.bot.voice_clients, guild=ctx.guild)  # type: ignore
        if not voice.is_playing():
            session.resume()
        elif voice.is_playing():
            await ctx.respond("❕ The bot is not paused")
            return


def setup(bot):
    print("Music.cog is loaded")
    bot.add_cog(Music(bot))
