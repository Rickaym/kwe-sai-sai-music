import random

from datetime import datetime
from youtube_dl import YoutubeDL
from discord.channel import TextChannel, VoiceChannel
from discord.commands import ApplicationContext
from discord.guild import Guild
from discord import Embed, VoiceClient
from discord.webhook import WebhookMessage
from discord.interactions import Interaction
from discord.member import Member

from enum import Enum

from dataclasses import dataclass, field
from typing import List, Optional, Union

SEEK = 0x6335

YDL_PRESET = {
    "format": "bestaudio",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "max-downloads": 1,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}


class PlayStyle(Enum):
    LOOP_TRACK = "Loop Track"
    LOOP_QUEUE = "Loop Queue"
    NORMAL = "Normal"
    SHUFFLE = "Shuffle"


class TrackType(Enum):
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"


@dataclass
class Track:
    title: str
    id: str
    thumbnail: str
    url: str
    duration: int
    type: TrackType
    commander: Member
    auto_queued: bool = False
    artists: List[str] = field(default_factory=list)
    _source: Optional[str] = None  # to pass in a predefined source
    _audio_features = (
        None  # this property should be set by the player for spotify tracks
    )
    _is_skipped = False

    def __hash__(self) -> int:
        return hash(self.id)

    def get_source(self) -> str:
        if self._source is None:
            self.load_source()
        return self._source  # type: ignore

    @property
    def skipped(self):
        return self._is_skipped

    @skipped.setter
    def skipped(self, value: bool):
        """
        Set the track as skipped.
        This information is useful for auto-queue system.
        """
        self._is_skipped = value

    async def get_audio_features(self, spotify_api) -> dict:
        if self._audio_features is None:
            await self.load_audio_features(spotify_api)
        return self._audio_features  # type: ignore

    @staticmethod
    def spotify(track: dict, commander: Member, **kwargs):
        # Recommended track object dicts do not come under "track" key but
        # normal track objects do.
        info = track.get("track", track)
        artists = [artist["name"] for artist in info["artists"]]
        return Track(
            title=f"{info['name']} - {', '.join(artists) if artists else ''}",
            artists=artists,
            url=info["external_urls"]["spotify"],
            thumbnail=info["album"]["images"][0]["url"],
            duration=info["duration_ms"] // 1000,
            type=TrackType.SPOTIFY,
            id=info["id"],
            commander=commander,
            **kwargs,
        )

    @property
    def requested_by(self) -> str:
        return "ကွီးရွေးထားသည်။" if self.auto_queued else self.commander.mention

    def load_source(self):
        print(f"[YouTube] Getting source for a spotify track {self.title}.")
        if self.type is TrackType.SPOTIFY:
            with YoutubeDL(YDL_PRESET) as ydl:
                info = ydl.extract_info(  # type: ignore
                    f"ytsearch:{self.title}",
                    download=False,
                )["entries"][0]
            print(f"[YouTube] Found YouTube video {info['title']}.")
            self._source = info["url"]
        else:
            raise Exception(f"Unrecoginized {self.type} to get source from.")

    async def load_audio_features(self, spotify_api):
        if self.type is TrackType.SPOTIFY and self._audio_features is None:
            self._audio_features = await spotify_api.async__get(f"audio-features/{self.id}")  # type: ignore

    async def load_all(self, spotify_api):
        """
        Non YouTube tracks need source and audio_features to be loaded before playing.
        """
        await self.load_audio_features(spotify_api)
        self.load_source()

    @staticmethod
    def youtube(track: dict, commander: Member, **kwargs):
        return Track(
            title=track["title"],
            id=track["id"],
            url=("https://www.youtu.be/" + str(track.get("id"))),
            thumbnail=track.get("thumbnail")
            or "https://www.freeiconspng.com/thumbs/youtube-logo-png/hd-youtube-logo-png-transparent-background-20.png",
            duration=round(track.get("duration", 0)),
            type=TrackType.YOUTUBE,
            commander=commander,
            _source=str(track.get("url")),
            **kwargs,
        )


