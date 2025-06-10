#!/usr/bin/python3
import traceback
from os.path import isfile
from deezspot.easy_spoty import Spo
from librespot.core import Session
from deezspot.exceptions import InvalidLink, MarketAvailabilityError
from deezspot.spotloader.__spo_api__ import tracking, tracking_album, tracking_episode
from deezspot.spotloader.spotify_settings import stock_quality, stock_market
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
    stock_save_cover,
    stock_real_time_dl,
    stock_market
)
from deezspot.libutils.logging_utils import logger, ProgressReporter, report_progress

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
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market: list[str] | None = stock_market
    ) -> Track:
        try:
            link_is_valid(link_track)
            ids = get_ids(link_track)
            song_metadata = tracking(ids, market=market)
            
            if song_metadata is None:
                raise Exception(f"Could not retrieve metadata for track {link_track}. It might not be available or an API error occurred.")

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
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            if convert_to is None:
                preferences.convert_to = None
                preferences.bitrate = None
            else:
                preferences.convert_to = convert_to
                preferences.bitrate = bitrate
            preferences.save_cover = save_cover
            preferences.market = market

            track = DW_TRACK(preferences).dw()

            return track
        except MarketAvailabilityError as e:
            logger.error(f"Track download failed due to market availability: {str(e)}")
            if song_metadata:
                track_info = {
                    "name": song_metadata.get("music", "Unknown Track"),
                    "artist": song_metadata.get("artist", "Unknown Artist"),
                }
                summary = {
                    "successful_tracks": [],
                    "skipped_tracks": [],
                    "failed_tracks": [{
                        "track": f"{track_info['name']} - {track_info['artist']}",
                        "reason": str(e)
                    }],
                    "total_successful": 0,
                    "total_skipped": 0,
                    "total_failed": 1
                }
                report_progress(
                    reporter=self.progress_reporter,
                    report_type="track",
                    song=track_info['name'],
                    artist=track_info['artist'],
                    status="error",
                    url=link_track,
                    error=str(e),
                    summary=summary
                )
            raise
        except Exception as e:
            logger.error(f"Failed to download track: {str(e)}")
            traceback.print_exc()
            if song_metadata:
                track_info = {
                    "name": song_metadata.get("music", "Unknown Track"),
                    "artist": song_metadata.get("artist", "Unknown Artist"),
                }
                summary = {
                    "successful_tracks": [],
                    "skipped_tracks": [],
                    "failed_tracks": [{
                        "track": f"{track_info['name']} - {track_info['artist']}",
                        "reason": str(e)
                    }],
                    "total_successful": 0,
                    "total_skipped": 0,
                    "total_failed": 1
                }
                report_progress(
                    reporter=self.progress_reporter,
                    report_type="track",
                    song=track_info['name'],
                    artist=track_info['artist'],
                    status="error",
                    url=link_track,
                    error=str(e),
                    summary=summary
                )
            raise e

    def download_album(
        self, link_album,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market: list[str] | None = stock_market
    ) -> Album:
        try:
            link_is_valid(link_album)
            ids = get_ids(link_album)
            album_json = Spo.get_album(ids)
            if not album_json:
                 raise Exception(f"Could not retrieve album data for {link_album}.")
            
            song_metadata = tracking_album(album_json, market=market)
            if song_metadata is None:
                raise Exception(f"Could not process album metadata for {link_album}. It might not be available in the specified market(s) or an API error occurred.")

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
            preferences.make_zip = make_zip
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            if convert_to is None:
                preferences.convert_to = None
                preferences.bitrate = None
            else:
                preferences.convert_to = convert_to
                preferences.bitrate = bitrate
            preferences.save_cover = save_cover
            preferences.market = market

            album = DW_ALBUM(preferences).dw()

            return album
        except MarketAvailabilityError as e:
            logger.error(f"Album download failed due to market availability: {str(e)}")
            raise
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
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market: list[str] | None = stock_market
    ) -> Playlist:
        try:
            link_is_valid(link_playlist)
            ids = get_ids(link_playlist)

            song_metadata = []
            playlist_json = Spo.get_playlist(ids)
            if not playlist_json:
                raise Exception(f"Could not retrieve playlist data for {link_playlist}.")
            
            logger.info(f"Starting download for playlist: {playlist_json.get('name', 'Unknown')}")

            for track_item_wrapper in playlist_json['tracks']['items']:
                track_info = track_item_wrapper.get('track')
                c_song_metadata = None # Initialize for each item

                if not track_info:
                    logger.warning(f"Skipping an item in playlist {playlist_json.get('name', 'Unknown Playlist')} as it does not appear to be a valid track object.")
                    # Create a placeholder for this unidentifiable item
                    c_song_metadata = {
                        'name': 'Unknown Skipped Item',
                        'ids': None,
                        'error_type': 'InvalidItemStructure',
                        'error_message': 'Playlist item was not a valid track object.'
                    }
                    song_metadata.append(c_song_metadata)
                    continue

                track_name_for_logs = track_info.get('name', 'Unknown Track')
                track_id_for_logs = track_info.get('id', 'Unknown ID') # Track's own ID if available
                external_urls = track_info.get('external_urls')

                if not external_urls or not external_urls.get('spotify'):
                    logger.warning(f"Track \"{track_name_for_logs}\" (ID: {track_id_for_logs}) in playlist {playlist_json.get('name', 'Unknown Playlist')} is not available on Spotify or has no URL.")
                    c_song_metadata = {
                        'name': track_name_for_logs,
                        'ids': track_id_for_logs, # Use track's own ID if available, otherwise will be None
                        'error_type': 'MissingTrackURL',
                        'error_message': f"Track \"{track_name_for_logs}\" is not available on Spotify or has no URL."
                    }
                else:
                    track_spotify_url = external_urls['spotify']
                    track_ids_from_url = get_ids(track_spotify_url) # This is the ID used for fetching with 'tracking'
                    try:
                        # Market check for each track is done within tracking()
                        # Pass market. tracking() will raise MarketAvailabilityError if unavailable.
                        fetched_metadata = tracking(track_ids_from_url, market=market)
                        if fetched_metadata:
                            c_song_metadata = fetched_metadata
                        else:
                            # tracking() returned None, but didn't raise MarketAvailabilityError. General fetch error.
                            logger.warning(f"Could not retrieve full metadata for track {track_name_for_logs} (ID: {track_ids_from_url}, URL: {track_spotify_url}) in playlist {playlist_json.get('name', 'Unknown Playlist')}. API error or other issue.")
                            c_song_metadata = {
                                'name': track_name_for_logs,
                                'ids': track_ids_from_url,
                                'error_type': 'MetadataFetchError',
                                'error_message': f"Failed to fetch full metadata for track {track_name_for_logs}."
                            }
                    except MarketAvailabilityError as e:
                        logger.warning(f"Track {track_name_for_logs} (ID: {track_ids_from_url}, URL: {track_spotify_url}) in playlist {playlist_json.get('name', 'Unknown Playlist')} is not available in the specified market(s). Skipping. Error: {str(e)}")
                        c_song_metadata = {
                            'name': track_name_for_logs,
                            'ids': track_ids_from_url,
                            'error_type': 'MarketAvailabilityError',
                            'error_message': str(e)
                        }
                    except Exception as e_tracking: # Catch any other unexpected error from tracking()
                        logger.error(f"Unexpected error fetching metadata for track {track_name_for_logs} (ID: {track_ids_from_url}, URL: {track_spotify_url}): {str(e_tracking)}")
                        c_song_metadata = {
                            'name': track_name_for_logs,
                            'ids': track_ids_from_url,
                            'error_type': 'UnexpectedTrackingError',
                            'error_message': f"Unexpected error fetching metadata: {str(e_tracking)}"
                        }
                
                if c_song_metadata: # Ensure something is appended
                    song_metadata.append(c_song_metadata)
                else:
                    # This case should ideally not be reached if logic above is complete
                    logger.error(f"Logic error: c_song_metadata remained None for track {track_name_for_logs} in playlist {playlist_json.get('name', 'Unknown Playlist')}")
                    song_metadata.append({
                        'name': track_name_for_logs,
                        'ids': track_id_for_logs or track_ids_from_url,
                        'error_type': 'InternalLogicError',
                        'error_message': 'Internal error processing playlist track metadata.'
                    })


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
            preferences.make_zip = make_zip
            preferences.is_episode = False
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            if convert_to is None:
                preferences.convert_to = None
                preferences.bitrate = None
            else:
                preferences.convert_to = convert_to
                preferences.bitrate = bitrate
            preferences.save_cover = save_cover
            preferences.market = market

            playlist = DW_PLAYLIST(preferences).dw()

            return playlist
        except MarketAvailabilityError as e:
            logger.error(f"Playlist download failed due to market availability issues with one or more tracks: {str(e)}")
            raise
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
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market: list[str] | None = stock_market
    ) -> Episode:
        try:
            link_is_valid(link_episode)
            ids = get_ids(link_episode)
            episode_json = Spo.get_episode(ids)
            if not episode_json:
                raise Exception(f"Could not retrieve episode data for {link_episode} from API.")

            episode_metadata = tracking_episode(ids, market=market)
            if episode_metadata is None:
                raise Exception(f"Could not process episode metadata for {link_episode}. It might not be available in the specified market(s) or an API error occurred.")
            
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
            preferences.is_episode = True
            preferences.custom_dir_format = custom_dir_format
            preferences.custom_track_format = custom_track_format
            preferences.pad_tracks = pad_tracks
            preferences.initial_retry_delay = initial_retry_delay
            preferences.retry_delay_increase = retry_delay_increase
            preferences.max_retries = max_retries
            if convert_to is None:
                preferences.convert_to = None
                preferences.bitrate = None
            else:
                preferences.convert_to = convert_to
                preferences.bitrate = bitrate
            preferences.save_cover = save_cover
            preferences.market = market

            episode = DW_EPISODE(preferences).dw()

            return episode
        except MarketAvailabilityError as e:
            logger.error(f"Episode download failed due to market availability: {str(e)}")
            raise
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
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        market: list[str] | None = stock_market,
        save_cover=stock_save_cover
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
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to,
                    bitrate=bitrate,
                    market=market,
                    save_cover=save_cover
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
        real_time_dl=stock_real_time_dl,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market: list[str] | None = stock_market
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
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to,
                    bitrate=bitrate,
                    save_cover=save_cover,
                    market=market
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
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to,
                    bitrate=bitrate,
                    save_cover=save_cover,
                    market=market
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
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to,
                    bitrate=bitrate,
                    save_cover=save_cover,
                    market=market
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
                    real_time_dl=real_time_dl,
                    custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format,
                    pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay,
                    retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries,
                    convert_to=convert_to,
                    bitrate=bitrate,
                    save_cover=save_cover,
                    market=market
                )
                smart.type = "episode"
                smart.episode = episode

            return smart
        except Exception as e:
            logger.error(f"Failed to perform smart download: {str(e)}")
            traceback.print_exc()
            raise e
