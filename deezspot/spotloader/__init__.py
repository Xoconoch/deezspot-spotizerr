#!/usr/bin/python3
import traceback
from os.path import isfile
from deezspot.easy_spoty import Spo
from librespot.core import Session
from deezspot.exceptions import InvalidLink
from deezspot.spotloader.__spo_api__ import tracking, tracking_album, tracking_episode
from deezspot.spotloader.spotify_settings import stock_quality
from deezspot.libutils.utils import (
    get_ids,
    link_is_valid,
    what_kind,
)
from deezspot.models import (
    Track,
    Album,
    Playlist,
    Preferences,
    Smart,
    Episode
)
from deezspot.spotloader.__download__ import (
    DW_TRACK,
    DW_ALBUM,
    DW_PLAYLIST,
    DW_EPISODE,
    Download_JOB,
)
from deezspot.libutils.others_settings import (
    stock_output,
    stock_recursive_quality,
    stock_recursive_download,
    stock_not_interface,
    stock_zip,
    method_save,
    is_thread,
    stock_real_time_dl
)
from deezspot.libutils.logging_utils import logger, ProgressReporter

class SpoLogin:
    def __init__(
        self,
        credentials_path: str,
        spotify_client_id: str = None,
        spotify_client_secret: str = None,
        progress_callback = None,
        silent: bool = False
    ) -> None:
        self.credentials_path = credentials_path
        self.spotify_client_id = spotify_client_id
        self.spotify_client_secret = spotify_client_secret
        
        # Initialize Spotify API with credentials if provided
        if spotify_client_id and spotify_client_secret:
            Spo.__init__(client_id=spotify_client_id, client_secret=spotify_client_secret)
            logger.info("Initialized Spotify API with provided credentials")
            
        # Configure progress reporting
        self.progress_reporter = ProgressReporter(callback=progress_callback, silent=silent)
        
        self.__initialize_session()

    def report_progress(self, progress_data):
        """Report progress using the configured reporter."""
        self.progress_reporter.report(progress_data)

    def __initialize_session(self) -> None:
        try:
            session_builder = Session.Builder()
            session_builder.conf.stored_credentials_file = self.credentials_path

            if isfile(self.credentials_path):
                session = session_builder.stored_file().create()
                logger.info("Successfully initialized Spotify session")
            else:
                logger.error("Credentials file not found")
                raise FileNotFoundError("Please fill your credentials.json location!")

            Download_JOB(session)
            Download_JOB.set_progress_reporter(self.progress_reporter)
        except Exception as e:
            logger.error(f"Failed to initialize Spotify session: {str(e)}")
            raise

    def download_track(
        self, link_track,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        method_save=method_save,
        is_thread=is_thread,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ) -> Track:
        try:
            link_is_valid(link_track)
            ids = get_ids(link_track)
            song_metadata = tracking(ids)
            
            logger.info(f"Starting download for track: {song_metadata.get('music', 'Unknown')} - {song_metadata.get('artist', 'Unknown')}")

            preferences = Preferences()
            preferences.real_time_dl = real_time_dl
            preferences.link = link_track
            preferences.song_metadata = song_metadata
            preferences.quality_download = quality_download
            preferences.output_dir = output_dir
            preferences.ids = ids
            preferences.recursive_quality = recursive_quality
            preferences.recursive_download = recursive_download
            preferences.not_interface = not_interface
            preferences.method_save = method_save
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            preferences.convert_to = convert_to

            if not is_thread:
                track = DW_TRACK(preferences).dw()
            else:
                track = DW_TRACK(preferences).dw2()

            return track
        except Exception as e:
            logger.error(f"Failed to download track: {str(e)}")
            traceback.print_exc()
            raise e

    def download_album(
        self, link_album,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        method_save=method_save,
        is_thread=is_thread,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ) -> Album:
        try:
            link_is_valid(link_album)
            ids = get_ids(link_album)
            # Use stored credentials for API calls
            album_json = Spo.get_album(ids)
            song_metadata = tracking_album(album_json)
            
            logger.info(f"Starting download for album: {song_metadata.get('album', 'Unknown')} - {song_metadata.get('ar_album', 'Unknown')}")

            preferences = Preferences()
            preferences.real_time_dl = real_time_dl
            preferences.link = link_album
            preferences.song_metadata = song_metadata
            preferences.quality_download = quality_download
            preferences.output_dir = output_dir
            preferences.ids = ids
            preferences.json_data = album_json
            preferences.recursive_quality = recursive_quality
            preferences.recursive_download = recursive_download
            preferences.not_interface = not_interface
            preferences.method_save = method_save
            preferences.make_zip = make_zip
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            preferences.convert_to = convert_to

            if not is_thread:
                album = DW_ALBUM(preferences).dw()
            else:
                album = DW_ALBUM(preferences).dw2()

            return album
        except Exception as e:
            logger.error(f"Failed to download album: {str(e)}")
            traceback.print_exc()
            raise e

    def download_playlist(
        self, link_playlist,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        method_save=method_save,
        is_thread=is_thread,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ) -> Playlist:
        try:
            link_is_valid(link_playlist)
            ids = get_ids(link_playlist)

            song_metadata = []
            # Use stored credentials for API calls
            playlist_json = Spo.get_playlist(ids)
            
            logger.info(f"Starting download for playlist: {playlist_json.get('name', 'Unknown')}")

            for track in playlist_json['tracks']['items']:
                is_track = track['track']
                if not is_track:
                    continue
                external_urls = is_track['external_urls']
                if not external_urls:
                    c_song_metadata = f"The track \"{is_track['name']}\" is not available on Spotify :("
                    logger.warning(f"Track not available: {is_track['name']}")
                else:
                    ids = get_ids(external_urls['spotify'])
                    c_song_metadata = tracking(ids)
                song_metadata.append(c_song_metadata)

            preferences = Preferences()
            preferences.real_time_dl = real_time_dl
            preferences.link = link_playlist
            preferences.song_metadata = song_metadata
            preferences.quality_download = quality_download
            preferences.output_dir = output_dir
            preferences.ids = ids
            preferences.json_data = playlist_json
            preferences.recursive_quality = recursive_quality
            preferences.recursive_download = recursive_download
            preferences.not_interface = not_interface
            preferences.method_save = method_save
            preferences.make_zip = make_zip
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            preferences.convert_to = convert_to

            if not is_thread:
                playlist = DW_PLAYLIST(preferences).dw()
            else:
                playlist = DW_PLAYLIST(preferences).dw2()

            return playlist
        except Exception as e:
            logger.error(f"Failed to download playlist: {str(e)}")
            traceback.print_exc()
            raise e

    def download_episode(
        self, link_episode,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        method_save=method_save,
        is_thread=is_thread,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ) -> Episode:
        try:
            link_is_valid(link_episode)
            ids = get_ids(link_episode)
            # Use stored credentials for API calls
            episode_json = Spo.get_episode(ids)
            episode_metadata = tracking_episode(ids)
            
            logger.info(f"Starting download for episode: {episode_metadata.get('name', 'Unknown')} - {episode_metadata.get('show', 'Unknown')}")

            preferences = Preferences()
            preferences.real_time_dl = real_time_dl
            preferences.link = link_episode
            preferences.song_metadata = episode_metadata
            preferences.output_dir = output_dir
            preferences.ids = ids
            preferences.json_data = episode_json
            preferences.recursive_quality = recursive_quality
            preferences.recursive_download = recursive_download
            preferences.not_interface = not_interface
            preferences.method_save = method_save
            preferences.is_episode = True
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            preferences.convert_to = convert_to

            if not is_thread:
                episode = DW_EPISODE(preferences).dw()
            else:
                episode = DW_EPISODE(preferences).dw2()

            return episode
        except Exception as e:
            logger.error(f"Failed to download episode: {str(e)}")
            traceback.print_exc()
            raise e

    def download_artist(
        self, link_artist,
        album_type: str = 'album,single,compilation,appears_on',
        limit: int = 50,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        method_save=method_save,
        is_thread=is_thread,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ):
        """
        Download all albums (or a subset based on album_type and limit) from an artist.
        """
        try:
            link_is_valid(link_artist)
            ids = get_ids(link_artist)
            discography = Spo.get_artist(ids, album_type=album_type, limit=limit)
            albums = discography.get('items', [])
            if not albums:
                logger.warning("No albums found for the provided artist")
                raise Exception("No albums found for the provided artist.")
                
            logger.info(f"Starting download for artist discography: {discography.get('name', 'Unknown')}")
            
            downloaded_albums = []
            for album in albums:
                album_url = album.get('external_urls', {}).get('spotify')
                if not album_url:
                    logger.warning(f"No URL found for album: {album.get('name', 'Unknown')}")
                    continue
                downloaded_album = self.download_album(
                    album_url,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
                    make_zip=make_zip,
                    method_save=method_save,
                    is_thread=is_thread,
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to
                )
                downloaded_albums.append(downloaded_album)
            return downloaded_albums
        except Exception as e:
            logger.error(f"Failed to download artist discography: {str(e)}")
            traceback.print_exc()
            raise e

    def download_smart(
        self, link,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        method_save=method_save,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None
    ) -> Smart:
        try:
            link_is_valid(link)
            link = what_kind(link)
            smart = Smart()

            if "spotify.com" in link:
                source = "https://spotify.com"
            smart.source = source
            
            logger.info(f"Starting smart download for: {link}")

            if "track/" in link:
                if not "spotify.com" in link:
                    raise InvalidLink(link)
                track = self.download_track(
                    link,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
                    method_save=method_save,
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries
                )
                smart.type = "track"
                smart.track = track

            elif "album/" in link:
                if not "spotify.com" in link:
                    raise InvalidLink(link)
                album = self.download_album(
                    link,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
                    make_zip=make_zip,
                    method_save=method_save,
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries
                )
                smart.type = "album"
                smart.album = album

            elif "playlist/" in link:
                if not "spotify.com" in link:
                    raise InvalidLink(link)
                playlist = self.download_playlist(
                    link,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
                    make_zip=make_zip,
                    method_save=method_save,
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries
                )
                smart.type = "playlist"
                smart.playlist = playlist

            elif "episode/" in link:
                if not "spotify.com" in link:
                    raise InvalidLink(link)
                episode = self.download_episode(
                    link,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
                    method_save=method_save,
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries
                )
                smart.type = "episode"
                smart.episode = episode

            return smart
        except Exception as e:
            logger.error(f"Failed to perform smart download: {str(e)}")
            traceback.print_exc()
            raise e