class MusicSession:
    def __init__(
        self, queue: List[Track], ctx: ApplicationContext, auto_queue: bool
    ) -> None:
        self.queue = queue
        self.auto_queue = auto_queue
        self.ctx = ctx

        self.at: int = 0
        self.voice_channel: VoiceChannel = ctx.author.voice.channel
        self.guild: Guild = ctx.guild
        self.cmd_channel: TextChannel = ctx.channel
        self.commander: Member = ctx.author
        self.volume = 0.5
        self.controller: Optional[Union[WebhookMessage, Interaction]] = None

        self._voice_client = None
        self._play_style: PlayStyle = PlayStyle.NORMAL
        self._started_song_at = None
        self._schedule = [
            None,
            None,
        ]
        self._last_paused = None

    @property
    def now_duration(self) -> int:
        """
        Returns the amount of time in seconds since
        a song started playing
        """
        time_taken = datetime.utcnow() - self._started_song_at
        if self._last_paused is not None:
            time_taken -= datetime.utcnow() - self._last_paused

        return time_taken.seconds

    @property
    def now_playing(self) -> Track:
        """
        Returns the track that is first in queue
        """
        return self.queue[self.at]

    @property
    def upcoming_track(self) -> Optional[Track]:
        """
        Returns the track that is second in queue
        """
        if self._play_style is PlayStyle.NORMAL:
            if self.at + 1 >= len(self.queue):
                return None
            return self.queue[self.at + 1]
        else:
            return self.queue[self.at]

    @property
    def voice_client(self) -> VoiceClient:
        return self._voice_client  # type: ignore

    @property
    def style(self):
        return self._play_style

    @style.setter
    def style(self, value: PlayStyle):
        self._play_style = value

    @property
    def voice(self):
        return self.guild.me.voice

    @property
    def remaining_tracks(self):
        return [track for i, track in enumerate(self.queue) if i >= self.at]

    def start_queue(self):
        """
        Marks the start of the queue
        """
        self._started_song_at = datetime.utcnow()

    def clear_queue(self):
        self.queue = [self.queue[self.at]]
        self.at = 0

    def is_queue_remaining(self):
        return len(self.remaining_tracks) > 1 or self._play_style in (PlayStyle.LOOP_QUEUE, PlayStyle.LOOP_TRACK)

    def total_time(self) -> int:
        return sum(t.duration for t in self.remaining_tracks)

    def place(self, track) -> int:
        return self.queue.index(track)

    def add(self, *tracks: Track):
        if self.auto_queue:
            for t in tracks:
                self.queue.insert(self.at + 1, t)
        else:
            self.queue.extend(tracks)

    def get_next_song_index(self, offset: int = 1):
        """
        Get the index of the next song to play.
        """
        if self._play_style is PlayStyle.NORMAL:
            next_at = self.at + offset
        elif self._play_style is PlayStyle.LOOP_TRACK:
            next_at = self.at
        elif self._play_style is PlayStyle.LOOP_QUEUE:
            next_at = (self.at + offset) % len(self.queue)
        elif self._play_style is PlayStyle.SHUFFLE:
            next_at = random.randint(0, len(self.queue) - 2)
        else:
            raise Exception("Unrecognized play style")
        return next_at

    def set_next_track(self, offset: int = 1):
        """
        Set the next track to play.
        """
        self._started_song_at = datetime.utcnow()
        self.at = self.get_next_song_index(offset)

    def pause(self):
        self.voice_client.pause()
        self._last_paused = datetime.utcnow()

    def resume(self):
        self.voice_client.resume()
        self._last_paused = None

    async def disconnect(self):
        await self.voice_client.disconnect()
        msg = None
        if self.controller:
            try:
                msg = await self.controller.channel.fetch_message(self.controller.id)
            except Exception:
                return

        if msg is None:
            return

        embed = msg.embeds[0]
        embed.description = "```🔴 DISCONNECTED 🔴```"
        await msg.edit(embed=embed)

    async def ensure_voice_connection(self):
        if self._voice_client is None:
            # joining a new voice channel
            print(f"[{self.guild.name}] Joining channel {self.voice_channel.name}")
            self._voice_client = await self.voice_channel.connect(timeout=6000)
        elif self._voice_client.channel != self.commander.voice.channel:
            print(f"[{self.guild.name}] Moved to channel {self.voice_channel.name}")
            await self._voice_client.move_to(self.voice_channel)

    async def update_controller(self):
        if not self.controller:
            return
        if isinstance(self.controller, WebhookMessage):
            await self.controller.edit(content="", embed=self.get_queue_embed())  # type: ignore
        else:
            await self.controller.edit_original_response(
                content="", embed=self.get_queue_embed()
            )

    def get_queue_embed(self) -> Embed:
        embed = Embed(color=0x0074BA)

        progress_bar = ["―"] * 34
        try:
            progress_bar[0] = "🔵"
        except IndexError:
            progress_bar[-1] = "🔵"

        embed.description = (
            f" ```cmd\n%s {''.join(progress_bar)} | {':'.join(self.format_duration(self.now_duration))}/{':'.join(self.format_duration(self.now_playing.duration))} |```\n"
            % ("▶" if self.voice_client.is_playing() else "⏸")
        )
        embed.set_author(
            name=f"𝖭𝖮𝖶 𝖯𝖫𝖠𝖸𝖨𝖭𝖦 🎵 {self.now_playing.title} 🎵",
        )
        t_hor, t_min, t_sec = self.format_duration(self.total_time())
        embed.add_field(name="⏰ Total Duration", value=f"`{t_hor}:{t_min}:{t_sec}`")
        if self.style == PlayStyle.SHUFFLE:
            mode = '🔀'
        elif self.style is PlayStyle.LOOP_QUEUE:
            mode = '🔁'
        elif self.style is PlayStyle.LOOP_TRACK:
            mode ='🔂'
        else:
            mode = '▶️'

        embed.add_field(
            name="Mode",
            value=f"**`{mode:^5}`**"
        )
        embed.add_field(
            name="Volume", value=f"**`{f'{round(self.volume*200)} %':^9}`**"
        )
        embed.add_field(
            name="Songs in queue",
            value=f"{len(self.queue)} {'song' if len(self.queue) == 1 else 'songs'}",
        )
        embed.add_field(
            name="Next-Up",
            value=f"{self.at+2}. {self.upcoming_track.title}"
            if self.upcoming_track
            else f"`{'🚫':^9}`",
        )

        queue = ""
        i = 0

        start = max(self.at - 2, 0)
        end = min(self.at + 3, len(self.queue))

        for i in range(start, end):
            track = self.queue[i]
            row = f"{i+1}. [{track.title}]({track.url}) ||{':'.join(self.format_duration(track.duration))}|| *({track.requested_by})*\n"
            if i == self.at:
                queue += f"**{row}**"
            else:
                queue += row

        remainder = len(self.queue) - end

        embed.add_field(
            name="\n🧳 Queue",
            value=f"{queue}{f'... and {remainder} more.' if remainder >= 1 else ''}",
            inline=False,
        )
        if self.auto_queue:
            embed.set_footer(text=f"🔁 Auto queue is enabled.")
        return embed

    def format_duration(self, seconds):
        sec = seconds
        min = 0
        hor = 0
        while sec >= 60:
            min += 1
            sec -= 60
        while min >= 60:
            hor += 1
            min -= 60

        if len(str(sec)) < 2:
            sec = f"0{sec}"
        if len(str(min)) < 2:
            min = f"0{min}"
        if len(str(hor)) < 2:
            hor = f"0{hor}"
        return str(hor), str(min), str(sec)
