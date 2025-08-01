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


def append_track_to_m3u(m3u_path: str, track_path: str) -> None:
    """
    Appends a single track path to an existing m3u file.
    
    Args:
        m3u_path: Full path to the m3u file
        track_path: Full path to the track file
    """
    if not track_path or not os.path.exists(track_path):
        return
        
    playlist_m3u_dir = os.path.dirname(m3u_path)
    relative_path = os.path.relpath(track_path, start=playlist_m3u_dir)
    
    with open(m3u_path, "a", encoding="utf-8") as m3u_file:
        m3u_file.write(f"{relative_path}\n")


def write_tracks_to_m3u(output_dir: str, playlist_name: str, tracks: List[Track]) -> str:
    """
    Creates an m3u file and writes all successful tracks to it at once.
    
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