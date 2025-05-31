#!/usr/bin/python3

from deezspot.models.track import Track
from deezspot.models.album import Album
from deezspot.models.playlist import Playlist

class Smart:
	def __init__(self) -> None:
		self.track: Track = None
		self.album: Album = None
		self.playlist: Playlist = None
		self.type = None
		self.source = None