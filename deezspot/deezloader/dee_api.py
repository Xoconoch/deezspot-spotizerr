#!/usr/bin/python3

from time import sleep
from datetime import datetime
from typing import Union
from deezspot.deezloader.__utils__ import artist_sort
from requests import get as req_get
from deezspot.libutils.utils import convert_to_date
from deezspot.libutils.others_settings import header
from deezspot.exceptions import (
    NoDataApi,
    QuotaExceeded,
    TrackNotFound,
    MarketAvailabilityError,
)
from deezspot.libutils.logging_utils import logger
import requests

class API:

	@classmethod
	def __init__(cls):
		cls.__api_link = "https://api.deezer.com/"
		cls.__cover = "https://e-cdns-images.dzcdn.net/images/cover/%s/{}-000000-80-0-0.jpg"
		cls.headers = {
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
		}

	@classmethod
	def __get_api(cls, url, quota_exceeded = False):
		try:
			response = req_get(url, headers=cls.headers)
			response.raise_for_status()
			return response.json()
		except requests.exceptions.RequestException as e:
			logger.error(f"Failed to get API data from {url}: {str(e)}")
			raise

	@classmethod
	def get_chart(cls, index = 0):
		url = f"{cls.__api_link}chart/{index}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_track(cls, track_id):
		url = f"{cls.__api_link}track/{track_id}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_album(cls, album_id):
		url = f"{cls.__api_link}album/{album_id}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_playlist(cls, playlist_id):
		url = f"{cls.__api_link}playlist/{playlist_id}"
		infos = cls.__get_api(url)

		return infos
	
	@classmethod
	def get_episode(cls, episode_id):
		url = f"{cls.__api_link}episode/{episode_id}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist(cls, ids):
		url = f"{cls.__api_link}artist/{ids}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist_top_tracks(cls, ids, limit = 25):
		url = f"{cls.__api_link}artist/{ids}/top?limit={limit}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist_top_albums(cls, ids, limit = 25):
		url = f"{cls.__api_link}artist/{ids}/albums?limit={limit}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist_related(cls, ids):
		url = f"{cls.__api_link}artist/{ids}/related"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist_radio(cls, ids):
		url = f"{cls.__api_link}artist/{ids}/radio"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def get_artist_top_playlists(cls, ids, limit = 25):
		url = f"{cls.__api_link}artist/{ids}/playlists?limit={limit}"
		infos = cls.__get_api(url)

		return infos

	@classmethod
	def search(cls, query, limit=25):
		url = f"{cls.__api_link}search"
		params = {
			"q": query,
			"limit": limit
		}
		infos = cls.__get_api(url, params=params)

		if infos['total'] == 0:
			raise NoDataApi(query)

		return infos

	@classmethod
	def search_track(cls, query, limit=None):
		url = f"{cls.__api_link}search/track/?q={query}"
		
		# Add the limit parameter to the URL if it is provided
		if limit is not None:
			url += f"&limit={limit}"
		
		infos = cls.__get_api(url)

		if infos['total'] == 0:
			raise NoDataApi(query)

		return infos

	@classmethod
	def search_album(cls, query, limit=None):
		url = f"{cls.__api_link}search/album/?q={query}"
		
		# Add the limit parameter to the URL if it is provided
		if limit is not None:
			url += f"&limit={limit}"
		
		infos = cls.__get_api(url)

		if infos['total'] == 0:
			raise NoDataApi(query)

		return infos

	@classmethod
	def search_playlist(cls, query, limit=None):
		url = f"{cls.__api_link}search/playlist/?q={query}"
		
		# Add the limit parameter to the URL if it is provided
		if limit is not None:
			url += f"&limit={limit}"
		
		infos = cls.__get_api(url)

		if infos['total'] == 0:
			raise NoDataApi(query)

		return infos

	@classmethod
	def search_artist(cls, query, limit=None):
		url = f"{cls.__api_link}search/artist/?q={query}"
		
		# Add the limit parameter to the URL if it is provided
		if limit is not None:
			url += f"&limit={limit}"
		
		infos = cls.__get_api(url)

		if infos['total'] == 0:
			raise NoDataApi(query)

		return infos

	@classmethod
	def not_found(cls, song, title):
		try:
			data = cls.search_track(song)['data']
		except NoDataApi:
			raise TrackNotFound(song)

		ids = None

		for track in data:
			if (
				track['title'] == title
			) or (
				title in track['title_short']
			):
				ids = track['id']
				break

		if not ids:
			raise TrackNotFound(song)

		return str(ids)

	@classmethod
	def get_img_url(cls, md5_image, size = "1200x1200"):
		cover = cls.__cover.format(size)
		image_url = cover % md5_image

		return image_url

	@classmethod
	def choose_img(cls, md5_image, size = "1200x1200"):
		image_url = cls.get_img_url(md5_image, size)
		image = req_get(image_url).content

		if len(image) == 13:
			logger.debug(f"Received 13-byte image for md5_image: {md5_image}. Attempting fallback image.")
			image_url = cls.get_img_url("", size)
			image = req_get(image_url).content
			if len(image) == 13:
				logger.warning(f"Fallback image for md5_image {md5_image} (using empty md5) also resulted in a 13-byte response.")

		return image

	@classmethod
	def tracking(cls, ids, album = False, market = None) -> dict:
		song_metadata = {}
		json_track = cls.get_track(ids)

		# Market availability check
		if market:
			available_countries = json_track.get("available_countries")
			track_available_in_specified_markets = False
			markets_checked_str = ""

			if isinstance(market, list):
				markets_checked_str = ", ".join([m.upper() for m in market])
				if available_countries:
					for m_code in market:
						if m_code.upper() in available_countries:
							track_available_in_specified_markets = True
							break # Found in one market, no need to check further
				else: # available_countries is None or empty
					track_available_in_specified_markets = False # Cannot be available if API lists no countries
			elif isinstance(market, str):
				markets_checked_str = market.upper()
				if available_countries and market.upper() in available_countries:
					track_available_in_specified_markets = True
				else: # available_countries is None or empty, or market not in list
					track_available_in_specified_markets = False
			else:
				logger.warning(f"Market parameter has an unexpected type: {type(market)}. Skipping market check.")
				track_available_in_specified_markets = True # Default to available if market param is malformed

			if not track_available_in_specified_markets:
				track_title = json_track.get('title', 'Unknown Title')
				artist_name = json_track.get('artist', {}).get('name', 'Unknown Artist')
				error_msg = f"Track '{track_title}' by '{artist_name}' (ID: {ids}) is not available in market(s): '{markets_checked_str}'."
				logger.warning(error_msg)
				raise MarketAvailabilityError(message=error_msg)

		song_metadata['isrc'] = json_track.get('isrc', '')

		if not album:
			album_ids = json_track['album']['id']
			album_json = cls.get_album(album_ids)
			genres = []

			if "genres" in album_json:
				for genre in album_json['genres']['data']:
					genres.append(genre['name'])

			song_metadata['genre'] = "; ".join(genres)
			ar_album = []

			for contributor in album_json['contributors']:
				if contributor['role'] == "Main":
					ar_album.append(contributor['name'])

			song_metadata['ar_album'] = "; ".join(ar_album)
			song_metadata['album'] = album_json['title']
			song_metadata['label'] = album_json['label']
			song_metadata['upc'] = album_json.get('upc', '')
			song_metadata['nb_tracks'] = album_json['nb_tracks']

		song_metadata['music'] = json_track['title']
		array = []

		for contributor in json_track['contributors']:
			if contributor['name'] != "":
				array.append(contributor['name'])

		array.append(
			json_track['artist']['name']
		)

		song_metadata['artist'] = artist_sort(array)
		song_metadata['tracknum'] = json_track['track_position']
		song_metadata['discnum'] = json_track['disk_number']
		song_metadata['year'] = convert_to_date(json_track['release_date'])
		song_metadata['bpm'] = json_track['bpm']
		song_metadata['duration'] = json_track['duration']
		song_metadata['gain'] = json_track['gain']

		return song_metadata

	@classmethod
	def tracking_album(cls, album_json, market = None):
		song_metadata: dict[
			str,
			Union[list, str, int, datetime]
		] = {
			"music": [],
			"artist": [],
			"tracknum": [],
			"discnum": [],
			"bpm": [],
			"duration": [],
			"isrc": [],
			"gain": [],
			"album": album_json['title'],
			"label": album_json['label'],
			"year": convert_to_date(album_json['release_date']),
			"upc": album_json.get('upc', ''),
			"nb_tracks": album_json['nb_tracks']
		}

		genres = []

		if "genres" in album_json:
			for a in album_json['genres']['data']:
				genres.append(a['name'])

		song_metadata['genre'] = "; ".join(genres)
		ar_album = []

		for a in album_json['contributors']:
			if a['role'] == "Main":
				ar_album.append(a['name'])

		song_metadata['ar_album'] = "; ".join(ar_album)
		sm_items = song_metadata.items()

		for track_info_from_album_json in album_json['tracks']['data']:
			c_ids = track_info_from_album_json['id']
			track_title_for_error = track_info_from_album_json.get('title', 'Unknown Track')
			track_artist_for_error = track_info_from_album_json.get('artist', {}).get('name', 'Unknown Artist')
			
			current_track_metadata_or_error = None
			track_failed = False

			try:
				# Get detailed metadata for the current track
				current_track_metadata_or_error = cls.tracking(c_ids, album=True, market=market)
			except MarketAvailabilityError as e:
				market_str = market
				if isinstance(market, list):
					market_str = ", ".join([m.upper() for m in market])
				elif isinstance(market, str):
					market_str = market.upper()
				logger.warning(f"Track '{track_title_for_error}' (ID: {c_ids}) in album '{album_json.get('title','Unknown Album')}' not available in market(s) '{market_str}': {e.message}")
				current_track_metadata_or_error = {
					'error_type': 'MarketAvailabilityError', 
					'message': e.message, 
					'name': track_title_for_error, 
					'artist': track_artist_for_error, 
					'ids': c_ids,
					'checked_markets': market_str # Store the markets that were checked
				}
				track_failed = True
			except NoDataApi as e_nd:
				logger.warning(f"Track '{track_title_for_error}' (ID: {c_ids}) in album '{album_json.get('title','Unknown Album')}' data not found: {str(e_nd)}")
				current_track_metadata_or_error = {
					'error_type': 'NoDataApi', 
					'message': str(e_nd), 
					'name': track_title_for_error, 
					'artist': track_artist_for_error, 
					'ids': c_ids
				}
				track_failed = True
			except requests.exceptions.ConnectionError as e_conn: # Added to catch connection errors here
				logger.warning(f"Connection error fetching metadata for track '{track_title_for_error}' (ID: {c_ids}) in album '{album_json.get('title','Unknown Album')}': {str(e_conn)}")
				current_track_metadata_or_error = {
				    'error_type': 'ConnectionError',
				    'message': f"Connection error: {str(e_conn)}",
				    'name': track_title_for_error,
				    'artist': track_artist_for_error,
				    'ids': c_ids
				}
				track_failed = True
			except Exception as e_other_track_meta: # Catch any other unexpected error for this specific track
				logger.warning(f"Unexpected error fetching metadata for track '{track_title_for_error}' (ID: {c_ids}) in album '{album_json.get('title','Unknown Album')}': {str(e_other_track_meta)}")
				current_track_metadata_or_error = {
				    'error_type': 'TrackMetadataError',
				    'message': str(e_other_track_meta),
				    'name': track_title_for_error,
				    'artist': track_artist_for_error,
				    'ids': c_ids
				}
				track_failed = True

			for key, list_template in sm_items:
				if isinstance(list_template, list):
					if track_failed:
						if key == 'music':
							song_metadata[key].append(current_track_metadata_or_error)
						elif key == 'artist' and isinstance(current_track_metadata_or_error, dict):
							song_metadata[key].append(current_track_metadata_or_error.get('artist'))
						elif key == 'ids' and isinstance(current_track_metadata_or_error, dict):
							pass
						else:
							song_metadata[key].append(None)
					else:
						song_metadata[key].append(current_track_metadata_or_error.get(key))

		return song_metadata
