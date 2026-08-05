import discord

from bot.config import EMBED_COLOR, VM_MAX_DB, VM_MIN_DB, get_text
from bot.services.spotify_client import SpotifyTrackInfo

def create_now_embed(
    locale: discord.Locale | str | None,
    info: SpotifyTrackInfo,
    vol: float,
    muted: bool,
) -> discord.Embed:
    title = (
        info.title
        if info.active
        else get_text("nothing_playing", locale)
    )
    mute_icon = "🔇" if muted else "🔊"
    bar_size = 10
    # bar_size шкала калибрована под диапазон VM_MIN_DB..VM_MAX_DB
    db_range = VM_MAX_DB - VM_MIN_DB
    filled = int(((vol - VM_MIN_DB) / db_range) * bar_size) if db_range else 0
    filled = max(0, min(bar_size, filled))
    bar = "▰" * filled + "▱" * (bar_size - filled)
    embed = discord.Embed(
        title=f"{mute_icon} {get_text('now_playing', locale)}",
        description=f"**{title}**",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name=get_text("volume_bar", locale),
        value=f"`{bar}` {round(vol, 1)} dB",
        inline=False,
    )
    return embed