#!/usr/bin/python3

from dataclasses import dataclass, field
from typing import List, Optional

from .common import IDs
from .album import albumTrackObject
from .artist import artistTrackObject


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