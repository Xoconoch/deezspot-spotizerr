#!/usr/bin/python3
import os
import json
import logging
from deezspot.deezloader.dee_api import API
from deezspot.easy_spoty import Spo
from deezspot.deezloader.deegw_api import API_GW
from deezspot.deezloader.deezer_settings import stock_quality
from deezspot.models import (
    Track,
    Album,
    Playlist,
    Preferences,
    Smart,
    Episode,
)
from deezspot.deezloader.__download__ import (
    DW_TRACK,
    DW_ALBUM,
    DW_PLAYLIST,
    DW_EPISODE,
    Download_JOB,
)
from deezspot.exceptions import (
    InvalidLink,
    TrackNotFound,
    NoDataApi,
    AlbumNotFound,
    MarketAvailabilityError,
)
from deezspot.libutils.utils import (
    create_zip,
    get_ids,
    link_is_valid,
    what_kind
)
from deezspot.libutils.others_settings import (
    stock_output,
    stock_recursive_quality,
    stock_recursive_download,
    stock_not_interface,
    stock_zip,
    stock_save_cover,
    stock_market
)
from deezspot.libutils.logging_utils import ProgressReporter, logger, report_progress
import requests

API()

# Create a logger for the deezspot library
logger = logging.getLogger('deezspot')

