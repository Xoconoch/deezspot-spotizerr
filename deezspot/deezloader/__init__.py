#!/usr/bin/python3
import os
import json
import logging
from deezspot.deezloader.dee_api import API
from deezspot.easy_spoty import Spo
from deezspot.deezloader.deegw_api import API_GW
from deezspot.deezloader.deezer_settings import stock_quality
from deezspot.models.download import (
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
    what_kind,
    sanitize_name
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

from deezspot.models.callback.callbacks import (
    trackCallbackObject,
    albumCallbackObject,
    playlistCallbackObject,
    errorObject,
    summaryObject,
    failedTrackObject,
    initializingObject,
    doneObject,
)
from deezspot.models.callback.track import trackObject as trackCbObject, artistTrackObject
from deezspot.models.callback.album import albumObject as albumCbObject
from deezspot.models.callback.playlist import playlistObject as playlistCbObject
from deezspot.models.callback.common import IDs
from deezspot.models.callback.user import userObject


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
        market=stock_market,
        playlist_context=None
    ) -> Track:

        link_is_valid(link_track)
        ids = get_ids(link_track)
        track_obj = None

        def report_error(e, current_ids, url):
            error_status = errorObject(ids=IDs(deezer=current_ids), error=str(e))
            summary = summaryObject(
                failed_tracks=[failedTrackObject(track=trackCbObject(title=f"Track ID {current_ids}"), reason=str(e))],
                total_failed=1
            )
            error_status.summary = summary
            callback_obj = trackCallbackObject(
                track=trackCbObject(title=f"Track ID {current_ids}", ids=IDs(deezer=current_ids)),
                status_info=error_status
            )
            report_progress(reporter=self.progress_reporter, callback_obj=callback_obj)

        try:
            # Get standardized track object using our enhanced API module
            track_obj = API.get_track(ids)
        except (NoDataApi, MarketAvailabilityError) as e:
            # Try to get fallback track information
            infos = self.__gw_api.get_song_data(ids)
            if "FALLBACK" not in infos:
                report_error(e, ids, link_track)
                raise TrackNotFound(link_track) from e

            fallback_id = infos['FALLBACK']['SNG_ID']
            try:
                # Try again with fallback ID
                track_obj = API.get_track(fallback_id)
                if not track_obj or not track_obj.available:
                    raise MarketAvailabilityError(f"Fallback track {fallback_id} not available.")
                # Update the ID to use the fallback
                ids = fallback_id
            except (NoDataApi, MarketAvailabilityError) as e_fallback:
                report_error(e_fallback, fallback_id, link_track)
                raise TrackNotFound(url=link_track, message=str(e_fallback)) from e_fallback
        
        if not track_obj:
            e = TrackNotFound(f"Could not retrieve track metadata for {link_track}")
            report_error(e, ids, link_track)
            raise e

        # Set up download preferences
        preferences = Preferences()
        preferences.link = link_track
        preferences.song_metadata = track_obj  # Use our standardized track object
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

        if playlist_context:
            preferences.json_data = playlist_context['json_data']
            preferences.track_number = playlist_context['track_number']
            preferences.total_tracks = playlist_context['total_tracks']
            preferences.spotify_url = playlist_context['spotify_url']

        try:
            parent = 'playlist' if playlist_context else None
            track = DW_TRACK(preferences, parent=parent).dw()
            return track
        except Exception as e:
            logger.error(f"Failed to download track: {str(e)}")
            report_error(e, ids, link_track)
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
        market=stock_market,
        playlist_context=None
    ) -> Album:

        link_is_valid(link_album)
        ids = get_ids(link_album)

        def report_error(e, current_ids, url):
            error_status = errorObject(ids=IDs(deezer=current_ids), error=str(e))
            callback_obj = albumCallbackObject(
                album=albumCbObject(title=f"Album ID {current_ids}", ids=IDs(deezer=current_ids)),
                status_info=error_status
            )
            report_progress(reporter=self.progress_reporter, callback_obj=callback_obj)

        try:
            # Get standardized album object
            album_obj = API.get_album(ids)
            if not album_obj:
                e = AlbumNotFound(f"Could not retrieve album metadata for {link_album}")
                report_error(e, ids, link_album)
                raise e
        except NoDataApi as e:
            report_error(e, ids, link_album)
            raise AlbumNotFound(link_album) from e

        # Set up download preferences
        preferences = Preferences()
        preferences.link = link_album
        preferences.song_metadata = album_obj  # Using the standardized album object
        preferences.quality_download = quality_download
        preferences.output_dir = output_dir
        preferences.ids = ids
        preferences.json_data = album_obj  # Pass the complete album object
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

        if playlist_context:
            preferences.json_data = playlist_context['json_data']
            preferences.track_number = playlist_context['track_number']
            preferences.total_tracks = playlist_context['total_tracks']
            preferences.spotify_url = playlist_context['spotify_url']

        try:
            album = DW_ALBUM(preferences).dw()
            return album
        except Exception as e:
            logger.error(f"Failed to download album: {str(e)}")
            report_error(e, ids, link_album)
            raise e

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

        playlist_obj = API.get_playlist(ids)
        if not playlist_obj:
            raise NoDataApi(f"Playlist {ids} not found.")

        # This part of fetching metadata track by track is now handled in __download__.py
        # The logic here is simplified to pass the full playlist object.

        preferences = Preferences()
        preferences.link = link_playlist
        # preferences.song_metadata is not needed here, DW_PLAYLIST will use json_data
        preferences.quality_download = quality_download
        preferences.output_dir = output_dir
        preferences.ids = ids
        preferences.json_data = playlist_obj
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

        # Assuming get_artist_top_tracks returns a list of track-like dicts with a 'link'
        top_tracks_json = API.get_artist_top_tracks(ids)['data']

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
            for track in top_tracks_json
        ]

        return names

    def convert_spoty_to_dee_link_track(self, link_track):
        link_is_valid(link_track)
        ids = get_ids(link_track)

        track_json = Spo.get_track(ids)
        external_ids = track_json.get('external_ids')

        if not external_ids or 'isrc' not in external_ids:
            msg = f"⚠ The track '{track_json.get('name', 'Unknown Track')}' has no ISRC and can't be converted to Deezer link :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(url=link_track, message=msg)

        isrc_code = external_ids['isrc']
        try:
            return self.convert_isrc_to_dee_link_track(isrc_code)
        except TrackNotFound as e:
            logger.error(f"Failed to convert Spotify track {link_track} (ISRC: {isrc_code}) to Deezer link: {e.message}")
            raise TrackNotFound(url=link_track, message=f"Failed to find Deezer equivalent for ISRC {isrc_code} from Spotify track {link_track}: {e.message}") from e

    def convert_isrc_to_dee_link_track(self, isrc_code: str) -> str:
        if not isinstance(isrc_code, str) or not isrc_code:
            raise ValueError("ISRC code must be a non-empty string.")

        isrc_query = f"isrc:{isrc_code}"
        logger.debug(f"Attempting Deezer track search with ISRC query: {isrc_query}")

        try:
            track_obj = API.get_track(isrc_query)
        except NoDataApi:
            msg = f"⚠ The track with ISRC '{isrc_code}' can't be found on Deezer :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(url=f"isrc:{isrc_code}", message=msg)
        
        if not track_obj or not track_obj.type or not track_obj.ids or not track_obj.ids.deezer:
            msg = f"⚠ Deezer API returned no link for ISRC '{isrc_code}' :( ⚠"
            logger.warning(msg)
            raise TrackNotFound(url=f"isrc:{isrc_code}", message=msg)

        track_link_dee = f"https://www.deezer.com/{track_obj.type}/{track_obj.ids.deezer}"
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
                        deezer_album_obj = API.get_album(f"upc:{upc_base}")
                        if deezer_album_obj and deezer_album_obj.type and deezer_album_obj.ids and deezer_album_obj.ids.deezer:
                            link_dee = f"https://www.deezer.com/{deezer_album_obj.type}/{deezer_album_obj.ids.deezer}"
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
                            deezer_track_obj = API.get_track(f"isrc:{isrc_value}")

                            if deezer_track_obj and deezer_track_obj.album and deezer_track_obj.album.ids.deezer:
                                deezer_album_id = deezer_track_obj.album.ids.deezer
                                full_deezer_album_obj = API.get_album(deezer_album_id)
                                if (full_deezer_album_obj and
                                    full_deezer_album_obj.total_tracks == spotify_total_tracks and
                                    full_deezer_album_obj.type and full_deezer_album_obj.ids and full_deezer_album_obj.ids.deezer):
                                    link_dee = f"https://www.deezer.com/{full_deezer_album_obj.type}/{full_deezer_album_obj.ids.deezer}"
                                    logger.info(f"Found Deezer album via ISRC ({isrc_value}): {link_dee}")
                                    break
                        except NoDataApi:
                            logger.debug(f"No Deezer track/album found for ISRC: {isrc_value}")
                        except Exception as e_isrc_track_search:
                            logger.warning(f"Error during Deezer search for ISRC {isrc_value}: {e_isrc_track_search}")
                    if not link_dee:
                        logger.warning(f"ISRC method completed for {link_album}, but no matching Deezer album found.")
            except Exception as e_isrc_block:
                logger.error(f"Error during ISRC processing block for {link_album}: {e_isrc_block}")

        if not link_dee:
            raise AlbumNotFound(f"Failed to convert Spotify album link {link_album} to a Deezer link after all attempts.")

        return link_dee

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
        market=stock_market,
        playlist_context=None
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
            market=market,
            playlist_context=playlist_context
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
        market=stock_market,
        playlist_context=None
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
            market=market,
            playlist_context=playlist_context
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

        playlist_json = Spo.get_playlist(ids)
        
        # Extract track metadata for playlist callback object
        playlist_tracks_for_callback = []
        for item in playlist_json['tracks']['items']:
            if not item.get('track'):
                continue
            
            track_info = item['track']
            
            # Import the correct playlist-specific objects
            from deezspot.models.callback.playlist import (
                artistTrackPlaylistObject, 
                albumTrackPlaylistObject,
                trackPlaylistObject
            )
            
            # Create artists with proper type
            track_artists = [artistTrackPlaylistObject(
                name=artist['name'],
                ids=IDs(spotify=artist.get('id'))
            ) for artist in track_info.get('artists', [])]
            
            # Process album with proper type and include images
            album_info = track_info.get('album', {})
            album_images = []
            if album_info.get('images'):
                album_images = [
                    {"url": img.get('url'), "height": img.get('height'), "width": img.get('width')}
                    for img in album_info.get('images', [])
                ]
            
            # Process album artists
            album_artists = []
            if album_info.get('artists'):
                from deezspot.models.callback.playlist import artistAlbumTrackPlaylistObject
                album_artists = [
                    artistAlbumTrackPlaylistObject(
                        name=artist.get('name'),
                        ids=IDs(spotify=artist.get('id'))
                    )
                    for artist in album_info.get('artists', [])
                ]
            
            album_obj = albumTrackPlaylistObject(
                title=album_info.get('name', 'Unknown Album'),
                ids=IDs(spotify=album_info.get('id')),
                images=album_images,
                artists=album_artists,
                album_type=album_info.get('album_type', ''),
                release_date={
                    "year": int(album_info.get('release_date', '0').split('-')[0]) if album_info.get('release_date') else 0,
                    "month": int(album_info.get('release_date', '0-0').split('-')[1]) if album_info.get('release_date') and len(album_info.get('release_date').split('-')) > 1 else 0,
                    "day": int(album_info.get('release_date', '0-0-0').split('-')[2]) if album_info.get('release_date') and len(album_info.get('release_date').split('-')) > 2 else 0
                },
                total_tracks=album_info.get('total_tracks', 0)
            )
            
            # Create track with proper playlist-specific type
            track_obj = trackPlaylistObject(
                title=track_info.get('name', 'Unknown Track'),
                artists=track_artists,
                album=album_obj,
                duration_ms=track_info.get('duration_ms', 0),
                explicit=track_info.get('explicit', False),
                ids=IDs(
                    spotify=track_info.get('id'), 
                    isrc=track_info.get('external_ids', {}).get('isrc')
                ),
                disc_number=track_info.get('disc_number', 1),
                track_number=track_info.get('track_number', 0)
            )
            playlist_tracks_for_callback.append(track_obj)
        
        playlist_obj = playlistCbObject(
            title=playlist_json['name'],
            owner=userObject(name=playlist_json.get('owner', {}).get('display_name', 'Unknown Owner')),
            ids=IDs(spotify=playlist_json['id']),
            tracks=playlist_tracks_for_callback  # Populate tracks array with track objects
        )

        status_obj_init = initializingObject(ids=playlist_obj.ids)
        callback_obj_init = playlistCallbackObject(playlist=playlist_obj, status_info=status_obj_init)
        report_progress(reporter=self.progress_reporter, callback_obj=callback_obj_init)

        total_tracks = playlist_json['tracks']['total']
        playlist_tracks = playlist_json['tracks']['items']
        playlist = Playlist()
        tracks = playlist.tracks

        successful_tracks_cb = []
        failed_tracks_cb = []
        skipped_tracks_cb = []

        for index, item in enumerate(playlist_tracks, 1):
            is_track = item.get('track')
            if not is_track:
                logger.warning(f"Skipping an item in playlist {playlist_obj.title} as it's not a valid track (likely unavailable in region).")
                unknown_track = trackCbObject(title="Unknown Skipped Item", artists=[artistTrackObject(name="")])
                reason = "Playlist item was not a valid track object or is not available in your region."
                
                failed_tracks_cb.append(failedTrackObject(track=unknown_track, reason=reason))
                
                # Create a placeholder for the failed item
                failed_track = Track(
                    tags={'music': 'Unknown Skipped Item', 'artist': 'Unknown'},
                    song_path=None, file_format=None, quality=None, link=None, ids=None
                )
                failed_track.success = False
                failed_track.error_message = reason
                tracks.append(failed_track)
                continue

            track_info = is_track
            track_name = track_info.get('name', 'Unknown Track')
            artist_name = track_info['artists'][0]['name'] if track_info.get('artists') else 'Unknown Artist'
            link_track = track_info.get('external_urls', {}).get('spotify')

            if not link_track:
                logger.warning(f"The track \"{track_name}\" is not available on Spotify :(")
                continue

            try:
                playlist_context = {
                    'json_data': playlist_json,
                    'track_number': index,
                    'total_tracks': total_tracks,
                    'spotify_url': link_track
                }
                downloaded_track = self.download_trackspo(
                    link_track,
                    output_dir=output_dir, quality_download=quality_download,
                    recursive_quality=recursive_quality, recursive_download=recursive_download,
                    not_interface=not_interface, custom_dir_format=custom_dir_format,
                    custom_track_format=custom_track_format, pad_tracks=pad_tracks,
                    initial_retry_delay=initial_retry_delay, retry_delay_increase=retry_delay_increase,
                    max_retries=max_retries, convert_to=convert_to, bitrate=bitrate,
                    save_cover=save_cover, market=market, playlist_context=playlist_context
                )
                tracks.append(downloaded_track)
                
                # After download, check status for summary
                track_obj_for_cb = trackCbObject(title=track_name, artists=[artistTrackObject(name=artist_name)])
                if getattr(downloaded_track, 'was_skipped', False):
                    skipped_tracks_cb.append(track_obj_for_cb)
                elif downloaded_track.success:
                    successful_tracks_cb.append(track_obj_for_cb)
                else:
                    failed_tracks_cb.append(failedTrackObject(
                        track=track_obj_for_cb,
                        reason=getattr(downloaded_track, 'error_message', 'Unknown reason')
                    ))

            except (TrackNotFound, NoDataApi) as e:
                logger.error(f"Failed to download track: {track_name} - {artist_name}: {e}")
                failed_track_obj = trackCbObject(title=track_name, artists=[artistTrackObject(name=artist_name)])
                failed_tracks_cb.append(failedTrackObject(track=failed_track_obj, reason=str(e)))
                # Create a placeholder for the failed item
                failed_track = Track(
                    tags={'name': track_name, 'artist': artist_name},
                    song_path=None, file_format=None, quality=None, link=link_track, ids=None
                )
                failed_track.success = False
                failed_track.error_message = str(e)
                tracks.append(failed_track)

        total_from_spotify = playlist_json['tracks']['total']
        processed_count = len(successful_tracks_cb) + len(skipped_tracks_cb) + len(failed_tracks_cb)

        if total_from_spotify != processed_count:
            logger.warning(
                f"Playlist '{playlist_obj.title}' metadata reports {total_from_spotify} tracks, "
                f"but only {processed_count} were processed. This might indicate that not all pages of tracks were retrieved from Spotify."
            )

        summary_obj = summaryObject(
            successful_tracks=successful_tracks_cb,
            skipped_tracks=skipped_tracks_cb,
            failed_tracks=failed_tracks_cb,
            total_successful=len(successful_tracks_cb),
            total_skipped=len(skipped_tracks_cb),
            total_failed=len(failed_tracks_cb)
        )
        
        status_obj_done = doneObject(ids=playlist_obj.ids, summary=summary_obj)
        callback_obj_done = playlistCallbackObject(playlist=playlist_obj, status_info=status_obj_done)
        report_progress(reporter=self.progress_reporter, callback_obj=callback_obj_done)

        from deezspot.libutils.write_m3u import write_tracks_to_m3u
        m3u_path = write_tracks_to_m3u(output_dir, playlist_obj.title, tracks)

        if make_zip:
            zip_name = f"{output_dir}/playlist_{sanitize_name(playlist_obj.title)}.zip"
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
        search = self.__spo.search(query)
        
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
        
        logger.warning("Episode download logic is not fully refactored and might not work as expected with new reporting.")
        link_is_valid(link_episode)
        ids = get_ids(link_episode)
        
        try:
            # This will likely fail as API.tracking is gone.
            episode_metadata = API.get_episode(ids)
        except (NoDataApi, MarketAvailabilityError) as e:
            raise TrackNotFound(url=link_episode, message=f"Episode not available: {e}") from e
        except Exception:
            # Fallback to GW API if public API fails for any reason
            infos = self.__gw_api.get_episode_data(ids)
            if not infos:
                raise TrackNotFound(f"Episode {ids} not found")
            episode_metadata = {
                'music': infos.get('EPISODE_TITLE', ''), 'artist': infos.get('SHOW_NAME', ''),
                'album': infos.get('SHOW_NAME', ''), 'date': infos.get('EPISODE_PUBLISHED_TIMESTAMP', '').split()[0],
                'genre': 'Podcast', 'explicit': infos.get('SHOW_IS_EXPLICIT', '2'),
                'disc': 1, 'track': 1, 'duration': int(infos.get('DURATION', 0)), 'isrc': None,
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
        preferences.max_retries = max_retries
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
            source = "spotify"
        elif "deezer.com" in link:
            source = "deezer"
        else:
            raise InvalidLink(link)

        smart.source = source
        
        # Smart download reporting can be enhanced later if needed
        # For now, the individual download functions will do the reporting.

        if "track/" in link:
            func = self.download_trackspo if source == 'spotify' else self.download_trackdee
            track = func(
                link, output_dir=output_dir, quality_download=quality_download,
                recursive_quality=recursive_quality, recursive_download=recursive_download,
                not_interface=not_interface, custom_dir_format=custom_dir_format,
                custom_track_format=custom_track_format, pad_tracks=pad_tracks,
                initial_retry_delay=initial_retry_delay, retry_delay_increase=retry_delay_increase,
                max_retries=max_retries, convert_to=convert_to, bitrate=bitrate,
                save_cover=save_cover, market=market
            )
            smart.type = "track"
            smart.track = track

        elif "album/" in link:
            func = self.download_albumspo if source == 'spotify' else self.download_albumdee
            album = func(
                link, output_dir=output_dir, quality_download=quality_download,
                recursive_quality=recursive_quality, recursive_download=recursive_download,
                not_interface=not_interface, make_zip=make_zip,
                custom_dir_format=custom_dir_format, custom_track_format=custom_track_format,
                pad_tracks=pad_tracks, initial_retry_delay=initial_retry_delay,
                retry_delay_increase=retry_delay_increase, max_retries=max_retries,
                convert_to=convert_to, bitrate=bitrate, save_cover=save_cover,
                market=market
            )
            smart.type = "album"
            smart.album = album

        elif "playlist/" in link:
            func = self.download_playlistspo if source == 'spotify' else self.download_playlistdee
            playlist = func(
                link, output_dir=output_dir, quality_download=quality_download,
                recursive_quality=recursive_quality, recursive_download=recursive_download,
                not_interface=not_interface, make_zip=make_zip,
                custom_dir_format=custom_dir_format, custom_track_format=custom_track_format,
                pad_tracks=pad_tracks, initial_retry_delay=initial_retry_delay,
                retry_delay_increase=retry_delay_increase, max_retries=max_retries,
                convert_to=convert_to, bitrate=bitrate, save_cover=save_cover,
                market=market
            )
            smart.type = "playlist"
            smart.playlist = playlist

        return smart
