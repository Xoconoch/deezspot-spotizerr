#!/usr/bin/python3
import os
import json
import requests
import time
from os.path import isfile
from copy import deepcopy
from deezspot.libutils.audio_converter import convert_audio
from deezspot.deezloader.dee_api import API
from deezspot.deezloader.deegw_api import API_GW
from deezspot.deezloader.deezer_settings import qualities
from deezspot.libutils.others_settings import answers
from deezspot.deezloader.__download_utils__ import decryptfile, gen_song_hash
from deezspot.exceptions import (
    TrackNotFound,
    NoRightOnMedia,
    QualityNotFound,
)
from deezspot.models.download import (
    Track,
    Album,
    Playlist,
    Preferences,
    Episode,
)
from deezspot.deezloader.__utils__ import (
    check_track_ids,
    check_track_token,
    check_track_md5,
)
from deezspot.libutils.utils import (
    set_path,
    trasform_sync_lyric,
    create_zip,
    sanitize_name,
    save_cover_image,
    __get_dir as get_album_directory,
)
from deezspot.libutils.write_m3u import create_m3u_file, append_track_to_m3u
from deezspot.libutils.metadata_converter import track_object_to_dict, album_object_to_dict
from deezspot.libutils.progress_reporter import (
    report_track_initializing, report_track_skipped, report_track_retrying,
    report_track_realtime_progress, report_track_error, report_track_done,
    report_album_initializing, report_album_done, report_playlist_initializing, report_playlist_done
)
from deezspot.libutils.taggers import (
    enhance_metadata_with_image, add_deezer_enhanced_metadata, process_and_tag_track,
    save_cover_image_for_track
)
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen import File
from deezspot.libutils.logging_utils import logger, ProgressReporter, report_progress
from deezspot.libutils.skip_detection import check_track_exists
from deezspot.libutils.cleanup_utils import register_active_download, unregister_active_download
from deezspot.libutils.audio_converter import AUDIO_FORMATS # Added for parse_format_string
from deezspot.models.callback.callbacks import (
    trackCallbackObject,
    albumCallbackObject,
    playlistCallbackObject,
    initializingObject,
    skippedObject,
    retryingObject,
    realTimeObject,
    errorObject,
    doneObject,
    summaryObject,
    failedTrackObject,
)
from deezspot.models.callback.track import trackObject as trackCbObject, albumTrackObject, artistTrackObject, playlistTrackObject
from deezspot.models.callback.album import albumObject as albumCbObject
from deezspot.models.callback.playlist import playlistObject as playlistCbObject
from deezspot.models.callback.common import IDs
from deezspot.models.callback.user import userObject

# Use unified metadata converter
def _track_object_to_dict(track_obj: trackCbObject) -> dict:
    """
    Convert a track object to a dictionary format for tagging.
    Similar to spotloader's approach for consistent metadata handling.
    """
    return track_object_to_dict(track_obj, source_type='deezer')

# Use unified metadata converter  
def _album_object_to_dict(album_obj: albumCbObject) -> dict:
    """
    Convert an album object to a dictionary format for tagging.
    Similar to spotloader's approach for consistent metadata handling.
    """
    return album_object_to_dict(album_obj, source_type='deezer')

class Download_JOB:
    progress_reporter = None
    
    @classmethod
    def set_progress_reporter(cls, reporter):
        cls.progress_reporter = reporter
        
    @classmethod
    def __get_url(cls, c_track: Track, quality_download: str) -> dict:
        if c_track.get('__TYPE__') == 'episode':
            return {
                "media": [{
                    "sources": [{
                        "url": c_track.get('EPISODE_DIRECT_STREAM_URL')
                    }]
                }]
            }
        else:
            # Get track IDs and check which encryption method is available
            track_info = check_track_ids(c_track)
            encryption_type = track_info.get('encryption_type', 'blowfish')
            
            # If AES encryption is available (MEDIA_KEY and MEDIA_NONCE present)
            if encryption_type == 'aes':
                # Use track token to get media URL from API
                track_token = check_track_token(c_track)
                medias = API_GW.get_medias_url([track_token], quality_download)
                return medias[0]
            
            # Use Blowfish encryption (legacy method)
            else:
                md5_origin = track_info.get('md5_origin')
                media_version = track_info.get('media_version', '1')
                track_id = track_info.get('track_id')
                
                if not md5_origin:
                    raise ValueError("MD5_ORIGIN is missing")
                if not track_id:
                    raise ValueError("Track ID is missing")
                
                n_quality = qualities[quality_download]['n_quality']
                
                # Create the song hash using the correct parameter order
                # Note: For legacy Deezer API, the order is: MD5 + Media Version + Track ID
                c_song_hash = gen_song_hash(track_id, md5_origin, media_version)
                
                # Log the hash generation parameters for debugging
                logger.debug(f"Generating song hash with: track_id={track_id}, md5_origin={md5_origin}, media_version={media_version}")
                
                c_media_url = API_GW.get_song_url(md5_origin[0], c_song_hash)
                
                return {
                    "media": [
                        {
                            "sources": [
                                {
                                    "url": c_media_url
                                }
                            ]
                        }
                    ]
                }
     
    @classmethod
    def check_sources(
        cls,
        infos_dw: list,
        quality_download: str  
    ) -> list:
        from deezspot.deezloader.deegw_api import API_GW
        # Preprocess episodes separately
        medias = []
        for track in infos_dw:
            if track.get('__TYPE__') == 'episode':
                media_json = cls.__get_url(track, quality_download)
                medias.append(media_json)

        # For non-episodes, gather tokens
        non_episode_tracks = [c_track for c_track in infos_dw if c_track.get('__TYPE__') != 'episode']
        tokens = [check_track_token(c_track) for c_track in non_episode_tracks]

        def chunk_list(lst, chunk_size):
            """Yield successive chunk_size chunks from lst."""
            for i in range(0, len(lst), chunk_size):
                yield lst[i:i + chunk_size]

        # Prepare list for media results for non-episodes
        non_episode_medias = []

        # Split tokens into chunks of 25
        for tokens_chunk in chunk_list(tokens, 25):
            try:
                chunk_medias = API_GW.get_medias_url(tokens_chunk, quality_download)
                # Post-process each returned media in the chunk
                for idx in range(len(chunk_medias)):
                    if "errors" in chunk_medias[idx]:
                        c_media_json = cls.__get_url(non_episode_tracks[len(non_episode_medias) + idx], quality_download)
                        chunk_medias[idx] = c_media_json
                    else:
                        if not chunk_medias[idx]['media']:
                            c_media_json = cls.__get_url(non_episode_tracks[len(non_episode_medias) + idx], quality_download)
                            chunk_medias[idx] = c_media_json
                        elif len(chunk_medias[idx]['media'][0]['sources']) == 1:
                            c_media_json = cls.__get_url(non_episode_tracks[len(non_episode_medias) + idx], quality_download)
                            chunk_medias[idx] = c_media_json
                non_episode_medias.extend(chunk_medias)
            except NoRightOnMedia:
                for c_track in tokens_chunk:
                    # Find the corresponding full track info from non_episode_tracks
                    track_index = len(non_episode_medias)
                    c_media_json = cls.__get_url(non_episode_tracks[track_index], quality_download)
                    non_episode_medias.append(c_media_json)

        # Now, merge the medias. We need to preserve the original order.
        # We'll create a final list that contains media for each track in infos_dw.
        final_medias = []
        episode_idx = 0
        non_episode_idx = 0
        for track in infos_dw:
            if track.get('__TYPE__') == 'episode':
                final_medias.append(medias[episode_idx])
                episode_idx += 1
            else:
                final_medias.append(non_episode_medias[non_episode_idx])
                non_episode_idx += 1

        return final_medias

