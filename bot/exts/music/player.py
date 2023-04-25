import random

from datetime import datetime
from youtube_dl import YoutubeDL
from discord.channel import TextChannel, VoiceChannel
from discord.commands import ApplicationContext
from discord.guild import Guild
from discord import Embed, Color, VoiceClient
from discord.webhook import WebhookMessage
from discord.member import Member

from enum import Enum

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

NORMAL = 0
LOOP = 1
SUHUFFLE = 2
STYLE_MAP = {0: "Normal", 1: "Loop", 2: "Shuffle"}

SEEK = 0x6335

YDL_PRESET = {
    "format": "bestaudio/best",
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
    _partial: bool = False
    _source: Optional[str] = None  # to pass in a predefined source

    def prefetch(self):
        """
        Initializes source object in advance.
        """
        if self._source is not None:
            raise Exception(f"{self.type} source is alread defined to be prefetched.")
        print(f"[YouTube] Getting source for a spotify track {self.title}.")
        if self.type is TrackType.SPOTIFY:
            with YoutubeDL(YDL_PRESET) as ydl:
                info = ydl.extract_info(  # type: ignore
                    f"ytsearch:{self.title}",
                    download=False,
                )["entries"][
                    0
                ]
            print(f"[YouTube] Found YouTube video {info['title']}.")
            self._source = info["url"]  # type: ignore
        else:
            raise Exception(f"Unrecoginized {self.type} to get source from.")

    @property
    def source(self) -> str:
        if self._source is None:
            self.prefetch()
        return self._source

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
        self.controller: Optional[WebhookMessage] = None

        self._voice_client = None
        self._play_style: int = NORMAL
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
        if self._play_style == NORMAL:
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
    def style(self, value):
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


    def next_track(self):
        self._started_song_at = datetime.utcnow()
        if self._play_style == NORMAL:
            self.at += 1
        elif self._play_style == LOOP:
            pass
        else:
            self.at = random.randint(0, len(self.queue) - 1)

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
        await self.controller.edit(content="", embed=self.get_queue_embed())  # type: ignore

    def get_queue_embed(self) -> Embed:
        embed = Embed(color=0x0074ba)

        progress_bar = ["―"] * 34
        try:
            progress_bar[0] = "🔵"
        except IndexError:
            progress_bar[-1] = "🔵"

        embed.description = (
            f" ```cmd\n%s {''.join(progress_bar)} | {':'.join(self.get_duration(self.now_duration))}/{':'.join(self.get_duration(self.now_playing.duration))} |```\n"
            % ("▶" if self.voice_client.is_playing() else "⏸")
        )
        embed.set_author(
            name=f"𝖭𝖮𝖶 𝖯𝖫𝖠𝖸𝖨𝖭𝖦 🎵 {self.now_playing.title} 🎵",
        )
        t_hor, t_min, t_sec = self.get_duration(self.total_time())
        embed.add_field(name="⏰ Total Duration", value=f"`{t_hor}:{t_min}:{t_sec}`")
        embed.add_field(
            name="Loop",
            value=f"**`{'❌':^5}`**"
            if STYLE_MAP[self.style] == "Normal"
            else f"**`{'✅':^5}`**",
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
            value=self.upcoming_track.title[:8] + "..."
            if self.upcoming_track is not None
            else f"`{'🚫':^9}`",
        )
        embed.add_field(name="Requested By", value=self.now_playing.requested_by)

        queue = ""
        i = 0

        start = max(self.at - 2, 0)
        end = min(self.at + 3, len(self.queue))

        for i in range(start, end):
            track = self.queue[i]
            queue += f"{i+1}. {track.title} ||{':'.join(self.get_duration(track.duration))}||  *({track.requested_by})*\n"

        remainder = len(self.queue)-end

        embed.add_field(name="\n🧳 Queue", value=f"{queue}{f'... and {remainder} more.' if remainder >= 1 else ''}", inline=False)
        if self.auto_queue:
            embed.set_footer(text=f"🔁 Auto queue is enabled.")
        return embed

    def get_duration(self, seconds):
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
