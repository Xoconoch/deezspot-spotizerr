#!/usr/bin/python3

"""
Callback data models for the music metadata schema.
"""

from .common import IDs, ReleaseDate
from .artist import artistObject, albumArtistObject
from .album import albumObject, trackAlbumObject
from .track import trackObject, artistTrackObject, albumTrackObject
from .playlist import playlistObject, trackPlaylistObject, albumTrackPlaylistObject, artistTrackPlaylistObject 