class EASY_DW:
    progress_reporter = None
    
    @classmethod
    def set_progress_reporter(cls, reporter):
        cls.progress_reporter = reporter
        
    def __init__(
        self,
        infos_dw: dict,
        preferences: Preferences,
        parent: str = None  # Can be 'album', 'playlist', or None for individual track
    ) -> None:
        
        self.__preferences = preferences
        self.__parent = parent  # Store the parent type
        
        self.__infos_dw = infos_dw
        self.__ids = preferences.ids
        self.__link = preferences.link
        self.__output_dir = preferences.output_dir
        self.__not_interface = preferences.not_interface
        self.__quality_download = preferences.quality_download
        self.__recursive_quality = preferences.recursive_quality
        self.__recursive_download = preferences.recursive_download
        self.__convert_to = getattr(preferences, 'convert_to', None)
        self.__bitrate = getattr(preferences, 'bitrate', None) # Added for consistency

        if self.__infos_dw.get('__TYPE__') == 'episode':
            self.__song_metadata = {
                'music': self.__infos_dw.get('EPISODE_TITLE', ''),
                'artist': self.__infos_dw.get('SHOW_NAME', ''),
                'album': self.__infos_dw.get('SHOW_NAME', ''),
                'date': self.__infos_dw.get('EPISODE_PUBLISHED_TIMESTAMP', '').split()[0],
                'genre': 'Podcast',
                'explicit': self.__infos_dw.get('SHOW_IS_EXPLICIT', '2'),
                'disc': 1,
                'track': 1,
                'duration': int(self.__infos_dw.get('DURATION', 0)),
                'isrc': None
            }
            self.__download_type = "episode"
        else:
            # Get the track object from preferences
            self.__track_obj: trackCbObject = preferences.song_metadata
            
            # Convert it to the dictionary format needed for legacy functions
            self.__song_metadata = self._track_object_to_dict(self.__track_obj)
            self.__download_type = "track"

        self.__c_quality = qualities[self.__quality_download]
        self.__fallback_ids = self.__ids

        self.__set_quality()
        self.__write_track()

    def _get_parent_context(self):
        parent_obj = None
        current_track_val = None
        total_tracks_val = None

        if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
            playlist_data = self.__preferences.json_data
            
            if isinstance(playlist_data, dict):
                # Spotify raw dict
                parent_obj = playlistTrackObject(
                    title=playlist_data.get('name', 'unknown'),
                    description=playlist_data.get('description', ''),
                    owner=userObject(name=playlist_data.get('owner', {}).get('display_name', 'unknown')),
                    ids=IDs(spotify=playlist_data.get('id', ''))
                )
            else:
                # Deezer playlistObject
                playlist_data_obj: playlistCbObject = playlist_data
                parent_obj = playlistTrackObject(
                    title=playlist_data_obj.title,
                    description=playlist_data_obj.description,
                    owner=playlist_data_obj.owner,
                    ids=playlist_data_obj.ids
                )
            
            total_tracks_val = getattr(self.__preferences, 'total_tracks', 0)
            current_track_val = getattr(self.__preferences, 'track_number', 0)

        elif self.__parent == "album" and hasattr(self.__preferences, "json_data"):
            album_data = self.__preferences.json_data
            album_id = album_data.ids.deezer
            parent_obj = albumCbObject(
                title=album_data.title,
                artists=[artistTrackObject(name=artist.name) for artist in album_data.artists],
                ids=IDs(deezer=album_id)
            )
            total_tracks_val = getattr(self.__preferences, 'total_tracks', 0)
            current_track_val = getattr(self.__preferences, 'track_number', 0)

        return parent_obj, current_track_val, total_tracks_val

    def _track_object_to_dict(self, track_obj: any) -> dict:
        """
        Helper to convert a track object (of any kind) to the dict format 
        expected by legacy tagging and path functions.
        It intelligently finds the album information based on the download context.
        """
        # Use the unified metadata converter
        metadata_dict = track_object_to_dict(track_obj, source_type='deezer')
        
        # Check for track_position and disk_number in the original API data
        # These might be directly available in the infos_dw dictionary for Deezer tracks
        if self.__infos_dw:
            if 'track_position' in self.__infos_dw:
                metadata_dict['tracknum'] = self.__infos_dw['track_position']
            if 'disk_number' in self.__infos_dw:
                metadata_dict['discnum'] = self.__infos_dw['disk_number']

        return metadata_dict

    def __set_quality(self) -> None:
        self.__file_format = self.__c_quality['f_format']
        self.__song_quality = self.__c_quality['s_quality']

    def __set_song_path(self) -> None:
        # If the Preferences object has custom formatting strings, pass them on.
        custom_dir_format = getattr(self.__preferences, 'custom_dir_format', None)
        custom_track_format = getattr(self.__preferences, 'custom_track_format', None)
        pad_tracks = getattr(self.__preferences, 'pad_tracks', True)
        self.__song_path = set_path(
            self.__song_metadata,
            self.__output_dir,
            self.__song_quality,
            self.__file_format,
            custom_dir_format=custom_dir_format,
            custom_track_format=custom_track_format,
            pad_tracks=pad_tracks
        )
    
    def __set_episode_path(self) -> None:
        custom_dir_format = getattr(self.__preferences, 'custom_dir_format', None)
        custom_track_format = getattr(self.__preferences, 'custom_track_format', None)
        pad_tracks = getattr(self.__preferences, 'pad_tracks', True)
        self.__song_path = set_path(
            self.__song_metadata,
            self.__output_dir,
            self.__song_quality,
            self.__file_format,
            is_episode=True,
            custom_dir_format=custom_dir_format,
            custom_track_format=custom_track_format,
            pad_tracks=pad_tracks
        )

    def __write_track(self) -> None:
        self.__set_song_path()

        self.__c_track = Track(
            self.__song_metadata, self.__song_path,
            self.__file_format, self.__song_quality,
            self.__link, self.__ids
        )

        self.__c_track.set_fallback_ids(self.__fallback_ids)
    
    def __write_episode(self) -> None:
        self.__set_episode_path()

        self.__c_episode = Episode(
            self.__song_metadata, self.__song_path,
            self.__file_format, self.__song_quality,
            self.__link, self.__ids
        )

        self.__c_episode.md5_image = self.__ids
        self.__c_episode.set_fallback_ids(self.__fallback_ids)

    def easy_dw(self) -> Track:
        # Get image URL and enhance metadata
        if self.__infos_dw.get('__TYPE__') == 'episode':
            pic = self.__infos_dw.get('EPISODE_IMAGE_MD5', '')
        else:
            pic = self.__infos_dw['ALB_PICTURE']
        image = API.choose_img(pic)
        self.__song_metadata['image'] = image
        
        # Process image data using unified utility
        self.__song_metadata = enhance_metadata_with_image(self.__song_metadata)
        song = f"{self.__song_metadata['music']} - {self.__song_metadata['artist']}"

        # Check if track already exists based on metadata
        current_title = self.__song_metadata['music']
        current_album = self.__song_metadata['album']
        current_artist = self.__song_metadata.get('artist') # For logging

        # Use check_track_exists from skip_detection module
        # self.__song_path is the original path before any conversion logic in this download attempt.
        # self.__convert_to is the user's desired final format.
        exists, existing_file_path = check_track_exists(
            original_song_path=self.__song_path,
            title=current_title,
            album=current_album,
            convert_to=self.__convert_to, # User's target conversion format
            logger=logger
        )

        if exists and existing_file_path:
            logger.info(f"Track '{current_title}' by '{current_artist}' already exists at '{existing_file_path}'. Skipping download.")
            
            self.__c_track.song_path = existing_file_path
            _, new_ext = os.path.splitext(existing_file_path)
            self.__c_track.file_format = new_ext.lower()
            self.__c_track.success = True
            self.__c_track.was_skipped = True

            parent_obj, current_track_val, total_tracks_val = self._get_parent_context()

            # Report track skipped status
            report_track_skipped(
                track_obj=self.__track_obj,
                reason=f"Track already exists in desired format at {existing_file_path}",
                preferences=self.__preferences,
                parent_obj=parent_obj,
                current_track=current_track_val,
                total_tracks=total_tracks_val
            )

            skipped_item = Track(
                self.__song_metadata,
                existing_file_path, # Use the path of the existing file
                self.__c_track.file_format, # Use updated file format
                self.__song_quality, # Original download quality target
                self.__link, self.__ids
            )
            skipped_item.success = True # Considered successful as file is available
            skipped_item.was_skipped = True
            self.__c_track = skipped_item
            return self.__c_track

        # Initialize success to False for the item being processed
        if self.__infos_dw.get('__TYPE__') == 'episode':
            if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                 self.__c_episode.success = False
        else:
            if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                 self.__c_track.success = False

        try:
            if self.__infos_dw.get('__TYPE__') == 'episode':
                self.download_episode_try()
            else:
                self.download_try()
                
                if self.__c_track.success :
                    parent_obj, current_track_val, total_tracks_val = self._get_parent_context()
                    
                    done_status = doneObject(ids=self.__track_obj.ids, convert_to=self.__convert_to)
                    
                    if self.__parent is None:
                        summary = summaryObject(
                            successful_tracks=[self.__track_obj],
                            total_successful=1
                        )
                        done_status.summary = summary
                        
                    callback_obj = trackCallbackObject(
                        track=self.__track_obj,
                        status_info=done_status,
                        parent=parent_obj,
                        current_track=current_track_val,
                        total_tracks=total_tracks_val
                    )
                    report_progress(
                        reporter=Download_JOB.progress_reporter,
                        callback_obj=callback_obj
                    )

        except Exception as e:
            item_type = "Episode" if self.__infos_dw.get('__TYPE__') == 'episode' else "Track"
            item_name = self.__song_metadata.get('music', f'Unknown {item_type}')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            error_message = f"Download process failed for {item_type.lower()} '{item_name}' by '{artist_name}' (URL: {self.__link}). Error: {str(e)}"
            logger.error(error_message)
            
            current_item_obj = self.__c_episode if self.__infos_dw.get('__TYPE__') == 'episode' else self.__c_track
            if current_item_obj:
                current_item_obj.success = False
                current_item_obj.error_message = error_message
            
            if item_type == "Track":
                parent_obj, current_track_val, total_tracks_val = self._get_parent_context()
                
                error_obj = errorObject(
                    ids=self.__track_obj.ids,
                    error=error_message
                )
                callback_obj = trackCallbackObject(
                    track=self.__track_obj,
                    status_info=error_obj,
                    parent=parent_obj,
                    current_track=current_track_val,
                    total_tracks=total_tracks_val
                )
                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    callback_obj=callback_obj
                )

            raise TrackNotFound(message=error_message, url=self.__link) from e

        # --- Handling after download attempt --- 

        current_item = self.__c_episode if self.__infos_dw.get('__TYPE__') == 'episode' else self.__c_track
        item_type_str = "episode" if self.__infos_dw.get('__TYPE__') == 'episode' else "track"

        # If the item was skipped (e.g. file already exists), return it immediately.
        if getattr(current_item, 'was_skipped', False):
            return current_item

        # Final check for non-skipped items that might have failed.
        if not current_item.success:
            item_name = self.__song_metadata.get('music', f'Unknown {item_type_str.capitalize()}')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            original_error_msg = getattr(current_item, 'error_message', f"Download failed for an unspecified reason after {item_type_str} processing attempt.")
            error_msg_template = "Cannot download {type} '{title}' by '{artist}'. Reason: {reason}"
            final_error_msg = error_msg_template.format(type=item_type_str, title=item_name, artist=artist_name, reason=original_error_msg)
            current_link_attr = current_item.link if hasattr(current_item, 'link') and current_item.link else self.__link
            logger.error(f"{final_error_msg} (URL: {current_link_attr})")
            current_item.error_message = final_error_msg
            raise TrackNotFound(message=final_error_msg, url=current_link_attr)

                # If we reach here, the item should be successful and not skipped.
        if current_item.success:
            if self.__infos_dw.get('__TYPE__') != 'episode': # Assuming pic is for tracks
                current_item.md5_image = pic # Set md5_image for tracks
            # Apply tags using unified utility with Deezer enhancements
            from deezspot.deezloader.deegw_api import API_GW
            enhanced_metadata = add_deezer_enhanced_metadata(
                self.__song_metadata,
                self.__infos_dw,
                self.__ids,
                API_GW
            )
            process_and_tag_track(
                track=current_item,
                metadata_dict=enhanced_metadata,
                source_type='deezer'
            )
        
        return current_item

    def download_try(self) -> Track:
        from deezspot.deezloader.deegw_api import API_GW
        # Pre-check: if FLAC is requested but filesize is zero, fallback to MP3.
        if self.__file_format == '.flac':
            filesize_str = self.__infos_dw.get('FILESIZE_FLAC', '0')
            try:
                filesize = int(filesize_str)
            except ValueError:
                filesize = 0

            if filesize == 0:
                song = self.__song_metadata['music']
                artist = self.__song_metadata['artist']
                # Switch quality settings to MP3_320.
                self.__quality_download = 'MP3_320'
                self.__file_format = '.mp3'
                self.__song_path = self.__song_path.rsplit('.', 1)[0] + '.mp3'
                media = Download_JOB.check_sources([self.__infos_dw], 'MP3_320')
                if media:
                    self.__infos_dw['media_url'] = media[0]
                else:
                    raise TrackNotFound(f"Track {song} - {artist} not available in MP3 format after FLAC attempt failed (filesize was 0).")

        # Continue with the normal download process.
        try:
            media_list = self.__infos_dw['media_url']['media']
            song_link = media_list[0]['sources'][0]['url']

            try:
                crypted_audio = API_GW.song_exist(song_link)
            except TrackNotFound:
                song = self.__song_metadata['music']
                artist = self.__song_metadata['artist']

                if self.__file_format == '.flac':
                    logger.warning(f"\n⚠ {song} - {artist} is not available in FLAC format. Trying MP3...")
                    self.__quality_download = 'MP3_320'
                    self.__file_format = '.mp3'
                    self.__song_path = self.__song_path.rsplit('.', 1)[0] + '.mp3'

                    media = Download_JOB.check_sources(
                        [self.__infos_dw], 'MP3_320'
                    )
                    if media:
                        self.__infos_dw['media_url'] = media[0]
                        song_link = media[0]['media'][0]['sources'][0]['url']
                        crypted_audio = API_GW.song_exist(song_link)
                    else:
                        raise TrackNotFound(f"Track {song} - {artist} not available in MP3 after FLAC attempt failed (media not found for MP3).")
                else:
                    if not self.__recursive_quality:
                        # msg was not defined, provide a more specific message
                        raise QualityNotFound(f"Quality {self.__quality_download} not found for {song} - {artist} and recursive quality search is disabled.")
                    for c_quality in qualities:
                        if self.__quality_download == c_quality:
                            continue
                        media = Download_JOB.check_sources(
                            [self.__infos_dw], c_quality
                        )
                        if media:
                            self.__infos_dw['media_url'] = media[0]
                            song_link = media[0]['media'][0]['sources'][0]['url']
                            try:
                                crypted_audio = API_GW.song_exist(song_link)
                                self.__c_quality = qualities[c_quality]
                                self.__set_quality()
                                break
                            except TrackNotFound:
                                if c_quality == "MP3_128":
                                    raise TrackNotFound(f"Error with {song} - {artist}. All available qualities failed, last attempt was {c_quality}. Link: {self.__link}")
                                continue

            c_crypted_audio = crypted_audio.iter_content(2048)
            
            self.__fallback_ids = check_track_ids(self.__infos_dw)
            encryption_type = self.__fallback_ids.get('encryption_type', 'unknown')
            logger.debug(f"Using encryption type: {encryption_type}")

            parent_obj, current_track_val, total_tracks_val = self._get_parent_context()

            try:
                self.__write_track()
                
                # Report track initialization status
                report_track_initializing(
                    track_obj=self.__track_obj,
                    preferences=self.__preferences,
                    parent_obj=parent_obj,
                    current_track=current_track_val,
                    total_tracks=total_tracks_val
                )
                
                register_active_download(self.__song_path)
                try:
                    decryptfile(c_crypted_audio, self.__fallback_ids, self.__song_path)
                    logger.debug(f"Successfully decrypted track using {encryption_type} encryption")
                except Exception as e_decrypt:
                    unregister_active_download(self.__song_path)
                    if isfile(self.__song_path):
                        try:
                            os.remove(self.__song_path)
                        except OSError:
                            logger.warning(f"Could not remove partially downloaded file: {self.__song_path}")
                    self.__c_track.success = False
                    self.__c_track.error_message = f"Decryption failed: {str(e_decrypt)}"
                    
                    # Ensure error callback uses the same parent_obj that was created earlier
                    error_status = errorObject(
                        ids=self.__track_obj.ids,
                        error=f"Decryption failed: {str(e_decrypt)}",
                        convert_to=self.__convert_to
                    )
                    
                    error_callback_obj = trackCallbackObject(
                        track=self.__track_obj,
                        status_info=error_status,
                        parent=parent_obj,  # Use the same parent_obj created earlier
                        current_track=current_track_val,
                        total_tracks=total_tracks_val
                    )

                    report_progress(
                        reporter=Download_JOB.progress_reporter,
                        callback_obj=error_callback_obj
                    )
                    
                    raise TrackNotFound(f"Failed to process {self.__song_path}. Error: {str(e_decrypt)}") from e_decrypt

                # Add Deezer-specific enhanced metadata and apply tags
                from deezspot.deezloader.deegw_api import API_GW
                enhanced_metadata = add_deezer_enhanced_metadata(
                    self.__song_metadata,
                    self.__infos_dw,
                    self.__ids,
                    API_GW
                )
                
                # Apply tags using unified utility
                process_and_tag_track(
                    track=self.__c_track,
                    metadata_dict=enhanced_metadata,
                    source_type='deezer',
                    save_cover=getattr(self.__preferences, 'save_cover', False)
                )

                if self.__convert_to:
                    format_name, bitrate = self._parse_format_string(self.__convert_to)
                    if format_name:
                        path_before_conversion = self.__song_path
                        try:
                            converted_path = convert_audio(
                                path_before_conversion, 
                                format_name, 
                                bitrate if bitrate else self.__bitrate,
                                register_active_download,
                                unregister_active_download
                            )
                            if converted_path != path_before_conversion:
                                self.__song_path = converted_path
                                self.__c_track.song_path = converted_path
                                _, new_ext = os.path.splitext(converted_path)
                                self.__file_format = new_ext.lower()
                                self.__c_track.file_format = new_ext.lower()
                        except Exception as conv_error:
                            logger.error(f"Audio conversion error: {str(conv_error)}. Proceeding with original format.")
                            register_active_download(path_before_conversion)

                # Apply tags using unified utility with Deezer enhancements
                from deezspot.deezloader.deegw_api import API_GW
                enhanced_metadata = add_deezer_enhanced_metadata(
                    self.__song_metadata,
                    self.__infos_dw,
                    self.__ids,
                    API_GW
                )
                process_and_tag_track(
                    track=self.__c_track,
                    metadata_dict=enhanced_metadata,
                    source_type='deezer'
                )
                self.__c_track.success = True
                unregister_active_download(self.__song_path)

            except Exception as e:
                unregister_active_download(self.__song_path)
                if isfile(self.__song_path):
                    try:
                        os.remove(self.__song_path)
                    except OSError:
                         logger.warning(f"Could not remove file on error: {self.__song_path}")
                
                error_msg = str(e)
                if "Data must be padded" in error_msg: error_msg = "Decryption error (padding issue) - Try a different quality setting or download format"
                elif isinstance(e, ConnectionError) or "Connection" in error_msg: error_msg = "Connection error - Check your internet connection"
                elif "timeout" in error_msg.lower(): error_msg = "Request timed out - Server may be busy"
                elif "403" in error_msg or "Forbidden" in error_msg: error_msg = "Access denied - Track might be region-restricted or premium-only"
                elif "404" in error_msg or "Not Found" in error_msg: error_msg = "Track not found - It might have been removed"
                
                error_status = errorObject(
                    ids=self.__track_obj.ids,
                    error=error_msg,
                    convert_to=self.__convert_to
                )
                
                callback_obj = trackCallbackObject(
                    track=self.__track_obj,
                    status_info=error_status,
                    parent=parent_obj,  # Use the same parent_obj created earlier
                    current_track=current_track_val,
                    total_tracks=total_tracks_val
                )

                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    callback_obj=callback_obj
                )
                logger.error(f"Failed to process track: {error_msg}")
                
                self.__c_track.success = False
                self.__c_track.error_message = error_msg
                raise TrackNotFound(f"Failed to process {self.__song_path}. Error: {error_msg}. Original Exception: {str(e)}")

            return self.__c_track

        except Exception as e:
            song_title = self.__song_metadata.get('music', 'Unknown Song')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            error_message = f"Download failed for '{song_title}' by '{artist_name}' (Link: {self.__link}). Error: {str(e)}"
            logger.error(error_message)
            unregister_active_download(self.__song_path)
            if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                self.__c_track.success = False
                self.__c_track.error_message = str(e)
            raise TrackNotFound(message=error_message, url=self.__link) from e

    def download_episode_try(self) -> Episode:
        try:
            direct_url = self.__infos_dw.get('EPISODE_DIRECT_STREAM_URL')
            if not direct_url:
                raise TrackNotFound("No direct stream URL found")

            os.makedirs(os.path.dirname(self.__song_path), exist_ok=True)
            
            register_active_download(self.__song_path)
            try:
                response = requests.get(direct_url, stream=True)
                response.raise_for_status()

                content_length = response.headers.get('content-length')
                total_size = int(content_length) if content_length else None

                downloaded = 0
                with open(self.__song_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            size = f.write(chunk)
                            downloaded += size
                            
                            # Download progress reporting could be added here
                
                # If download successful, unregister the initially downloaded file before potential conversion
                unregister_active_download(self.__song_path)


                # Build episode progress report
                progress_data = {
                    "type": "episode",
                    "song": self.__song_metadata.get('music', 'Unknown Episode'),
                    "artist": self.__song_metadata.get('artist', 'Unknown Show'),
                    "status": "done"
                }
                
                # Use Spotify URL if available (for downloadspo functions), otherwise use Deezer link
                spotify_url = getattr(self.__preferences, 'spotify_url', None)
                progress_data["url"] = spotify_url if spotify_url else self.__link
                
                Download_JOB.progress_reporter.report(progress_data)
                
                self.__c_track.success = True
                self.__write_episode()
                # Apply tags using unified utility with Deezer enhancements
                from deezspot.deezloader.deegw_api import API_GW
                enhanced_metadata = add_deezer_enhanced_metadata(
                    self.__song_metadata,
                    self.__infos_dw,
                    self.__ids,
                    API_GW
                )
                process_and_tag_track(
                    track=self.__c_track,
                    metadata_dict=enhanced_metadata,
                    source_type='deezer'
                )
            
                return self.__c_track

            except Exception as e_dw_ep: # Catches errors from requests.get, file writing
                unregister_active_download(self.__song_path) # Unregister if download part failed
                if isfile(self.__song_path):
                    try:
                        os.remove(self.__song_path)
                    except OSError:
                        logger.warning(f"Could not remove episode file on error: {self.__song_path}")
                self.__c_track.success = False # Mark as failed
                episode_title = self.__preferences.song_metadata.get('music', 'Unknown Episode')
                err_msg = f"Episode download failed for '{episode_title}' (URL: {self.__link}). Error: {str(e_dw_ep)}"
                logger.error(err_msg)
                self.__c_track.error_message = str(e_dw_ep)
                raise TrackNotFound(message=err_msg, url=self.__link) from e_dw_ep
        
        except Exception as e:
            if isfile(self.__song_path):
                os.remove(self.__song_path)
            self.__c_track.success = False
            episode_title = self.__preferences.song_metadata.get('music', 'Unknown Episode')
            err_msg = f"Episode download failed for '{episode_title}' (URL: {self.__link}). Error: {str(e)}"
            logger.error(err_msg)
            # Store error on track object
            self.__c_track.error_message = str(e)
            raise TrackNotFound(message=err_msg, url=self.__link) from e

    def _parse_format_string(self, format_str: str) -> tuple[str | None, str | None]:
        """Helper to parse format string like 'MP3_320K' into format and bitrate."""
        if not format_str:
            return None, None
        
        parts = format_str.upper().split('_', 1)
        format_name = parts[0]
        bitrate = parts[1] if len(parts) > 1 else None

        if format_name not in AUDIO_FORMATS:
            logger.warning(f"Unsupported format {format_name} in format string '{format_str}'. Will not convert.")
            return None, None

        if bitrate:
            # Ensure bitrate ends with 'K' for consistency if it's a number followed by K
            if bitrate[:-1].isdigit() and not bitrate.endswith('K'):
                bitrate += 'K'
            
            valid_bitrates = AUDIO_FORMATS[format_name].get("bitrates", [])
            if valid_bitrates and bitrate not in valid_bitrates:
                default_br = AUDIO_FORMATS[format_name].get("default_bitrate")
                logger.warning(f"Unsupported bitrate {bitrate} for {format_name}. Using default {default_br if default_br else 'as available'}.")
                bitrate = default_br # Fallback to default, or None if no specific default for lossless
            elif not valid_bitrates and AUDIO_FORMATS[format_name].get("default_bitrate") is None: # Lossless format
                logger.info(f"Bitrate {bitrate} specified for lossless format {format_name}. Bitrate will be ignored by converter.")
                # Keep bitrate as is, convert_audio will handle ignoring it for lossless.
        
        return format_name, bitrate

    # Removed __add_more_tags() - now handled by unified libutils/taggers.py

class DW_TRACK:
    def __init__(
        self,
        preferences: Preferences,
        parent: str = None
    ) -> None:

        self.__preferences = preferences
        self.__parent = parent
        self.__ids = self.__preferences.ids
        self.__song_metadata = self.__preferences.song_metadata
        self.__quality_download = self.__preferences.quality_download

    def dw(self) -> Track:
        from deezspot.deezloader.deegw_api import API_GW
        infos_dw = API_GW.get_song_data(self.__ids)

        media = Download_JOB.check_sources(
            [infos_dw], self.__quality_download
        )

        infos_dw['media_url'] = media[0]
        track = EASY_DW(infos_dw, self.__preferences, parent=self.__parent).easy_dw()

        if not track.success and not getattr(track, 'was_skipped', False):
            error_msg = getattr(track, 'error_message', "An unknown error occurred during download.")
            raise TrackNotFound(message=error_msg, url=track.link or self.__preferences.link)

        return track

class DW_ALBUM:
    def _album_object_to_dict(self, album_obj: albumCbObject) -> dict:
        """Converts an albumObject to a dictionary for tagging and path generation."""
        # Use the unified metadata converter
        return album_object_to_dict(album_obj, source_type='deezer')

    def _track_object_to_dict(self, track_obj: any, album_obj: albumCbObject) -> dict:
        """Converts a track object to a dictionary with album context."""
        # Check if track_obj is a trackAlbumObject which doesn't have its own album attribute
        if hasattr(track_obj, 'type') and track_obj.type == 'trackAlbum':
            # Create a trackObject with album reference from the provided album_obj
            from deezspot.models.callback.track import trackObject
            full_track = trackObject(
                title=track_obj.title,
                disc_number=track_obj.disc_number,
                track_number=track_obj.track_number,
                duration_ms=track_obj.duration_ms,
                explicit=track_obj.explicit,
                ids=track_obj.ids,
                artists=track_obj.artists,
                album=album_obj,  # Use the parent album
                genres=getattr(track_obj, 'genres', [])
            )
            # Use the unified metadata converter
            return track_object_to_dict(full_track, source_type='deezer')
        else:
            # Use the unified metadata converter
            return track_object_to_dict(track_obj, source_type='deezer')

    def __init__(
        self,
        preferences: Preferences
    ) -> None:

        self.__preferences = preferences
        self.__ids = self.__preferences.ids
        self.__make_zip = self.__preferences.make_zip
        self.__output_dir = self.__preferences.output_dir
        self.__not_interface = self.__preferences.not_interface
        self.__quality_download = self.__preferences.quality_download
        self.__recursive_quality = self.__preferences.recursive_quality
        album_obj: albumCbObject = self.__preferences.song_metadata
        self.__song_metadata = self._album_object_to_dict(album_obj)

    def dw(self) -> Album:
        from deezspot.deezloader.deegw_api import API_GW
        # Report album initializing status
        album_obj = self.__preferences.json_data
        # Report album initialization status
        report_album_initializing(album_obj)
        
        infos_dw = API_GW.get_album_data(self.__ids)['data']
        md5_image = infos_dw[0]['ALB_PICTURE']
        image_bytes = API.choose_img(md5_image, size="1400x1400")
        
        # Convert album object to dictionary for legacy functions
        album_dict = self._album_object_to_dict(album_obj)
        album_dict['image'] = image_bytes

        album = Album(self.__ids)
        album.image = image_bytes
        album.md5_image = md5_image
        album.nb_tracks = album_obj.total_tracks
        album.album_name = album_obj.title
        album.upc = album_obj.ids.upc
        album.tags = album_dict
        tracks = album.tracks

        medias = Download_JOB.check_sources(infos_dw, self.__quality_download)
        
        album_base_directory = get_album_directory(
            album.tags,
            self.__output_dir,
            custom_dir_format=self.__preferences.custom_dir_format,
            pad_tracks=self.__preferences.pad_tracks
        )
        
        # Save cover to album directory
        if self.__preferences.save_cover and album.image and album_base_directory:
            save_cover_image(album.image, album_base_directory, "cover.jpg")
            
        total_tracks = len(infos_dw)
        for a, album_track_obj in enumerate(album_obj.tracks):
            c_infos_dw_item = infos_dw[a] 
            
            # Update track object with proper track position and disc number from API
            if 'track_position' in c_infos_dw_item:
                album_track_obj.track_number = c_infos_dw_item['track_position']
            if 'disk_number' in c_infos_dw_item:
                album_track_obj.disc_number = c_infos_dw_item['disk_number']
            
            # Ensure we have valid values, not None
            if album_track_obj.track_number is None:
                album_track_obj.track_number = a + 1  # Fallback to sequential if API doesn't provide
            if album_track_obj.disc_number is None:
                album_track_obj.disc_number = 1
                
            c_infos_dw_item['media_url'] = medias[a]
            c_preferences = deepcopy(self.__preferences)
            
            try:
                # Create full track object with album context
                from deezspot.models.callback.track import trackObject
                full_track_obj = trackObject(
                    title=album_track_obj.title,
                    disc_number=album_track_obj.disc_number,
                    track_number=album_track_obj.track_number,
                    duration_ms=album_track_obj.duration_ms,
                    explicit=album_track_obj.explicit,
                    ids=album_track_obj.ids,
                    artists=album_track_obj.artists,
                    album=album_obj,  # Set the parent album
                    genres=getattr(album_track_obj, 'genres', [])
                )
                
                c_preferences.song_metadata = full_track_obj
                c_preferences.ids = full_track_obj.ids.deezer
                c_preferences.track_number = a + 1  # For progress reporting only
                c_preferences.total_tracks = total_tracks
                c_preferences.link = f"https://deezer.com/track/{c_preferences.ids}"
                
                current_track_object = EASY_DW(c_infos_dw_item, c_preferences, parent='album').easy_dw()
            except Exception as e:
                logger.error(f"Track '{album_track_obj.title}' in album '{album_obj.title}' failed: {e}")
                # Create a simple track metadata dict manually since we don't have EASY_DW to process it
                track_metadata = self._track_object_to_dict(album_track_obj, album_obj)
                current_track_object = Track(track_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e)
            
            if current_track_object:
                tracks.append(current_track_object)

        if self.__make_zip:
            song_quality = tracks[0].quality if tracks else 'Unknown'
            custom_dir_format = getattr(self.__preferences, 'custom_dir_format', None)
            zip_name = create_zip(
                tracks,
                output_dir=self.__output_dir,
                song_metadata=album_dict,
                song_quality=song_quality,
                custom_dir_format=custom_dir_format
            )
            album.zip_path = zip_name

        successful_tracks_cb = []
        failed_tracks_cb = []
        skipped_tracks_cb = []
        
        for track, track_obj in zip(tracks, album_obj.tracks):
            if getattr(track, 'was_skipped', False):
                skipped_tracks_cb.append(track_obj)
            elif track.success:
                successful_tracks_cb.append(track_obj)
            else:
                failed_tracks_cb.append(failedTrackObject(
                    track=track_obj,
                    reason=getattr(track, 'error_message', 'Unknown reason')
                ))

        summary_obj = summaryObject(
            successful_tracks=successful_tracks_cb,
            skipped_tracks=skipped_tracks_cb,
            failed_tracks=failed_tracks_cb,
            total_successful=len(successful_tracks_cb),
            total_skipped=len(skipped_tracks_cb),
            total_failed=len(failed_tracks_cb)
        )
        
        # Report album completion status
        report_album_done(album_obj, summary_obj)
        
        return album

class DW_PLAYLIST:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:

        self.__preferences = preferences
        self.__ids = self.__preferences.ids
        self.__json_data = preferences.json_data
        self.__make_zip = self.__preferences.make_zip
        self.__output_dir = self.__preferences.output_dir
        self.__song_metadata = self.__preferences.song_metadata
        self.__quality_download = self.__preferences.quality_download

    def _track_object_to_dict(self, track_obj: any) -> dict:
        # Use the unified metadata converter
        return track_object_to_dict(track_obj, source_type='deezer')

    def dw(self) -> Playlist:
        playlist_obj: playlistCbObject = self.__preferences.json_data
        
        status_obj_init = initializingObject(ids=playlist_obj.ids)
        callback_obj_init = playlistCallbackObject(playlist=playlist_obj, status_info=status_obj_init)
        report_progress(
            reporter=Download_JOB.progress_reporter,
            callback_obj=callback_obj_init
        )
        
        from deezspot.deezloader.deegw_api import API_GW
        infos_dw = API_GW.get_playlist_data(self.__ids)['data']
        playlist_name_sanitized = sanitize_name(playlist_obj.title)
        
        playlist = Playlist()
        tracks = playlist.tracks

        m3u_path = create_m3u_file(self.__output_dir, playlist_obj.title)

        medias = Download_JOB.check_sources(infos_dw, self.__quality_download)

        successful_tracks_cb = []
        failed_tracks_cb = []
        skipped_tracks_cb = []
        
        total_tracks = len(infos_dw)

        for idx in range(total_tracks):
            c_infos_dw_item = infos_dw[idx]
            c_media = medias[idx]
            c_track_obj = playlist_obj.tracks[idx] if idx < len(playlist_obj.tracks) else None


            if not c_track_obj or not c_track_obj.ids or not c_track_obj.ids.deezer:
                logger.warning(f"Skipping item {idx + 1} in playlist '{playlist_obj.title}' as it's not a valid track object.")
                from deezspot.models.callback.track import trackObject as trackCbObject
                unknown_track = trackCbObject(title="Unknown Skipped Item")
                reason = "Playlist item was not a valid track object."
                
                failed_tracks_cb.append(failedTrackObject(track=unknown_track, reason=reason))
                
                failed_track_model = Track(
                    tags={'music': 'Unknown Skipped Item', 'artist': 'Unknown'},
                    song_path=None, file_format=None, quality=None, link=None, ids=None
                )
                failed_track_model.success = False
                failed_track_model.error_message = reason
                tracks.append(failed_track_model)
                continue

            c_infos_dw_item['media_url'] = c_media
            c_preferences = deepcopy(self.__preferences)
            c_preferences.ids = c_track_obj.ids.deezer
            c_preferences.song_metadata = c_track_obj
            c_preferences.track_number = idx + 1
            c_preferences.total_tracks = total_tracks
            c_preferences.json_data = self.__preferences.json_data
            c_preferences.link = f"https://deezer.com/track/{c_preferences.ids}"

            current_track_object = None
            try:
                current_track_object = EASY_DW(c_infos_dw_item, c_preferences, parent='playlist').easy_dw()
                
                if getattr(current_track_object, 'was_skipped', False):
                    skipped_tracks_cb.append(c_track_obj)
                elif current_track_object.success:
                    successful_tracks_cb.append(c_track_obj)
                else:
                    failed_tracks_cb.append(failedTrackObject(
                        track=c_track_obj,
                        reason=getattr(current_track_object, 'error_message', 'Unknown reason')
                    ))
            except Exception as e:
                logger.error(f"Track '{c_track_obj.title}' in playlist '{playlist_obj.title}' failed: {e}")
                failed_tracks_cb.append(failedTrackObject(track=c_track_obj, reason=str(e)))
                current_track_object = Track(self._track_object_to_dict(c_track_obj), None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e)

            if current_track_object:
                tracks.append(current_track_object)
                if current_track_object.success and hasattr(current_track_object, 'song_path') and current_track_object.song_path:
                    append_track_to_m3u(m3u_path, current_track_object)

        if self.__make_zip:
            zip_name = f"{self.__output_dir}/{playlist_obj.title} [playlist {self.__ids}]"
            create_zip(tracks, zip_name=zip_name)
            playlist.zip_path = zip_name

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
        report_progress(
            reporter=Download_JOB.progress_reporter,
            callback_obj=callback_obj_done
        )
        
        return playlist

class DW_EPISODE:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:
        self.__preferences = preferences
        self.__ids = preferences.ids
        self.__output_dir = preferences.output_dir
        self.__not_interface = preferences.not_interface
        self.__quality_download = preferences.quality_download
        
    def dw(self) -> Track:
        from deezspot.deezloader.deegw_api import API_GW
        infos_dw = API_GW.get_episode_data(self.__ids)
        infos_dw['__TYPE__'] = 'episode'
        
        self.__preferences.song_metadata = {
            'music': infos_dw.get('EPISODE_TITLE', ''),
            'artist': infos_dw.get('SHOW_NAME', ''),
            'album': infos_dw.get('SHOW_NAME', ''),
            'date': infos_dw.get('EPISODE_PUBLISHED_TIMESTAMP', '').split()[0],
            'genre': 'Podcast',
            'explicit': infos_dw.get('SHOW_IS_EXPLICIT', '2'),
            'duration': int(infos_dw.get('DURATION', 0)),
        }
        
        try:
            direct_url = infos_dw.get('EPISODE_DIRECT_STREAM_URL')
            if not direct_url:
                raise TrackNotFound("No direct URL found")
            
            from deezspot.libutils.utils import sanitize_name
            from pathlib import Path
            safe_filename = sanitize_name(self.__preferences.song_metadata['music'])
            Path(self.__output_dir).mkdir(parents=True, exist_ok=True)
            output_path = os.path.join(self.__output_dir, f"{safe_filename}.mp3")
            
            response = requests.get(direct_url, stream=True)
            response.raise_for_status()

            content_length = response.headers.get('content-length')
            total_size = int(content_length) if content_length else None

            downloaded = 0
            total_size = int(response.headers.get('content-length', 0))
            
            # Send initial progress status
            parent = {
                "type": "show",
                "title": self.__preferences.song_metadata.get('artist', ''),
                "artist": self.__preferences.song_metadata.get('artist', '')
            }
            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="episode",
                song=self.__preferences.song_metadata.get('music', ''),
                artist=self.__preferences.song_metadata.get('artist', ''),
                status="initializing",
                url=f"https://www.deezer.com/episode/{self.__ids}",
                parent=parent
            )
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            episode = Track(
                self.__preferences.song_metadata,
                output_path,
                '.mp3',
                self.__quality_download, 
                f"https://www.deezer.com/episode/{self.__ids}",
                self.__ids
            )
            episode.success = True
            
            # Send completion status
            parent = {
                "type": "show",
                "title": self.__preferences.song_metadata.get('artist', ''),
                "artist": self.__preferences.song_metadata.get('artist', '')
            }
            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="episode",
                song=self.__preferences.song_metadata.get('music', ''),
                artist=self.__preferences.song_metadata.get('artist', ''),
                status="done",
                url=f"https://www.deezer.com/episode/{self.__ids}",
                parent=parent
            )
            
            # Save cover image for the episode
            if self.__preferences.save_cover:
                episode_image_md5 = infos_dw.get('EPISODE_IMAGE_MD5', '')
                episode_image_data = None
                if episode_image_md5:
                    episode_image_data = API.choose_img(episode_image_md5, size="1200x1200")
                
                if episode_image_data:
                    episode_directory = os.path.dirname(output_path)
                    save_cover_image(episode_image_data, episode_directory, "cover.jpg")

            return episode
            
        except Exception as e:
            if 'output_path' in locals() and os.path.exists(output_path):
                os.remove(output_path)
            episode_title = self.__preferences.song_metadata.get('music', 'Unknown Episode')
            err_msg = f"Episode download failed for '{episode_title}' (URL: {self.__preferences.link}). Error: {str(e)}"
            logger.error(err_msg)
            # Add original error to exception
            raise TrackNotFound(message=err_msg, url=self.__preferences.link) from e
