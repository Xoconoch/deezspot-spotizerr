#!/usr/bin/python3

"""
Callback data models for the music metadata schema.
"""

from .common import IDs, ReleaseDate
from .artist import artistObject, artistTrackObject
from .album import albumObject, albumTrackObject, albumArtistObject, trackAlbumObject
from .track import trackObject
from .playlist import playlistObject, trackPlaylistObject, albumTrackPlaylistObject, artistTrackPlaylistObject 