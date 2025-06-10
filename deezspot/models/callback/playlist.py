#!/usr/bin/python3

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .common import IDs
from .artist import artistObject


@dataclass
class albumTrackPlaylistObject:
    """Album when nested inside a track in a playlist context."""
    type: str = "albumTrackPlaylist"
    album_type: str = ""  # "album" | "single" | "compilation"
    title: str = ""
    release_date: Dict[str, Any] = field(default_factory=dict)  # ReleaseDate as dict
    ids: IDs = field(default_factory=IDs)


@dataclass
class artistTrackPlaylistObject:
    """Artist when nested inside a track in a playlist context."""
    type: str = "artistTrackPlaylist"
    name: str = ""
    genres: List[str] = field(default_factory=list)
    ids: IDs = field(default_factory=IDs)


@dataclass
class trackPlaylistObject:
    """Track when nested inside a playlist context."""
    type: str = "trackPlaylist"
    title: str = ""
    position: int = 0  # Position in the playlist
    duration_ms: int = 0  # mandatory
    # Nested objects instead of string references
    artist: artistTrackPlaylistObject = field(default_factory=artistTrackPlaylistObject)
    album: albumTrackPlaylistObject = field(default_factory=albumTrackPlaylistObject)
    ids: IDs = field(default_factory=IDs)


@dataclass
class playlistObject:
    """A user‑curated playlist, nesting trackPlaylistObject[]."""
    type: str = "playlist"
    title: str = ""
    description: Optional[str] = None
    collaborative: bool = False
    owner: artistObject = field(default_factory=artistObject)
    tracks: List[trackPlaylistObject] = field(default_factory=list)
    ids: IDs = field(default_factory=IDs) 