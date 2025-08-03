#!/usr/bin/python3

import os
from typing import List, Union
from deezspot.libutils.utils import sanitize_name
from deezspot.libutils.logging_utils import logger
from deezspot.models.download import Track


def create_m3u_file(output_dir: str, playlist_name: str) -> str:
    """
    Creates an m3u playlist file with the proper header.
    
    Args:
        output_dir: Base output directory
        playlist_name: Name of the playlist (will be sanitized)
        
    Returns:
        str: Full path to the created m3u file
    """
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    os.makedirs(playlist_m3u_dir, exist_ok=True)
    
    playlist_name_sanitized = sanitize_name(playlist_name)
    m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u")
    
    if not os.path.exists(m3u_path):
        with open(m3u_path, "w", encoding="utf-8") as m3u_file:
            m3u_file.write("#EXTM3U\n")
        logger.debug(f"Created m3u playlist file: {m3u_path}")
    
    return m3u_path


def _get_track_duration_seconds(track: Track) -> int:
    """
    Extract track duration in seconds from track metadata.
    
    Args:
        track: Track object
        
    Returns:
        int: Duration in seconds, defaults to 0 if not available
    """
    try:
        # Try to get duration from tags first
        if hasattr(track, 'tags') and track.tags:
            if 'duration' in track.tags:
                return int(float(track.tags['duration']))
            elif 'length' in track.tags:
                return int(float(track.tags['length']))
        
        # Try to get from song_metadata if available
        if hasattr(track, 'song_metadata') and hasattr(track.song_metadata, 'duration_ms'):
            return int(track.song_metadata.duration_ms / 1000)
        
        # Fallback to 0 if no duration found
        return 0
    except (ValueError, AttributeError, TypeError):
        return 0


def _get_track_info(track: Track) -> tuple:
    """
    Extract artist and title information from track.
    
    Args:
        track: Track object
        
    Returns:
        tuple: (artist, title) strings
    """
    try:
        if hasattr(track, 'tags') and track.tags:
            artist = track.tags.get('artist', 'Unknown Artist')
            title = track.tags.get('music', track.tags.get('title', 'Unknown Title'))
            return artist, title
        elif hasattr(track, 'song_metadata'):
            if hasattr(track.song_metadata, 'artists') and track.song_metadata.artists:
                artist = ', '.join([a.name for a in track.song_metadata.artists])
            else:
                artist = 'Unknown Artist'
            title = getattr(track.song_metadata, 'title', 'Unknown Title')
            return artist, title
        else:
            return 'Unknown Artist', 'Unknown Title'
    except (AttributeError, TypeError):
        return 'Unknown Artist', 'Unknown Title'


def append_track_to_m3u(m3u_path: str, track: Union[str, Track]) -> None:
    """
    Appends a single track to an existing m3u file with extended format.
    
    Args:
        m3u_path: Full path to the m3u file
        track: Track object or string path to track file
    """
    if isinstance(track, str):
        # Legacy support for string paths
        track_path = track
        if not track_path or not os.path.exists(track_path):
            return
        
        playlist_m3u_dir = os.path.dirname(m3u_path)
        relative_path = os.path.relpath(track_path, start=playlist_m3u_dir)
        
        with open(m3u_path, "a", encoding="utf-8") as m3u_file:
            m3u_file.write(f"{relative_path}\n")
    else:
        # Track object with full metadata
        if (not isinstance(track, Track) or 
            not track.success or 
            not hasattr(track, 'song_path') or 
            not track.song_path or 
            not os.path.exists(track.song_path)):
            return
        
        playlist_m3u_dir = os.path.dirname(m3u_path)
        relative_path = os.path.relpath(track.song_path, start=playlist_m3u_dir)
        
        # Get track metadata
        duration = _get_track_duration_seconds(track)
        artist, title = _get_track_info(track)
        
        with open(m3u_path, "a", encoding="utf-8") as m3u_file:
            m3u_file.write(f"#EXTINF:{duration},{artist} - {title}\n")
            m3u_file.write(f"{relative_path}\n")


def write_tracks_to_m3u(output_dir: str, playlist_name: str, tracks: List[Track]) -> str:
    """
    Creates an m3u file and writes all successful tracks to it at once using extended format.
    
    Args:
        output_dir: Base output directory
        playlist_name: Name of the playlist (will be sanitized)
        tracks: List of Track objects
        
    Returns:
        str: Full path to the created m3u file
    """
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    os.makedirs(playlist_m3u_dir, exist_ok=True)
    
    playlist_name_sanitized = sanitize_name(playlist_name)
    m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u")
    
    with open(m3u_path, "w", encoding="utf-8") as m3u_file:
        m3u_file.write("#EXTM3U\n")
        
        for track in tracks:
            if (isinstance(track, Track) and 
                track.success and 
                hasattr(track, 'song_path') and 
                track.song_path and 
                os.path.exists(track.song_path)):
                
                relative_song_path = os.path.relpath(track.song_path, start=playlist_m3u_dir)
                
                # Get track metadata
                duration = _get_track_duration_seconds(track)
                artist, title = _get_track_info(track)
                
                # Write EXTINF line with duration and metadata
                m3u_file.write(f"#EXTINF:{duration},{artist} - {title}\n")
                m3u_file.write(f"{relative_song_path}\n")
    
    logger.info(f"Created m3u playlist file at: {m3u_path}")
    return m3u_path


def get_m3u_path(output_dir: str, playlist_name: str) -> str:
    """
    Get the expected path for an m3u file without creating it.
    
    Args:
        output_dir: Base output directory
        playlist_name: Name of the playlist (will be sanitized)
        
    Returns:
        str: Full path where the m3u file would be located
    """
    playlist_m3u_dir = os.path.join(output_dir, "playlists")
    playlist_name_sanitized = sanitize_name(playlist_name)
    return os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u") 