class DeeLogin:
    def __init__(
        self,
        arl=None,
        email=None,
        password=None,
        spotify_client_id=None,
        spotify_client_secret=None,
        progress_callback=None,
        silent=False
    ) -> None:

        # Store Spotify credentials
        self.spotify_client_id = spotify_client_id
        self.spotify_client_secret = spotify_client_secret
        
        # Initialize Spotify API if credentials are provided
        if spotify_client_id and spotify_client_secret:
            Spo.__init__(client_id=spotify_client_id, client_secret=spotify_client_secret)

        # Initialize Deezer API
        if arl:
            self.__gw_api = API_GW(arl=arl)
        else:
            self.__gw_api = API_GW(
                email=email,
                password=password
            )
            
        # Reference to the Spotify search functionality
        self.__spo = Spo
        
        # Configure progress reporting
        self.progress_reporter = ProgressReporter(callback=progress_callback, silent=silent)
        
        # Set the progress reporter for Download_JOB
        Download_JOB.set_progress_reporter(self.progress_reporter)

    def download_trackdee(
        self, link_track,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Track:

        link_is_valid(link_track)
        ids = get_ids(link_track)
        song_metadata = None
        market_str = market
        if isinstance(market, list):
            market_str = ", ".join([m.upper() for m in market])
        elif isinstance(market, str):
            market_str = market.upper()

        try:
            song_metadata = API.tracking(ids, market=market)
        except MarketAvailabilityError as e:
            logger.error(f"Track {ids} is not available in market(s) '{market_str}'. Error: {e.message}")
            summary = {
                "successful_tracks": [], "skipped_tracks": [], "total_successful": 0, "total_skipped": 0, "total_failed": 1,
                "failed_tracks": [{"track": f"Track ID {ids}", "reason": str(e)}]
            }
            report_progress(
                reporter=self.progress_reporter,
                report_type="track",
                status="error",
                song="Unknown Track",
                artist="Unknown Artist",
                url=link_track,
                error=str(e),
                summary=summary
            )
            raise TrackNotFound(url=link_track, message=e.message) from e
        except NoDataApi:
            infos = self.__gw_api.get_song_data(ids)

            if not "FALLBACK" in infos:
                raise TrackNotFound(link_track)

            ids = infos['FALLBACK']['SNG_ID']
            try:
                song_metadata = API.tracking(ids, market=market)
            except MarketAvailabilityError as e:
                logger.error(f"Fallback track {ids} is not available in market(s) '{market_str}'. Error: {e.message}")
                raise TrackNotFound(url=link_track, message=e.message) from e
            except NoDataApi:
                 raise TrackNotFound(link_track)

        preferences = Preferences()
        preferences.link = link_track
        preferences.song_metadata = song_metadata
        preferences.quality_download = quality_download
        preferences.output_dir = output_dir
        preferences.ids = ids
        preferences.recursive_quality = recursive_quality
        preferences.recursive_download = recursive_download
        preferences.not_interface = not_interface
        preferences.custom_dir_format = custom_dir_format
        preferences.custom_track_format = custom_track_format
        preferences.pad_tracks = pad_tracks
        preferences.initial_retry_delay = initial_retry_delay
        preferences.retry_delay_increase = retry_delay_increase
        preferences.max_retries = max_retries
        preferences.convert_to = convert_to
        preferences.bitrate = bitrate
        preferences.save_cover = save_cover
        preferences.market = market

        try:
            track = DW_TRACK(preferences).dw()
            return track
        except Exception as e:
            logger.error(f"Failed to download track: {str(e)}")
            if song_metadata:
                track_info = {"name": song_metadata.get("music", "Unknown Track"), "artist": song_metadata.get("artist", "Unknown Artist")}
                summary = {
                    "successful_tracks": [], "skipped_tracks": [], "total_successful": 0, "total_skipped": 0, "total_failed": 1,
                    "failed_tracks": [{"track": f"{track_info['name']} - {track_info['artist']}", "reason": str(e)}]
                }
                report_progress(
                    reporter=self.progress_reporter,
                    report_type="track",
                    status="error",
                    song=track_info['name'],
                    artist=track_info['artist'],
                    url=link_track,
                    error=str(e),
                    summary=summary
                )
            raise e

    def download_albumdee(
        self, link_album,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Album:

        link_is_valid(link_album)
        ids = get_ids(link_album)
        album_json = None
        market_str = market
        if isinstance(market, list):
            market_str = ", ".join([m.upper() for m in market])
        elif isinstance(market, str):
            market_str = market.upper()

        try:
            album_json = API.get_album(ids)
        except NoDataApi:
            raise AlbumNotFound(link_album)

        song_metadata = API.tracking_album(album_json, market=market)

        preferences = Preferences()
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
        preferences.custom_dir_format = custom_dir_format
        preferences.custom_track_format = custom_track_format
        preferences.pad_tracks = pad_tracks
        preferences.initial_retry_delay = initial_retry_delay
        preferences.retry_delay_increase = retry_delay_increase
        preferences.max_retries = max_retries
        preferences.convert_to = convert_to
        preferences.bitrate = bitrate
        preferences.save_cover = save_cover
        preferences.market = market

        album = DW_ALBUM(preferences).dw()

        return album

    def download_playlistdee(
        self, link_playlist,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Playlist:

        link_is_valid(link_playlist)
        ids = get_ids(link_playlist)

        song_metadata = []
        playlist_json = API.get_playlist(ids)
        market_str_playlist = market
        if isinstance(market, list):
            market_str_playlist = ", ".join([m.upper() for m in market])
        elif isinstance(market, str):
            market_str_playlist = market.upper()

        for track in playlist_json['tracks']['data']:
            c_ids = track['id']
            c_song_metadata_item = None
            track_title_for_error = track.get('title', 'Unknown Track')
            track_artist_for_error = track.get('artist', {}).get('name', 'Unknown Artist')

            try:
                c_song_metadata_item = API.tracking(c_ids, market=market)
            except MarketAvailabilityError as e:
                logger.warning(f"Track '{track_title_for_error}' (ID: {c_ids}) in playlist not available in market(s) '{market_str_playlist}': {e.message}")
                c_song_metadata_item = {
                    'error_type': 'MarketAvailabilityError', 
                    'message': e.message, 
                    'name': track_title_for_error, 
                    'artist': track_artist_for_error, 
                    'ids': c_ids,
                    'checked_markets': market_str_playlist
                }
            except NoDataApi:
                infos = self.__gw_api.get_song_data(c_ids)
                if not "FALLBACK" in infos:
                    logger.warning(f"Track '{track_title_for_error}' (ID: {c_ids}) in playlist not found on Deezer and no fallback.")
                    c_song_metadata_item = {
                        'error_type': 'NoDataApi', 
                        'message': f"Track {track_title_for_error} - {track_artist_for_error} (ID: {c_ids}) not found.",
                        'name': track_title_for_error, 
                        'artist': track_artist_for_error, 
                        'ids': c_ids
                    }
                else:
                    fallback_ids = infos['FALLBACK']['SNG_ID']
                    try:
                        c_song_metadata_item = API.tracking(fallback_ids, market=market)
                    except MarketAvailabilityError as e_fallback:
                        logger.warning(f"Fallback track (Original ID: {c_ids}, Fallback ID: {fallback_ids}) for '{track_title_for_error}' in playlist not available in market(s) '{market_str_playlist}': {e_fallback.message}")
                        c_song_metadata_item = {
                            'error_type': 'MarketAvailabilityError', 
                            'message': e_fallback.message, 
                            'name': track_title_for_error, 
                            'artist': track_artist_for_error, 
                            'ids': fallback_ids,
                            'checked_markets': market_str_playlist
                        }
                    except NoDataApi:
                        logger.warning(f"Fallback track (Original ID: {c_ids}, Fallback ID: {fallback_ids}) for '{track_title_for_error}' in playlist also not found on Deezer.")
                        c_song_metadata_item = {
                            'error_type': 'NoDataApi', 
                            'message': f"Fallback for track {track_title_for_error} (ID: {fallback_ids}) also not found.",
                            'name': track_title_for_error, 
                            'artist': track_artist_for_error, 
                            'ids': fallback_ids
                        }
                    except requests.exceptions.ConnectionError as e_conn_fallback:
                        logger.warning(f"Connection error fetching metadata for fallback track (Original ID: {c_ids}, Fallback ID: {fallback_ids}) for '{track_title_for_error}' in playlist: {str(e_conn_fallback)}")
                        c_song_metadata_item = {
                            'error_type': 'ConnectionError',
                            'message': f"Connection error on fallback: {str(e_conn_fallback)}",
                            'name': track_title_for_error,
                            'artist': track_artist_for_error,
                            'ids': fallback_ids
                        }
            except requests.exceptions.ConnectionError as e_conn:
                logger.warning(f"Connection error fetching metadata for track '{track_title_for_error}' (ID: {c_ids}) in playlist: {str(e_conn)}")
                c_song_metadata_item = {
                    'error_type': 'ConnectionError',
                    'message': f"Connection error: {str(e_conn)}",
                    'name': track_title_for_error,
                    'artist': track_artist_for_error,
                    'ids': c_ids
                }
            except Exception as e_other_metadata:
                logger.warning(f"Unexpected error fetching metadata for track '{track_title_for_error}' (ID: {c_ids}) in playlist: {str(e_other_metadata)}")
                c_song_metadata_item = {
                    'error_type': 'MetadataError',
                    'message': str(e_other_metadata),
                    'name': track_title_for_error,
                    'artist': track_artist_for_error,
                    'ids': c_ids
                }
            
            song_metadata.append(c_song_metadata_item)

        preferences = Preferences()
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
        preferences.custom_dir_format = custom_dir_format
        preferences.custom_track_format = custom_track_format
        preferences.pad_tracks = pad_tracks
        preferences.initial_retry_delay = initial_retry_delay
        preferences.retry_delay_increase = retry_delay_increase
        preferences.max_retries = max_retries
        preferences.convert_to = convert_to
        preferences.bitrate = bitrate
        preferences.save_cover = save_cover
        preferences.market = market

        playlist = DW_PLAYLIST(preferences).dw()

        return playlist

    def download_artisttopdee(
        self, link_artist,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> list[Track]:

        link_is_valid(link_artist)
        ids = get_ids(link_artist)

        playlist_json = API.get_artist_top_tracks(ids)['data']

        names = [
            self.download_trackdee(
                track['link'], output_dir,
                quality_download, recursive_quality,
                recursive_download, not_interface,
                custom_dir_format=custom_dir_format,
                custom_track_format=custom_track_format,
                pad_tracks=pad_tracks,
                convert_to=convert_to,
                bitrate=bitrate,
                save_cover=save_cover,
                market=market
            )
            for track in playlist_json
        ]

        return names

    def convert_spoty_to_dee_link_track(self, link_track):
        link_is_valid(link_track)
        ids = get_ids(link_track)

        # Use stored credentials for API calls
        track_json = Spo.get_track(ids)
        external_ids = track_json.get('external_ids')

        if not external_ids or 'isrc' not in external_ids:
            msg = f"⚠ The track '{track_json.get('name', 'Unknown Track')}' has no ISRC and can't be converted to Deezer link :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(
                url=link_track,
                message=msg
            )

        isrc_code = external_ids['isrc']
        # Use the helper method
        try:
            return self.convert_isrc_to_dee_link_track(isrc_code)
        except TrackNotFound as e:
            logger.error(f"Failed to convert Spotify track {link_track} (ISRC: {isrc_code}) to Deezer link: {e.message}")
            # Re-raise with the original link_track for context
            raise TrackNotFound(url=link_track, message=f"Failed to find Deezer equivalent for ISRC {isrc_code} from Spotify track {link_track}: {e.message}") from e

    def convert_isrc_to_dee_link_track(self, isrc_code: str) -> str:

        if not isinstance(isrc_code, str) or not isrc_code:
            raise ValueError("ISRC code must be a non-empty string.")

        isrc_query = f"isrc:{isrc_code}"
        logger.debug(f"Attempting Deezer track search with ISRC query: {isrc_query}")

        try:
            track_json_dee = API.get_track(isrc_query)
        except NoDataApi:
            msg = f"⚠ The track with ISRC \"{isrc_code}\" can't be found on Deezer :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(
                # Passing the ISRC as 'url' for consistency, though it's not a URL
                url=f"isrc:{isrc_code}",
                message=msg
            )
        
        if not track_json_dee or 'link' not in track_json_dee:
            msg = f"⚠ Deezer API returned no link for ISRC \"{isrc_code}\" :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(
                url=f"isrc:{isrc_code}",
                message=msg
            )

        track_link_dee = track_json_dee['link']
        logger.info(f"Successfully converted ISRC {isrc_code} to Deezer link: {track_link_dee}")
        return track_link_dee

    def convert_spoty_to_dee_link_album(self, link_album):
        link_is_valid(link_album)
        ids = get_ids(link_album)
        link_dee = None

        spotify_album_data = Spo.get_album(ids)

        # Method 1: Try UPC
        try:
            external_ids = spotify_album_data.get('external_ids')
            if external_ids and 'upc' in external_ids:
                upc_base = str(external_ids['upc']).lstrip('0')
                if upc_base:
                    logger.debug(f"Attempting Deezer album search with UPC: {upc_base}")
                    try:
                        deezer_album_info = API.get_album(f"upc:{upc_base}")
                        if isinstance(deezer_album_info, dict) and 'link' in deezer_album_info:
                            link_dee = deezer_album_info['link']
                            logger.info(f"Found Deezer album via UPC: {link_dee}")
                    except NoDataApi:
                        logger.debug(f"No Deezer album found for UPC: {upc_base}")
                    except Exception as e_upc_search:
                        logger.warning(f"Error during Deezer API call for UPC {upc_base}: {e_upc_search}")
            else:
                logger.debug("No UPC found in Spotify data for album link conversion.")
        except Exception as e_upc_block:
            logger.error(f"Error processing UPC for album {link_album}: {e_upc_block}")

        # Method 2: Try ISRC if UPC failed
        if not link_dee:
            logger.debug(f"UPC method failed or skipped for {link_album}. Attempting ISRC method.")
            try:
                spotify_total_tracks = spotify_album_data.get('total_tracks')
                spotify_tracks_items = spotify_album_data.get('tracks', {}).get('items', [])

                if not spotify_tracks_items:
                    logger.warning(f"No track items in Spotify data for {link_album} to attempt ISRC lookup.")
                else:
                    for track_item in spotify_tracks_items:
                        try:
                            track_spotify_link = track_item.get('external_urls', {}).get('spotify')
                            if not track_spotify_link: continue

                            spotify_track_info = Spo.get_track(track_spotify_link)
                            isrc_value = spotify_track_info.get('external_ids', {}).get('isrc')
                            if not isrc_value: continue
                            
                            logger.debug(f"Attempting Deezer track search with ISRC: {isrc_value}")
                            deezer_track_info = API.get_track(f"isrc:{isrc_value}")

                            if isinstance(deezer_track_info, dict) and 'album' in deezer_track_info:
                                deezer_album_preview = deezer_track_info['album']
                                if isinstance(deezer_album_preview, dict) and 'id' in deezer_album_preview:
                                    deezer_album_id = deezer_album_preview['id']
                                    full_deezer_album_info = API.get_album(deezer_album_id)
                                    if (
                                        isinstance(full_deezer_album_info, dict) and
                                        full_deezer_album_info.get('nb_tracks') == spotify_total_tracks and
                                        'link' in full_deezer_album_info
                                    ):
                                        link_dee = full_deezer_album_info['link']
                                        logger.info(f"Found Deezer album via ISRC ({isrc_value}): {link_dee}")
                                        break  # Found a matching album, exit track loop
                        except NoDataApi:
                            logger.debug(f"No Deezer track/album found for ISRC: {isrc_value}")
                            # Continue to the next track's ISRC
                        except Exception as e_isrc_track_search:
                            logger.warning(f"Error during Deezer search for ISRC {isrc_value}: {e_isrc_track_search}")
                            # Continue to the next track's ISRC
                    if not link_dee: # If loop finished and no link found via ISRC
                        logger.warning(f"ISRC method completed for {link_album}, but no matching Deezer album found.")
            except Exception as e_isrc_block:
                logger.error(f"Error during ISRC processing block for {link_album}: {e_isrc_block}")

        if not link_dee:
            raise AlbumNotFound(f"Failed to convert Spotify album link {link_album} to a Deezer link after all attempts.")

        return link_dee

    def _convert_upc_to_dee_link_album(self, upc_code: str) -> str | None:
        """Helper to find Deezer album by UPC."""
        if not upc_code:
            return None
        logger.debug(f"Attempting Deezer album search with UPC: {upc_code}")
        try:
            deezer_album_info = API.get_album(f"upc:{upc_code}")
            if isinstance(deezer_album_info, dict) and 'link' in deezer_album_info:
                link_dee = deezer_album_info['link']
                logger.info(f"Found Deezer album via UPC ({upc_code}): {link_dee}")
                return link_dee
        except NoDataApi:
            logger.debug(f"No Deezer album found for UPC: {upc_code}")
        except Exception as e_upc_search:
            logger.warning(f"Error during Deezer API call for UPC {upc_code}: {e_upc_search}")
        return None

    def _convert_isrc_to_dee_link_album(self, isrc_code: str, spotify_album_name_for_log: str, spotify_total_tracks: int) -> str | None:
        """Helper to find Deezer album by ISRC, matching track count."""
        if not isrc_code:
            return None
        logger.debug(f"For Spotify album '{spotify_album_name_for_log}', attempting Deezer track search with ISRC: {isrc_code} for album matching")
        try:
            deezer_track_info = API.get_track(f"isrc:{isrc_code}")
            if isinstance(deezer_track_info, dict) and 'album' in deezer_track_info:
                deezer_album_preview = deezer_track_info['album']
                if isinstance(deezer_album_preview, dict) and 'id' in deezer_album_preview:
                    deezer_album_id = deezer_album_preview['id']
                    # Now fetch the full album details to check track count
                    full_deezer_album_info = API.get_album(deezer_album_id)
                    if (
                        isinstance(full_deezer_album_info, dict) and
                        full_deezer_album_info.get('nb_tracks') == spotify_total_tracks and
                        'link' in full_deezer_album_info
                    ):
                        link_dee = full_deezer_album_info['link']
                        logger.info(f"Found matching Deezer album for '{spotify_album_name_for_log}' via ISRC ({isrc_code}). Spotify tracks: {spotify_total_tracks}, Deezer tracks: {full_deezer_album_info.get('nb_tracks')}. Link: {link_dee}")
                        return link_dee
                    else:
                        logger.debug(f"Deezer album (ID: {deezer_album_id}, Title: {full_deezer_album_info.get('title', 'N/A') if isinstance(full_deezer_album_info, dict) else 'N/A'}) found via ISRC {isrc_code} for Spotify album '{spotify_album_name_for_log}', but track count mismatch or no link. Spotify tracks: {spotify_total_tracks}, Deezer tracks: {full_deezer_album_info.get('nb_tracks') if isinstance(full_deezer_album_info, dict) else 'N/A'}")
        except NoDataApi:
            logger.debug(f"No Deezer track (and thus no album context) found for ISRC: {isrc_code} during album search for '{spotify_album_name_for_log}'.")
        except Exception as e_isrc_search:
            logger.warning(f"Error during Deezer search for ISRC {isrc_code} for album matching for '{spotify_album_name_for_log}': {e_isrc_search}")
        return None

    def download_trackspo(
        self, link_track,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Track:

        link_dee = self.convert_spoty_to_dee_link_track(link_track)

        track = self.download_trackdee(
            link_dee,
            output_dir=output_dir,
            quality_download=quality_download,
            recursive_quality=recursive_quality,
            recursive_download=recursive_download,
            not_interface=not_interface,
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

        return track

    def download_albumspo(
        self, link_album,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Album:

        link_dee = self.convert_spoty_to_dee_link_album(link_album)

        album = self.download_albumdee(
            link_dee, output_dir,
            quality_download, recursive_quality,
            recursive_download, not_interface,
            make_zip, 
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

        return album

    def download_playlistspo(
        self, link_playlist,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Playlist:

        link_is_valid(link_playlist)
        ids = get_ids(link_playlist)

        # Use stored credentials for API calls
        playlist_json = Spo.get_playlist(ids)
        playlist_name = playlist_json['name']
        playlist_owner = playlist_json.get('owner', {}).get('display_name', 'Unknown Owner')
        total_tracks = playlist_json['tracks']['total']
        playlist_tracks = playlist_json['tracks']['items']
        playlist = Playlist()
        tracks = playlist.tracks

        # Initializing status - replaced print with report_progress
        report_progress(
            reporter=self.progress_reporter,
            report_type="playlist",
            status="initializing",
            name=playlist_name,
            owner=playlist_owner,
            total_tracks=total_tracks,
            url=link_playlist
        )

        for index, item in enumerate(playlist_tracks, 1):
            is_track = item.get('track')
            if not is_track:
                continue

            track_info = is_track
            track_name = track_info.get('name', 'Unknown Track')
            artists = track_info.get('artists', [])
            artist_name = artists[0]['name'] if artists else 'Unknown Artist'

            external_urls = track_info.get('external_urls', {})
            if not external_urls:
                logger.warning(f"The track \"{track_name}\" is not available on Spotify :(")
                continue

            link_track = external_urls['spotify']

            try:
                # Download each track individually via the Spotify-to-Deezer conversion method.
                downloaded_track = self.download_trackspo(
                    link_track,
                    output_dir=output_dir,
                    quality_download=quality_download,
                    recursive_quality=recursive_quality,
                    recursive_download=recursive_download,
                    not_interface=not_interface,
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
                tracks.append(downloaded_track)
            except (TrackNotFound, NoDataApi) as e:
                logger.error(f"Failed to download track: {track_name} - {artist_name}")
                tracks.append(f"{track_name} - {artist_name}")

        # Done status
        successful_tracks_list = []
        failed_tracks_list = []
        skipped_tracks_list = []
        for track in tracks:
            if isinstance(track, Track):
                track_info = {
                    "name": track.tags.get('music', 'Unknown Track'),
                    "artist": track.tags.get('artist', 'Unknown Artist')
                }
                if getattr(track, 'was_skipped', False):
                    skipped_tracks_list.append(f"{track_info['name']} - {track_info['artist']}")
                elif track.success:
                    successful_tracks_list.append(f"{track_info['name']} - {track_info['artist']}")
                else:
                    failed_tracks_list.append({
                        "track": f"{track_info['name']} - {track_info['artist']}",
                        "reason": getattr(track, 'error_message', 'Unknown reason')
                    })
            elif isinstance(track, str): # It can be a string for failed tracks
                failed_tracks_list.append({
                    "track": track,
                    "reason": "Failed to download or convert."
                })

        summary = {
            "successful_tracks": successful_tracks_list,
            "skipped_tracks": skipped_tracks_list,
            "failed_tracks": failed_tracks_list,
            "total_successful": len(successful_tracks_list),
            "total_skipped": len(skipped_tracks_list),
            "total_failed": len(failed_tracks_list),
        }

        report_progress(
            reporter=self.progress_reporter,
            report_type="playlist",
            status="done",
            name=playlist_name,
            owner=playlist_owner,
            total_tracks=total_tracks,
            url=link_playlist,
            summary=summary
        )

        # === New m3u File Creation Section ===
        # Create a subfolder "playlists" inside the output directory
        playlist_m3u_dir = os.path.join(output_dir, "playlists")
        os.makedirs(playlist_m3u_dir, exist_ok=True)
        # The m3u file will be named after the playlist (e.g. "MyPlaylist.m3u")
        m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name}.m3u")
        with open(m3u_path, "w", encoding="utf-8") as m3u_file:
            # Write the m3u header
            m3u_file.write("#EXTM3U\n")
            # Append each successfully downloaded track's relative path
            for track in tracks:
                if isinstance(track, Track) and track.success and hasattr(track, 'song_path') and track.song_path:
                    # Calculate the relative path from the m3u folder to the track file
                    relative_song_path = os.path.relpath(track.song_path, start=playlist_m3u_dir)
                    m3u_file.write(f"{relative_song_path}\n")
        logger.info(f"Created m3u playlist file at: {m3u_path}")
        # === End m3u File Creation Section ===

        if make_zip:
            playlist_name = playlist_json['name']
            zip_name = f"{output_dir}playlist {playlist_name}.zip"
            create_zip(tracks, zip_name=zip_name)
            playlist.zip_path = zip_name

        return playlist

    def download_name(
        self, artist, song,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        custom_dir_format=None,
        custom_track_format=None,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        pad_tracks=True,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Track:

        query = f"track:{song} artist:{artist}"
        # Use the stored credentials when searching
        search = self.__spo.search(
            query, 
            client_id=self.spotify_client_id, 
            client_secret=self.spotify_client_secret
        ) if not self.__spo._Spo__initialized else self.__spo.search(query)
        
        items = search['tracks']['items']

        if len(items) == 0:
            msg = f"No result for {query} :("
            raise TrackNotFound(message=msg)

        link_track = items[0]['external_urls']['spotify']

        track = self.download_trackspo(
            link_track,
            output_dir=output_dir,
            quality_download=quality_download,
            recursive_quality=recursive_quality,
            recursive_download=recursive_download,
            not_interface=not_interface,
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

        return track

    def download_episode(
        self,
        link_episode,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Episode:
        
        link_is_valid(link_episode)
        ids = get_ids(link_episode)
        episode_metadata = None
        market_str_episode = market
        if isinstance(market, list):
            market_str_episode = ", ".join([m.upper() for m in market])
        elif isinstance(market, str):
            market_str_episode = market.upper()
        
        try:
            episode_metadata = API.tracking(ids, market=market)
        except MarketAvailabilityError as e:
            logger.error(f"Episode {ids} is not available in market(s) '{market_str_episode}'. Error: {e.message}")
            # For episodes, structure of error might be different than TrackNotFound expects if it uses track-specific fields
            # Creating a message that TrackNotFound can use
            raise TrackNotFound(url=link_episode, message=f"Episode not available in market(s) '{market_str_episode}': {e.message}") from e
        except NoDataApi:
            infos = self.__gw_api.get_episode_data(ids)
            if not infos:
                raise TrackNotFound(f"Episode {ids} not found")
            # For episodes, API.tracking is usually not called again with GW API data in this flow.
            # We construct metadata directly.
            # No direct market check here as available_countries might not be in GW response for episodes.
            # The initial API.tracking call is the main point for market check for episodes.
            episode_metadata = {
                'music': infos.get('EPISODE_TITLE', ''),
                'artist': infos.get('SHOW_NAME', ''),
                'album': infos.get('SHOW_NAME', ''),
                'date': infos.get('EPISODE_PUBLISHED_TIMESTAMP', '').split()[0],
                'genre': 'Podcast',
                'explicit': infos.get('SHOW_IS_EXPLICIT', '2'),
                'disc': 1,
                'track': 1,
                'duration': int(infos.get('DURATION', 0)),
                'isrc': None,
                'image': infos.get('EPISODE_IMAGE_MD5', '')
            }

        preferences = Preferences()
        preferences.link = link_episode
        preferences.song_metadata = episode_metadata
        preferences.quality_download = quality_download
        preferences.output_dir = output_dir
        preferences.ids = ids
        preferences.recursive_quality = recursive_quality
        preferences.recursive_download = recursive_download
        preferences.not_interface = not_interface
        # No convert_to for episode download (and preferences.convert_to is not set here)
        preferences.max_retries = max_retries
        # Audio conversion parameters
        preferences.convert_to = convert_to
        preferences.bitrate = bitrate
        preferences.save_cover = save_cover
        preferences.is_episode = True
        preferences.market = market

        episode = DW_EPISODE(preferences).dw()

        return episode
    
    def download_smart(
        self, link,
        output_dir=stock_output,
        quality_download=stock_quality,
        recursive_quality=stock_recursive_quality,
        recursive_download=stock_recursive_download,
        not_interface=stock_not_interface,
        make_zip=stock_zip,
        custom_dir_format=None,
        custom_track_format=None,
        pad_tracks=True,
        initial_retry_delay=30,
        retry_delay_increase=30,
        max_retries=5,
        convert_to=None,
        bitrate=None,
        save_cover=stock_save_cover,
        market=stock_market
    ) -> Smart:

        link_is_valid(link)
        link = what_kind(link)
        smart = Smart()

        if "spotify.com" in link:
            source = "https://spotify.com"
        elif "deezer.com" in link:
            source = "https://deezer.com"

        smart.source = source
        
        # Add progress reporting for the smart downloader
        self.progress_reporter.report({
            "status": "initializing",
            "type": "smart_download",
            "link": link,
            "source": source
        })

        if "track/" in link:
            if "spotify.com" in link:
                func = self.download_trackspo
            elif "deezer.com" in link:
                func = self.download_trackdee
            else:
                raise InvalidLink(link)

            track = func(
                link,
                output_dir=output_dir,
                quality_download=quality_download,
                recursive_quality=recursive_quality,
                recursive_download=recursive_download,
                not_interface=not_interface,
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
            if "spotify.com" in link:
                func = self.download_albumspo
            elif "deezer.com" in link:
                func = self.download_albumdee
            else:
                raise InvalidLink(link)

            album = func(
                link,
                output_dir=output_dir,
                quality_download=quality_download,
                recursive_quality=recursive_quality,
                recursive_download=recursive_download,
                not_interface=not_interface,
                make_zip=make_zip,
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
            if "spotify.com" in link:
                func = self.download_playlistspo
            elif "deezer.com" in link:
                func = self.download_playlistdee
            else:
                raise InvalidLink(link)

            playlist = func(
                link,
                output_dir=output_dir,
                quality_download=quality_download,
                recursive_quality=recursive_quality,
                recursive_download=recursive_download,
                not_interface=not_interface,
                make_zip=make_zip,
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
            
        # Report completion
        self.progress_reporter.report({
            "status": "done",
            "type": "smart_download",
            "source": source,
            "content_type": smart.type
        })

        return smart
