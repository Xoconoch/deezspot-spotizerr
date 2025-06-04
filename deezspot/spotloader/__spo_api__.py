#!/usr/bin/python3

from deezspot.easy_spoty import Spo
from datetime import datetime
from deezspot.libutils.utils import convert_to_date
import traceback
from deezspot.libutils.logging_utils import logger
from deezspot.exceptions import MarketAvailabilityError

def _check_market_availability(item_name: str, item_type: str, api_available_markets: list[str] | None, user_markets: list[str] | None):
    """Checks if an item is available in any of the user-specified markets."""
    if user_markets and api_available_markets is not None:
        is_available_in_any_user_market = any(m in api_available_markets for m in user_markets)
        if not is_available_in_any_user_market:
            markets_str = ", ".join(user_markets)
            raise MarketAvailabilityError(f"{item_type} '{item_name}' not available in provided market(s): {markets_str}")
    elif user_markets and api_available_markets is None:
        # Log a warning if user specified markets, but API response doesn't include 'available_markets'
        # This might indicate the item is available in all markets or API doesn't provide this info for this item type.
        # For now, we proceed without raising an error, as we cannot confirm it's "not available".
        logger.warning(
            f"Market availability check for {item_type} '{item_name}' skipped: "
            "API response did not include 'available_markets' field. Assuming availability."
        )

def _get_best_image_urls(images_list):
    urls = {'image': '', 'image2': '', 'image3': ''}
    if not images_list or not isinstance(images_list, list):
        return urls

    # Sort images by area (height * width) in descending order
    # Handle cases where height or width might be missing
    sorted_images = sorted(
        images_list,
        key=lambda img: img.get('height', 0) * img.get('width', 0),
        reverse=True
    )

    if len(sorted_images) > 0:
        urls['image'] = sorted_images[0].get('url', '')
    if len(sorted_images) > 1:
        urls['image2'] = sorted_images[1].get('url', '') # Second largest or same if only one size
    if len(sorted_images) > 2:
        urls['image3'] = sorted_images[2].get('url', '') # Third largest
    
    return urls

