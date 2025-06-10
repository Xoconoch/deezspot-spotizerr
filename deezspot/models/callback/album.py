#!/usr/bin/python3

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .common import IDs, ReleaseDate


@dataclass
class trackAlbumObject:
    """Track when nested inside an album context."""
    type: str = "trackAlbum"
    title: str = ""
    disc_number: int = 1
    track_number: int = 1
    duration_ms: int = 0
    genres: List[str] = field(default_factory=list)
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
class albumObject:
    """A standalone album/single/compilation, with nested trackAlbumObject[] for its tracks."""
    type: str = "album"
    album_type: str = ""  # "album" | "single" | "compilation"
    title: str = ""
    release_date: Dict[str, Any] = field(default_factory=dict)  # ReleaseDate as dict
    total_tracks: int = 0
    genres: List[str] = field(default_factory=list)
    ids: IDs = field(default_factory=IDs)
    # Nested: album's tracks without redundant album info
    tracks: List[trackAlbumObject] = field(default_factory=list) 