#!/usr/bin/python3

import os
from typing import List, Union
from deezspot.libutils.utils import sanitize_name
from deezspot.libutils.logging_utils import logger
from deezspot.models.download import Track


def create_m3u_file(output_dir: str, playlist_name: str) -> str:
    """
    Creates an m3u playlist file with the proper header.
    Returns full path to the m3u file.
    """
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    os.makedirs(playlist_m3u_dir, exist_ok=True)
    playlist_name_sanitized = sanitize_name(playlist_name)
    m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u")
    # Always ensure header exists (idempotent)
    if not os.path.exists(m3u_path):
        with open(m3u_path, "w", encoding="utf-8") as m3u_file:
            m3u_file.write("#EXTM3U\n")
        logger.debug(f"Created m3u playlist file: {m3u_path}")
    return m3u_path


def ensure_m3u_header(m3u_path: str) -> None:
    """Ensure an existing m3u has the header; create if missing."""
    if not os.path.exists(m3u_path):
        os.makedirs(os.path.dirname(m3u_path), exist_ok=True)
        with open(m3u_path, "w", encoding="utf-8") as m3u_file:
            m3u_file.write("#EXTM3U\n")


# Prefer the actual file that exists on disk; if the stored path doesn't exist,
# attempt to find the same basename with a different extension (e.g., due to conversion).
_AUDIO_EXTS_TRY = [
    ".flac", ".mp3", ".m4a", ".aac", ".alac", ".ogg", ".opus", ".wav", ".aiff"
]


def _resolve_existing_song_path(song_path: str) -> Union[str, None]:
    if not song_path:
        return None
    if os.path.exists(song_path):
        return song_path
    base, _ = os.path.splitext(song_path)
    for ext in _AUDIO_EXTS_TRY:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def _get_track_duration_seconds(track: Track) -> int:
    try:
        if hasattr(track, 'tags') and track.tags:
            if 'duration' in track.tags:
                return int(float(track.tags['duration']))
            elif 'length' in track.tags:
                return int(float(track.tags['length']))
        if hasattr(track, 'song_metadata') and hasattr(track.song_metadata, 'duration_ms'):
            return int(track.song_metadata.duration_ms / 1000)
        return 0
    except (ValueError, AttributeError, TypeError):
        return 0


def _get_track_info(track: Track) -> tuple:
    try:
        if hasattr(track, 'tags') and track.tags:
            artist = track.tags.get('artist', 'Unknown Artist')
            title = track.tags.get('music', track.tags.get('title', 'Unknown Title'))
            return artist, title
        elif hasattr(track, 'song_metadata'):
            sep = ", "
            if hasattr(track, 'tags') and track.tags:
                sep = track.tags.get('artist_separator', sep)
            if hasattr(track.song_metadata, 'artists') and track.song_metadata.artists:
                artist = sep.join([a.name for a in track.song_metadata.artists])
            else:
                artist = 'Unknown Artist'
            title = getattr(track.song_metadata, 'title', 'Unknown Title')
            return artist, title
        else:
            return 'Unknown Artist', 'Unknown Title'
    except (AttributeError, TypeError):
        return 'Unknown Artist', 'Unknown Title'


def append_track_to_m3u(m3u_path: str, track: Union[str, Track]) -> None:
    """Append a single track to m3u with EXTINF and a resolved path."""
    ensure_m3u_header(m3u_path)
    if isinstance(track, str):
        resolved = _resolve_existing_song_path(track)
        if not resolved:
            return
        playlist_m3u_dir = os.path.dirname(m3u_path)
        relative_path = os.path.relpath(resolved, start=playlist_m3u_dir)
        with open(m3u_path, "a", encoding="utf-8") as m3u_file:
            m3u_file.write(f"{relative_path}\n")
    else:
        if (not isinstance(track, Track) or 
            not track.success or 
            not hasattr(track, 'song_path')):
            return
        resolved = _resolve_existing_song_path(track.song_path)
        if not resolved:
            return
        playlist_m3u_dir = os.path.dirname(m3u_path)
        relative_path = os.path.relpath(resolved, start=playlist_m3u_dir)
        duration = _get_track_duration_seconds(track)
        artist, title = _get_track_info(track)
        with open(m3u_path, "a", encoding="utf-8") as m3u_file:
            m3u_file.write(f"#EXTINF:{duration},{artist} - {title}\n")
            m3u_file.write(f"{relative_path}\n")


def write_tracks_to_m3u(output_dir: str, playlist_name: str, tracks: List[Track]) -> str:
    """
    Legacy batch method. Creates an m3u and writes provided tracks.
    Prefer progressive usage: create_m3u_file(...) once, then append_track_to_m3u(...) per track.
    """
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    os.makedirs(playlist_m3u_dir, exist_ok=True)
    m3u_path = os.path.join(playlist_m3u_dir, f"{sanitize_name(playlist_name)}.m3u")
    ensure_m3u_header(m3u_path)
    for track in tracks:
        append_track_to_m3u(m3u_path, track)
    logger.info(f"Created m3u playlist file at: {m3u_path}")
    return m3u_path


def get_m3u_path(output_dir: str, playlist_name: str) -> str:
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    return os.path.join(playlist_m3u_dir, f"{sanitize_name(playlist_name)}.m3u") 