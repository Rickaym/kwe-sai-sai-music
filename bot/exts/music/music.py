import time
import discord
import platform
import datetime
import random

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
from bot.exts.music.asyncspotify import AsyncSpotify
from os import getenv

from bot.exts.music.player import PlayStyle, Track, MusicSession, YDL_PRESET, TrackType

"""
By Ricky MY
"""


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


def random_shift(value, max_shift=0.15, min_shift=-0.15):
    value += random.uniform(min_shift, max_shift)
    # To ensure that a stays between 0 and 1
    return max(0, min(value, 1))


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

        spotify_client_credentials_manager = SpotifyClientCredentials(
            client_id=getenv("SPOTIFY_CLIENT_ID"),
            client_secret=getenv("SPOTIFY_CLIENT_SECRET"),
        )

        self.spotify = AsyncSpotify(
            self.bot.loop, client_credentials_manager=spotify_client_credentials_manager
        )

    async def search_spotify(self, commander: Member, track: str) -> List[Track]:
        queue: List[Dict[str, Any]]
        print(f"[Spotify] Fetching {track} items.")
        if track.startswith("https://open.spotify.com/playlist"):
            queue = (await self.spotify.async_playlist_items(playlist_id=track))["items"]  # type: ignore
        elif track.startswith("https://open.spotify.com/album"):
            queue = (await self.spotify.async_album_tracks(track))["items"]  # type: ignore
        else:
            queue = [await self.spotify.async_track(track)]  # type: ignore

        print(f"[Spotify] Fetched {len(queue)} from {track}.")

        return [Track.spotify(track, commander) for track in queue]

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
                    is_url = item.startswith("https://")
                    info = ydl.extract_info(("ytsearch:" if not is_url else "") + item, download=False)
                    if not is_url:
                        info = info["entries"][0]  # type: ignore
                    queue.append(info)
                    print(
                        f"[YouTube] Found results for {item}, fetching first response '{info['title']}'"  # type: ignore
                    )

            if not queue:
                return []

            # if its supposed to stem from externally obtained info
            # returning in _source because `source` is a property and should not
            # be messed with lol
            return [Track.youtube(track, commander) for track in queue]

        return await self.bot.loop.run_in_executor(None, search_yt_inner)

    @slash_command(name="rewind")
    @commands.check(get_voice_checker())
    async def rewind(self, ctx, amount: Option(int, default=1, description="ကျော်ခြင်သော သံစဉ်ခု။", required=False)):  # type: ignore
        """
        နောက်ပြန်ကျောခြင်းခွခြင်း။
        """
        await ctx.defer()
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("Rewind ဖို့သီချင်းအရင်ဖွင့်လေကွာ။")
            return

        try:
            session.move_track_index(-amount)  # offset for when the client stops
        except IndexError:
            await ctx.respond("Rewind စရာမရှိပါ။")
            return

        session.is_controller_moved = True

        session.voice_client.stop()
        await ctx.respond("အိုကေ။")

    @slash_command(name="skip")
    @commands.check(get_voice_checker())
    async def skip(self, ctx, amount: Option(int, default=1, description="ကျော်ခြင်သော သံစဉ်ခု။", required=False)):  # type: ignore
        """
        ကျောခြင်းခွခြင်း။
        """
        await ctx.defer()
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("skip ဖို့သီချင်းအရင်ဖွင့်လေကွာ။")
            return

        if amount == 1:
            session.now_playing.skipped = True

        try:
            session.move_track_index(amount)
        except IndexError:
            await ctx.respond("Skip စရာမရှိပါ။")
            return

        session.is_controller_moved = True

        session.voice_client.stop()
        await ctx.respond("အိုကေ။")

    @slash_command(name="seek")
    @commands.check(get_voice_checker())
    async def seek(self, ctx, seconds: Option(int, description="ကျော်ခြင်သောပမာဏ။")):  # type: ignore
        await ctx.defer()
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond("Seek ဖို့သီချင်းအရင်ဖွင့်လေကွာ။")
            return
        if seconds > (session.now_playing.duration - session.now_duration):
            await ctx.respond("Seek ဖို့သီချင်းကအဲ့လောက်မရှည်ဘူးကွ။")
            return

        start_at = session.now_duration + seconds
        session._started_song_at -= datetime.timedelta(days=0, seconds=seconds)
        session.start_track_at = start_at
        session.is_controller_moved = True

        session.voice_client.stop()

        await ctx.respond(f"အိုကေ `{seconds}` seconds ကျော်ပြီးပါပြီ။!")

    async def check_auto_queue(self, session: MusicSession):
        if session.is_auto_queue and session.at + 2 >= len(session.queue):
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

        if not session.is_queue_remaining():
            # there are no more songs left to be played.
            # we will wait 10 seconds to see if anything would be played
            print("[Move] No tracks remaining, waiting 10 seconds to see if anything would be played")
            time.sleep(10)

            if not session.is_queue_remaining():
                print(f"[Move] Job {guild.id} finished")
                await session.disconnect()
                if self.queues.get(guild.id) is not None:
                    self.queues.pop(guild.id)
            else:
                await self.play_next(guild)
            return

        # there are still songs left to be played.
        await session.ensure_voice_connection()

        # if the controller has been moved, we don't need to auto-move
        if not session.is_controller_moved:
            session.move_track_index(1)
        else:
            session.is_controller_moved = False

        ffmpeg_pre = dict(self.ffmpeg_pre)
        if session.start_track_at != 0:
            start_track_at = time.strftime("%H:%M:%S", time.gmtime(session.start_track_at))
            ffmpeg_pre["options"] = f"-vn -ss {start_track_at}"
            session.start_track_at = 0

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                source=await self.bot.loop.run_in_executor(
                    None, session.now_playing.get_source
                ),
                **self.ffmpeg_pre,
                executable=self.ffmpeg_executable,
            ),
            volume=session.volume,
        )

        try:
            session.voice_client.play(
                source, after=lambda e: self.bot.loop.create_task(self.play_next(guild))
            )
        except ClientException:
            if self.queues.get(guild.id) is not None:
                self.queues.pop(guild.id)

            print(f"[Move] Job {guild.id} got forcefully closed")
            return
        else:
            print(
                f"[Move] Now playing {session.now_playing.title} for job {session.guild.name} with the config as {ffmpeg_pre}."
            )

        upcoming = session.upcoming_track
        if upcoming and upcoming.type is TrackType.SPOTIFY:
            # prefetching upcoming track source & audio features
            self.bot.loop.create_task(upcoming.load_all(self.spotify))

        self.bot.loop.create_task(self.check_auto_queue(session))
        self.bot.loop.create_task(session.update_controller())

    async def start_queue(self, guild: Guild):
        """
        Start queue function that mitigates voice channel and plays the
        first song in queue followed by the move queue function
        """
        session: MusicSession = self.queues[guild.id]
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                source=await self.bot.loop.run_in_executor(
                    None, session.now_playing.get_source
                ),
                **self.ffmpeg_pre,
                executable=self.ffmpeg_executable,
            ),
            volume=session.volume,
        )
        session.start_queue()
        session.voice_client.play(
            source, after=lambda e: self.bot.loop.create_task(self.play_next(guild))
        )
        print(f"[Start] Now playing {session.now_playing.title} for job {guild.name}")

    async def get_recommendations(
        self, commander: Member, tracks: List[Track], limit=3
    ) -> List[Track]:
        if not tracks:
            return []

        if len(tracks) > 100:
            # get the first 100 unique tracks
            tracks = list(set(tracks[:100]))

        tracks_info = {
            track.id: await track.get_audio_features(self.spotify)
            for track in tracks
            if track.type is TrackType.SPOTIFY and not track.skipped
        }

        print(
            f"[Spotify] Getting recommendations for auto-queue based on {len(tracks_info)} tracks."
        )

        # Get the average audio features of the tracks in the playlist
        target_features = {}

        # all supported features for recommendations are set here
        for feature_name in [
            "danceability",
            "energy",
            "valence",
            "instrumentalness",
        ]:
            target_features[f"target_{feature_name}"] = random_shift(
                sum([track[feature_name] for track in tracks_info.values()])
                / len(tracks_info)
            )

        print(
            f"[Spotify] Generated average audio features based '{', '.join(target_features.keys())}' on the tracks."
        )

        # 5 random track ids from the playlist
        seed_tracks = random.sample(tracks_info.keys(), min(5, len(tracks_info)))

        # Get the recommended tracks based on the average audio features
        queue = (
            await self.spotify.async_recommendations(  # type: ignore
                seed_tracks=seed_tracks, limit=limit, **target_features
            )
        )["tracks"]
        print(seed_tracks, target_features)
        # Generate song recommendations based on the average audio features of the tracks in the playlist
        print(f"[Spotify] Recommending {len(queue)} tracks as auto-queue.")

        return [Track.spotify(track, commander, auto_queued=True) for track in queue]

    @slash_command(name="play")
    @commands.check(get_voice_checker(within_same_channel=False, connection=False))
    async def play(self, ctx, *, track: Option(str, description="သံစဉ်အမည် သို့မဟုတ် သံစဉ်လင့်ခ်က်"), auto_queue: Option(bool, description="Spotify Playlist သံစဉ်များအရ စက်စပ် တီးဆိုခြင်း။", default=False)):  # type: ignore
        """
        ကွီးရဲ့သံစဉ်နားထောင်ရန်
        """
        print(f"[{ctx.guild.name}] {ctx.author.name} is playing {track}")
        await ctx.defer()
        if track.startswith("raw:"):
            prelude = [Track.raw(track, ctx.author)]
        elif track.startswith("https://open.spotify.com/"):
            prelude = await self.search_spotify(ctx.author, track)
            # playlist tracks on auto-queue generate recommendations instantly
            if auto_queue and len(prelude) > 1:
                prelude = await self.get_recommendations(ctx.author, prelude)

            # load the first track in the playlist
            await prelude[0].load_all(self.spotify)
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
            await ctx.respond(
                embed=discord.Embed(
                    color=0x2F3136,
                    description=f"အိုကေ ဟော့ဒိသံစဉ်‌ {', '.join(f'[{track.title}]({track.url})' for track in prelude)} ဖွင့်ပါမယ်။",
                )
            )

        # setup session with a recommendation based queue if it's not a playlist
        if auto_queue and len(prelude) == 1:
            print("[Spotify] Starting auto-queue mode. Getting recommendations.")
            self.bot.loop.create_task(self.check_auto_queue(session))

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

    @slash_command(name="mode")
    @commands.check(get_voice_checker())
    async def loop_song(
        self,
        ctx,
        mode: Option(PlayStyle, description="အမျိုးအစား"),  # type: ignore
    ):
        """
        သံစဉ်များလာပုံပြောင်းရန်။
        """
        session = self.queues.get(ctx.guild.id)
        if session is None:
            await ctx.respond(content="သံစဥ်အရင်ဖွင့်ပြီးမှငါ့လာပြော။")
            return

        if PlayStyle.AUTO_QUEUE is mode:
            session.is_auto_queue = not session.is_auto_queue
            await ctx.respond(
                f"သံစဥ် auto-queue ကို {session.is_auto_queue} ပြောင်းပြီးပါပြီး။"
            )
        else:
            session.style = mode
            await ctx.respond(f"သံစဥ်ကို {session.style.value} ပြောင်းပြီးပါပြီး။")
        await session.update_controller()

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
            return await ctx.respond("ငါ့မှာထွက်စရာနေရာမရှိပါ။")
        else:
            await ctx.respond("ဘိုင်းဘိုင်း ငမွှထိုး။")

        await session.disconnect()
        try:
            self.queues.pop(ctx.guild.id)
        except KeyError:
            pass

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
                    "Channel ထဲကိုအရင်ဝင်ပါဉီး။",
                )
                return
            session.pause()
        elif not voice.is_playing():
            await ctx.respond("ဘာသံစဉ်မှရပ်ဆိုင်းဖို့မရှိပါ။")

    @slash_command(name="resume")
    @commands.check(get_voice_checker())
    async def resume(self, ctx):
        """
        ရပ်ဆိုင်းမှုပယ်ဖျက်ခြင်း။
        """
        session = self.queues.get(ctx.guild.id)
        voice: VoiceClient = utils_get(self.bot.voice_clients, guild=ctx.guild)  # type: ignore
        if not voice.is_playing():
            session.resume()
        elif voice.is_playing():
            await ctx.respond("ဘာသံစဉ်မှရပ်ဆိုင်းခြင်းမရှိပါ။")
            return


def setup(bot):
    print("Music.cog is loaded")
    bot.add_cog(Music(bot))
