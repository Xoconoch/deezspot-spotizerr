#!/usr/bin/python3

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .common import IDs


@dataclass
class artistTrackObject:
    """
    An artist when nested inside a track context.
    No genres, no albums—just identifying info.
    """
    type: str = "artistTrack"
    name: str = ""
    ids: IDs = field(default_factory=IDs)


@dataclass
class albumTrackObject:
    """Album when nested inside a track context."""
    type: str = "albumTrack"
    album_type: str = ""  # "album" | "single" | "compilation"
    title: str = ""
    release_date: Dict[str, Any] = field(default_factory=dict)  # ReleaseDate as dict
    total_tracks: int = 0
    genres: List[str] = field(default_factory=list)
    ids: IDs = field(default_factory=IDs)


@dataclass
class trackObject:
    """A full track record, nesting albumTrackObject and artistTrackObject."""
    type: str = "track"
    title: str = ""
    disc_number: int = 1
    track_number: int = 1
    duration_ms: int = 0  # mandatory
    genres: List[str] = field(default_factory=list)
    
    # Nested album summary
    album: albumTrackObject = field(default_factory=albumTrackObject)
    
    # Nested lean artist summary (no genres/albums)
    artist: artistTrackObject = field(default_factory=artistTrackObject)
    
    ids: IDs = field(default_factory=IDs) 