def tracking(ids, album_data_for_track=None, market: list[str] | None = None):
    datas = {}
    try:
        json_track = Spo.get_track(ids)
        if not json_track:
            logger.error(f"Failed to get track details for ID: {ids} from Spotify API.")
            return None

        # Perform market availability check for the track
        track_name_for_check = json_track.get('name', f'Track ID {ids}')
        api_track_markets = json_track.get('available_markets')
        _check_market_availability(track_name_for_check, "Track", api_track_markets, market)

        # Album details section
        # Use provided album_data_for_track if available (from tracking_album context)
        # Otherwise, fetch from track's album info or make a new API call for more details
        album_to_process = None
        fetch_full_album_details = False

        if album_data_for_track:
            album_to_process = album_data_for_track
        elif json_track.get('album'):
            album_to_process = json_track.get('album')
            # We might want fuller album details (like label, genres, upc, copyrights)
            # not present in track's nested album object.
            fetch_full_album_details = True 
        
        if fetch_full_album_details and album_to_process and album_to_process.get('id'):
            full_album_json = Spo.get_album(album_to_process.get('id'))
            if full_album_json:
                album_to_process = full_album_json # Prioritize full album details

        if album_to_process:
            image_urls = _get_best_image_urls(album_to_process.get('images', []))
            datas.update(image_urls)

            datas['genre'] = "; ".join(album_to_process.get('genres', []))
            
            album_artists_data = album_to_process.get('artists', [])
            ar_album_names = [artist.get('name', '') for artist in album_artists_data if artist.get('name')]
            datas['ar_album'] = "; ".join(filter(None, ar_album_names)) or 'Unknown Artist'
            
            datas['album'] = album_to_process.get('name', 'Unknown Album')
            datas['label'] = album_to_process.get('label', '') # Often in full album, not track's album obj
            datas['album_type'] = album_to_process.get('album_type', 'unknown')
            
            copyrights_data = album_to_process.get('copyrights', [])
            datas['copyright'] = copyrights_data[0].get('text', '') if copyrights_data else ''
            
            album_external_ids = album_to_process.get('external_ids', {})
            datas['upc'] = album_external_ids.get('upc', '')
            
            datas['nb_tracks'] = album_to_process.get('total_tracks', 0)
            # Release date from album_to_process is likely more definitive
            datas['year'] = convert_to_date(album_to_process.get('release_date', ''))
            datas['release_date_precision'] = album_to_process.get('release_date_precision', 'unknown')
        else: # Fallback if no album_to_process
            datas.update(_get_best_image_urls([]))
            datas['genre'] = ''
            datas['ar_album'] = 'Unknown Artist'
            datas['album'] = json_track.get('album', {}).get('name', 'Unknown Album') # Basic fallback
            datas['label'] = ''
            datas['album_type'] = json_track.get('album', {}).get('album_type', 'unknown')
            datas['copyright'] = ''
            datas['upc'] = ''
            datas['nb_tracks'] = json_track.get('album', {}).get('total_tracks', 0)
            datas['year'] = convert_to_date(json_track.get('album', {}).get('release_date', ''))
            datas['release_date_precision'] = json_track.get('album', {}).get('release_date_precision', 'unknown')


        # Track specific details
        datas['music'] = json_track.get('name', 'Unknown Track')

        track_artists_data = json_track.get('artists', [])
        track_artist_names = [artist.get('name', '') for artist in track_artists_data if artist.get('name')]
        datas['artist'] = "; ".join(filter(None, track_artist_names)) or 'Unknown Artist'
        
        datas['tracknum'] = json_track.get('track_number', 0)
        datas['discnum'] = json_track.get('disc_number', 0)

        # If year details were not set from a more complete album object, use track's album info
        if not datas.get('year') and json_track.get('album'):
            datas['year'] = convert_to_date(json_track.get('album', {}).get('release_date', ''))
            datas['release_date_precision'] = json_track.get('album', {}).get('release_date_precision', 'unknown')
        
        datas['duration'] = json_track.get('duration_ms', 0) // 1000

        track_external_ids = json_track.get('external_ids', {})
        datas['isrc'] = track_external_ids.get('isrc', '')
        
        datas['explicit'] = json_track.get('explicit', False)
        datas['popularity'] = json_track.get('popularity', 0)
        
        # Placeholder for tags not directly from this API response but might be expected by tagger
        datas['bpm'] = datas.get('bpm', 'Unknown') # Not available here
        datas['gain'] = datas.get('gain', 'Unknown') # Not available here
        datas['lyric'] = datas.get('lyric', '') # Not available here
        datas['author'] = datas.get('author', '') # Not available here (lyricist)
        datas['composer'] = datas.get('composer', '') # Not available here
        # copyright is handled by album section
        datas['lyricist'] = datas.get('lyricist', '') # Same as author, not here
        datas['version'] = datas.get('version', '') # Not typically here

        datas['ids'] = ids
        logger.debug(f"Successfully tracked metadata for track {ids}")
        
    except MarketAvailabilityError: # Re-raise to be caught by the calling download method
        raise
    except Exception as e:
        logger.error(f"Failed to track metadata for track {ids}: {str(e)}")
        logger.debug(traceback.format_exc())
        return None

    return datas

def tracking_album(album_json, market: list[str] | None = None):
    if not album_json:
        logger.error("tracking_album received None or empty album_json.")
        return None
        
    song_metadata = {}
    try:
        # Perform market availability check for the album itself
        album_name_for_check = album_json.get('name', f"Album ID {album_json.get('id', 'Unknown')}")
        api_album_markets = album_json.get('available_markets')
        _check_market_availability(album_name_for_check, "Album", api_album_markets, market)

        initial_list_fields = {
            "music": [], "artist": [], "tracknum": [], "discnum": [],
            "duration": [], "isrc": [], "ids": [], "explicit_list": [], "popularity_list": []
            # "bpm": [], "gain": [] are usually unknown from this endpoint for tracks
        }
        song_metadata.update(initial_list_fields)

        image_urls = _get_best_image_urls(album_json.get('images', []))
        song_metadata.update(image_urls)

        song_metadata['album'] = album_json.get('name', 'Unknown Album')
        song_metadata['label'] = album_json.get('label', '')
        song_metadata['year'] = convert_to_date(album_json.get('release_date', ''))
        song_metadata['release_date_precision'] = album_json.get('release_date_precision', 'unknown')
        song_metadata['nb_tracks'] = album_json.get('total_tracks', 0)
        song_metadata['genre'] = "; ".join(album_json.get('genres', []))
        song_metadata['album_type'] = album_json.get('album_type', 'unknown')
        song_metadata['popularity'] = album_json.get('popularity', 0)

        album_artists_data = album_json.get('artists', [])
        ar_album_names = [artist.get('name', '') for artist in album_artists_data if artist.get('name')]
        song_metadata['ar_album'] = "; ".join(filter(None, ar_album_names)) or 'Unknown Artist'

        album_external_ids = album_json.get('external_ids', {})
        song_metadata['upc'] = album_external_ids.get('upc', '')

        copyrights_data = album_json.get('copyrights', [])
        song_metadata['copyright'] = copyrights_data[0].get('text', '') if copyrights_data else ''
        
        # Add other common flat metadata keys with defaults if not directly from album_json
        song_metadata['bpm'] = 'Unknown'
        song_metadata['gain'] = 'Unknown'
        song_metadata['lyric'] = ''
        song_metadata['author'] = ''
        song_metadata['composer'] = ''
        song_metadata['lyricist'] = ''
        song_metadata['version'] = ''


        tracks_data = album_json.get('tracks', {}).get('items', [])
        for track_item in tracks_data:
            if not track_item: continue # Skip if track_item is None
            c_ids = track_item.get('id')
            if not c_ids: # If track has no ID, try to get some basic info directly
                song_metadata['music'].append(track_item.get('name', 'Unknown Track'))
                track_artists_data = track_item.get('artists', [])
                track_artist_names = [artist.get('name', '') for artist in track_artists_data if artist.get('name')]
                song_metadata['artist'].append("; ".join(filter(None, track_artist_names)) or 'Unknown Artist')
                song_metadata['tracknum'].append(track_item.get('track_number', 0))
                song_metadata['discnum'].append(track_item.get('disc_number', 0))
                song_metadata['duration'].append(track_item.get('duration_ms', 0) // 1000)
                song_metadata['isrc'].append(track_item.get('external_ids', {}).get('isrc', ''))
                song_metadata['ids'].append('N/A')
                song_metadata['explicit_list'].append(track_item.get('explicit', False))
                song_metadata['popularity_list'].append(track_item.get('popularity', 0))
                continue

            # Pass the main album_json as album_data_for_track to avoid refetching it in tracking()
            # Also pass the market parameter
            track_details = tracking(c_ids, album_data_for_track=album_json, market=market) 

            if track_details:
                song_metadata['music'].append(track_details.get('music', 'Unknown Track'))
                song_metadata['artist'].append(track_details.get('artist', 'Unknown Artist'))
                song_metadata['tracknum'].append(track_details.get('tracknum', 0))
                song_metadata['discnum'].append(track_details.get('discnum', 0))
                # BPM and Gain are generally not per-track from this endpoint
                # song_metadata['bpm'].append(track_details.get('bpm', 'Unknown'))
                song_metadata['duration'].append(track_details.get('duration', 0))
                song_metadata['isrc'].append(track_details.get('isrc', ''))
                song_metadata['ids'].append(c_ids)
                song_metadata['explicit_list'].append(track_details.get('explicit', False))
                # popularity_list for track specific popularity if needed, or use album popularity
                # song_metadata['popularity_list'].append(track_details.get('popularity',0))

            else: # Fallback if tracking(c_ids) failed
                logger.warning(f"Could not retrieve full metadata for track ID {c_ids} in album {album_json.get('id', 'N/A')}. Using minimal data.")
                song_metadata['music'].append(track_item.get('name', 'Unknown Track'))
                track_artists_data = track_item.get('artists', [])
                track_artist_names = [artist.get('name', '') for artist in track_artists_data if artist.get('name')]
                song_metadata['artist'].append("; ".join(filter(None, track_artist_names)) or 'Unknown Artist')
                song_metadata['tracknum'].append(track_item.get('track_number', 0))
                song_metadata['discnum'].append(track_item.get('disc_number', 0))
                song_metadata['duration'].append(track_item.get('duration_ms', 0) // 1000)
                song_metadata['isrc'].append(track_item.get('external_ids', {}).get('isrc', ''))
                song_metadata['ids'].append(c_ids)
                song_metadata['explicit_list'].append(track_item.get('explicit', False))
                # song_metadata['popularity_list'].append(track_item.get('popularity',0))


        logger.debug(f"Successfully tracked metadata for album {album_json.get('id', 'N/A')}")
                    
    except MarketAvailabilityError: # Re-raise
        raise
    except Exception as e:
        logger.error(f"Failed to track album metadata for album ID {album_json.get('id', 'N/A') if album_json else 'N/A'}: {str(e)}")
        logger.debug(traceback.format_exc())
        return None

    return song_metadata

def tracking_episode(ids, market: list[str] | None = None):
    datas = {}
    try:
        json_episode = Spo.get_episode(ids)
        if not json_episode:
            logger.error(f"Failed to get episode details for ID: {ids} from Spotify API.")
            return None

        # Perform market availability check for the episode
        episode_name_for_check = json_episode.get('name', f'Episode ID {ids}')
        api_episode_markets = json_episode.get('available_markets')
        _check_market_availability(episode_name_for_check, "Episode", api_episode_markets, market)

        image_urls = _get_best_image_urls(json_episode.get('images', []))
        datas.update(image_urls)

        datas['audio_preview_url'] = json_episode.get('audio_preview_url', '')
        datas['description'] = json_episode.get('description', '')
        datas['duration'] = json_episode.get('duration_ms', 0) // 1000
        datas['explicit'] = json_episode.get('explicit', False)
        datas['external_urls_spotify'] = json_episode.get('external_urls', {}).get('spotify', '')
        datas['href'] = json_episode.get('href', '')
        datas['html_description'] = json_episode.get('html_description', '')
        datas['id'] = json_episode.get('id', '') # Episode's own ID
        
        datas['is_externally_hosted'] = json_episode.get('is_externally_hosted', False)
        datas['is_playable'] = json_episode.get('is_playable', False)
        datas['language'] = json_episode.get('language', '') # Deprecated, use languages
        datas['languages'] = "; ".join(json_episode.get('languages', []))
        datas['music'] = json_episode.get('name', 'Unknown Episode') # Use 'music' for consistency with track naming
        datas['name'] = json_episode.get('name', 'Unknown Episode') # Keep 'name' as well if needed by other parts

        datas['release_date'] = convert_to_date(json_episode.get('release_date', ''))
        datas['release_date_precision'] = json_episode.get('release_date_precision', 'unknown')
        
        show_data = json_episode.get('show', {})
        datas['show_name'] = show_data.get('name', 'Unknown Show')
        datas['publisher'] = show_data.get('publisher', 'Unknown Publisher')
        datas['show_description'] = show_data.get('description', '')
        datas['show_explicit'] = show_data.get('explicit', False)
        datas['show_total_episodes'] = show_data.get('total_episodes', 0)
        datas['show_media_type'] = show_data.get('media_type', 'unknown') # e.g. 'audio'

        # For tagger compatibility, map some show data to common track/album fields
        datas['artist'] = datas['publisher'] # Publisher as artist for episodes
        datas['album'] = datas['show_name']  # Show name as album for episodes
        datas['genre'] = "; ".join(show_data.get('genres', [])) # If shows have genres
        datas['copyright'] = copyrights_data[0].get('text', '') if (copyrights_data := show_data.get('copyrights', [])) else ''


        # Placeholder for tags not directly from this API response but might be expected by tagger
        datas['tracknum'] = 1 # Default for single episode
        datas['discnum'] = 1 # Default for single episode
        datas['ar_album'] = datas['publisher'] 
        datas['label'] = datas['publisher']
        datas['bpm'] = 'Unknown'
        datas['gain'] = 'Unknown'
        datas['isrc'] = ''
        datas['upc'] = ''
        datas['lyric'] = ''
        datas['author'] = ''
        datas['composer'] = ''
        datas['lyricist'] = ''
        datas['version'] = ''
        
        datas['ids'] = ids # The episode's own ID passed to the function
        
        logger.debug(f"Successfully tracked metadata for episode {ids}")
        
    except MarketAvailabilityError: # Re-raise
        raise
    except Exception as e:
        logger.error(f"Failed to track episode metadata for ID {ids}: {str(e)}")
        logger.debug(traceback.format_exc())
        return None

    return datas