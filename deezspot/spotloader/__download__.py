import traceback
import json
import os
import time
from copy import deepcopy
from os.path import isfile, dirname
from librespot.core import Session
from deezspot.exceptions import TrackNotFound
from librespot.metadata import TrackId, EpisodeId
from deezspot.spotloader.spotify_settings import qualities
from deezspot.libutils.others_settings import answers
from deezspot.__taggers__ import write_tags, check_track
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from deezspot.libutils.audio_converter import convert_audio, AUDIO_FORMATS, get_output_path
from os import (
    remove,
    system,
    replace as os_replace,
)
from deezspot.models import (
    Track,
    Album,
    Playlist,
    Preferences,
    Episode,
)
from deezspot.libutils.utils import (
    set_path,
    create_zip,
    request,
    sanitize_name,
    save_cover_image,
    __get_dir as get_album_directory,
)
from deezspot.libutils.logging_utils import logger, report_progress
from deezspot.libutils.cleanup_utils import (
    register_active_download,
    unregister_active_download,
)
from deezspot.libutils.skip_detection import check_track_exists

# --- Global retry counter variables ---
GLOBAL_RETRY_COUNT = 0
GLOBAL_MAX_RETRIES = 100  # Adjust this value as needed

# --- Global tracking of active downloads ---
# Moved to deezspot.libutils.cleanup_utils

class Download_JOB:
    session = None
    progress_reporter = None

    @classmethod
    def __init__(cls, session: Session) -> None:
        cls.session = session

    @classmethod
    def set_progress_reporter(cls, reporter):
        cls.progress_reporter = reporter

class EASY_DW:
    def __init__(
        self,
        preferences: Preferences,
        parent: str = None  # Can be 'album', 'playlist', or None for individual track
    ) -> None:
        
        self.__preferences = preferences
        self.__parent = parent  # Store the parent type

        self.__ids = preferences.ids
        self.__link = preferences.link
        self.__output_dir = preferences.output_dir
        self.__song_metadata = preferences.song_metadata
        self.__not_interface = preferences.not_interface
        self.__quality_download = preferences.quality_download or "NORMAL"
        self.__recursive_download = preferences.recursive_download
        self.__type = "episode" if preferences.is_episode else "track"  # New type parameter
        self.__real_time_dl = preferences.real_time_dl
        self.__convert_to = getattr(preferences, 'convert_to', None)
        self.__bitrate = getattr(preferences, 'bitrate', None) # New bitrate attribute

        # Ensure if convert_to is None, bitrate is also None
        if self.__convert_to is None:
            self.__bitrate = None

        self.__c_quality = qualities[self.__quality_download]
        self.__fallback_ids = self.__ids

        self.__set_quality()
        if preferences.is_episode:
            self.__write_episode()
        else:
            self.__write_track()

    def __set_quality(self) -> None:
        self.__dw_quality = self.__c_quality['n_quality']
        self.__file_format = self.__c_quality['f_format']
        self.__song_quality = self.__c_quality['s_quality']

    def __set_song_path(self) -> None:
        # Retrieve custom formatting strings from preferences, if any.
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
        self.__c_track.md5_image = self.__ids
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

    def _get_parent_info(self):
        parent_info = None
        total_tracks_val = None
        if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
            playlist_data = self.__preferences.json_data
            total_tracks_val = playlist_data.get('tracks', {}).get('total', 'unknown')
            parent_info = {
                "type": "playlist",
                "name": playlist_data.get('name', 'unknown'),
                "owner": playlist_data.get('owner', {}).get('display_name', 'unknown'),
                "total_tracks": total_tracks_val,
                "url": f"https://open.spotify.com/playlist/{playlist_data.get('id', '')}"
            }
        elif self.__parent == "album":
            total_tracks_val = self.__song_metadata.get('nb_tracks', 0)
            parent_info = {
                "type": "album",
                "title": self.__song_metadata.get('album', ''),
                "artist": self.__song_metadata.get('album_artist', self.__song_metadata.get('ar_album', '')),
                "total_tracks": total_tracks_val,
                "url": f"https://open.spotify.com/album/{self.__song_metadata.get('album_id', '')}"
            }
        return parent_info, total_tracks_val

    def __convert_audio(self) -> None:
        # First, handle Spotify's OGG to standard format conversion (always needed)
        # self.__song_path is initially the path for the .ogg file (e.g., song.ogg)
        og_song_path_for_ogg_output = self.__song_path
        temp_filename = og_song_path_for_ogg_output.replace(".ogg", ".tmp")

        # Move original .ogg to .tmp
        os_replace(og_song_path_for_ogg_output, temp_filename)
        register_active_download(temp_filename) # CURRENT_DOWNLOAD = temp_filename
        
        try:
            # Step 1: First convert the OGG file to standard format (copy operation)
            # Output is og_song_path_for_ogg_output
            ffmpeg_cmd = f'ffmpeg -y -hide_banner -loglevel error -i "{temp_filename}" -c:a copy "{og_song_path_for_ogg_output}"'
            system(ffmpeg_cmd) # Creates/overwrites og_song_path_for_ogg_output
            
            # temp_filename has been processed. Unregister and remove it.
            # CURRENT_DOWNLOAD was temp_filename.
            unregister_active_download(temp_filename) # CURRENT_DOWNLOAD should become None.
            if os.path.exists(temp_filename):
                remove(temp_filename)
            
            # The primary file is now og_song_path_for_ogg_output. Register it.
            # Ensure self.__song_path reflects this, as it might be used by other parts of the class or returned.
            self.__song_path = og_song_path_for_ogg_output
            register_active_download(self.__song_path) # CURRENT_DOWNLOAD = self.__song_path (the .ogg)
            
            # Step 2: Convert to requested format if specified (e.g., MP3, FLAC)
            conversion_to_another_format_occurred_and_cleared_state = False
            if self.__convert_to:
                format_name = self.__convert_to
                bitrate = self.__bitrate
                if format_name:
                    try:
                        path_before_final_conversion = self.__song_path # Current path, e.g., .ogg
                        converted_path = convert_audio(
                            path_before_final_conversion, 
                            format_name,
                            bitrate,
                            register_active_download,
                            unregister_active_download
                        )
                        if converted_path != path_before_final_conversion:
                            # Conversion to a new format happened and path changed
                            self.__song_path = converted_path # Update EASY_DW's current song path

                            current_object_path_attr_name = 'song_path' if self.__type == "track" else 'episode_path'
                            current_media_object = self.__c_track if self.__type == "track" else self.__c_episode
                            
                            if current_media_object:
                                setattr(current_media_object, current_object_path_attr_name, converted_path)
                                _, new_ext = os.path.splitext(converted_path)
                                if new_ext:
                                    current_media_object.file_format = new_ext.lower()
                                    # Also update EASY_DW's internal __file_format
                                    self.__file_format = new_ext.lower()
                        
                        conversion_to_another_format_occurred_and_cleared_state = True
                    except Exception as conv_error:
                        # Conversion to a different format failed.
                        # self.__song_path (the .ogg) is still the latest valid file and is registered.
                        # We want to keep it, so CURRENT_DOWNLOAD should remain set to this .ogg path.
                        logger.error(f"Audio conversion to {format_name} error: {str(conv_error)}")
                        # conversion_to_another_format_occurred_and_cleared_state remains False.
            
            # If no conversion to another format was requested, or if it was requested but didn't effectively run
            # (e.g. format_name was None), or if convert_audio failed to clear state (which would be its bug),
            # then self.__song_path (the .ogg from Step 1) is the final successfully processed file for this method's scope.
            # It is currently registered. Unregister it as its processing is complete.
            if not conversion_to_another_format_occurred_and_cleared_state:
                unregister_active_download(self.__song_path) # Clears CURRENT_DOWNLOAD if it was self.__song_path
                
        except Exception as e:
            # This outer try/except handles errors primarily from Step 1 (OGG copy)
            # or issues during the setup for Step 2 before convert_audio is deeply involved.
            # In case of failure, try to restore the original file from temp if Step 1 didn't complete.
            if os.path.exists(temp_filename) and not os.path.exists(og_song_path_for_ogg_output):
                os_replace(temp_filename, og_song_path_for_ogg_output)
            
            # Clean up temp_filename. unregister_active_download is safe:
            # it only clears CURRENT_DOWNLOAD if CURRENT_DOWNLOAD == temp_filename.
            if os.path.exists(temp_filename):
                unregister_active_download(temp_filename)
                remove(temp_filename)
                
            # Re-throw the exception. If a file (like og_song_path_for_ogg_output) was registered
            # and an error occurred, it remains registered for atexit cleanup, which is intended.
            raise e

    def get_no_dw_track(self) -> Track:
        return self.__c_track

    def easy_dw(self) -> Track:
        # Request the image data
        pic = self.__song_metadata['image']
        image = request(pic).content
        self.__song_metadata['image'] = image

        try:
            # Initialize success to False, it will be set to True if download_try is successful
            if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                self.__c_track.success = False
            elif hasattr(self, '_EASY_DW__c_episode') and self.__c_episode: # For episodes
                self.__c_episode.success = False
            
            self.download_try() # This should set self.__c_track.success = True if successful

        except Exception as e:
            song_title = self.__song_metadata.get('music', 'Unknown Song')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            error_message = f"Download failed for '{song_title}' by '{artist_name}' (URL: {self.__link}). Original error: {str(e)}"
            logger.error(error_message)
            traceback.print_exc()
            # Store the error message on the track object if it exists
            if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                self.__c_track.success = False
                self.__c_track.error_message = error_message # Store the more detailed error message
            # Removed problematic elif for __c_episode here as easy_dw in spotloader is focused on tracks.
            # Episode-specific error handling should be within download_eps or its callers.
            raise TrackNotFound(message=error_message, url=self.__link) from e
        
        # If the track was skipped (e.g. file already exists), return it immediately.
        # download_try sets success=False and was_skipped=True in this case.
        if hasattr(self, '_EASY_DW__c_track') and self.__c_track and getattr(self.__c_track, 'was_skipped', False):
            return self.__c_track

        # Final check for non-skipped tracks that might have failed after download_try returned.
        # This handles cases where download_try didn't raise an exception but self.__c_track.success is still False.
        if hasattr(self, '_EASY_DW__c_track') and self.__c_track and not self.__c_track.success:
            song_title = self.__song_metadata.get('music', 'Unknown Song')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            original_error_msg = getattr(self.__c_track, 'error_message', "Download failed for an unspecified reason after attempt.")
            error_msg_template = "Cannot download '{title}' by '{artist}'. Reason: {reason}"
            final_error_msg = error_msg_template.format(title=song_title, artist=artist_name, reason=original_error_msg)
            current_link = self.__c_track.link if hasattr(self.__c_track, 'link') and self.__c_track.link else self.__link
            logger.error(f"{final_error_msg} (URL: {current_link})")
            self.__c_track.error_message = final_error_msg # Ensure the most specific error is on the object
            raise TrackNotFound(message=final_error_msg, url=current_link)
            
        # If we reach here, the track should be successful and not skipped.
        if hasattr(self, '_EASY_DW__c_track') and self.__c_track and self.__c_track.success:
            write_tags(self.__c_track)
        
        # Unregister the final successful file path after all operations are done.
        # self.__c_track.song_path would have been updated by __convert_audio__ if conversion occurred.
        unregister_active_download(self.__c_track.song_path)
        
        return self.__c_track

    def download_try(self) -> Track:
        current_title = self.__song_metadata.get('music')
        current_album = self.__song_metadata.get('album')
        current_artist = self.__song_metadata.get('artist')

        # Call the new check_track_exists function from skip_detection.py
        # It needs: original_song_path, title, album, convert_to, logger
        # self.__song_path is the original_song_path before any conversion attempts by this specific download operation.
        # self.__preferences.convert_to is the convert_to parameter.
        # logger is available as a global import in this module.
        exists, existing_file_path = check_track_exists(
            original_song_path=self.__song_path, 
            title=current_title, 
            album=current_album, 
            convert_to=self.__preferences.convert_to, 
            logger=logger # Pass the logger instance
        )

        if exists and existing_file_path:
            logger.info(f"Track '{current_title}' by '{current_artist}' already exists at '{existing_file_path}'. Skipping download and conversion.")
            # Update the track object to point to the existing file
            self.__c_track.song_path = existing_file_path
            _, new_ext = os.path.splitext(existing_file_path)
            self.__c_track.file_format = new_ext.lower() # Ensure it's just the extension like '.mp3'
            # self.__c_track.song_quality might need re-evaluation if we could determine quality of existing file
            # For now, assume if it exists in target format, its quality is acceptable.
            
            self.__c_track.success = True # Mark as success because the desired file is available
            self.__c_track.was_skipped = True

            parent_info, total_tracks_val = self._get_parent_info()
            
            summary_data = {
                "successful_tracks": [],
                "skipped_tracks": [f"{current_title} - {current_artist}"],
                "failed_tracks": [],
                "total_successful": 0,
                "total_skipped": 1,
                "total_failed": 0,
            } if self.__parent is None else None

            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="track",
                status="skipped",
                song=current_title,
                artist=current_artist,
                url=self.__link,
                reason=f"Track already exists in desired format at {existing_file_path}",
                convert_to=self.__preferences.convert_to,
                bitrate=self.__preferences.bitrate,
                current_track=getattr(self.__preferences, 'track_number', None),
                total_tracks=total_tracks_val,
                parent=parent_info,
                summary=summary_data
            )
            return self.__c_track

        # Report initializing status for the track download
        parent_info, total_tracks_val = self._get_parent_info()
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="track",
            status="initializing",
            song=current_title,
            artist=current_artist,
            album=current_album,
            url=self.__link,
            convert_to=self.__preferences.convert_to,
            bitrate=self.__preferences.bitrate,
            parent=parent_info,
            current_track=getattr(self.__preferences, 'track_number', None),
            total_tracks=total_tracks_val,
        )
        
        # If track does not exist in the desired final format, proceed with download/conversion
        retries = 0
        # Use the customizable retry parameters
        retry_delay = getattr(self.__preferences, 'initial_retry_delay', 30)  # Default to 30 seconds
        retry_delay_increase = getattr(self.__preferences, 'retry_delay_increase', 30)  # Default to 30 seconds
        max_retries = getattr(self.__preferences, 'max_retries', 5)  # Default to 5 retries

        while True:
            try:
                track_id_obj = TrackId.from_base62(self.__ids)
                stream = Download_JOB.session.content_feeder().load_track(
                    track_id_obj,
                    VorbisOnlyAudioQuality(self.__dw_quality),
                    False,
                    None
                )
                c_stream = stream.input_stream.stream()
                total_size = stream.input_stream.size
                
                os.makedirs(dirname(self.__song_path), exist_ok=True)
                
                # Register this file as being actively downloaded
                register_active_download(self.__song_path)
                
                try:
                    with open(self.__song_path, "wb") as f:
                        if self.__real_time_dl and self.__song_metadata.get("duration"):
                            # Real-time download path
                            duration = self.__song_metadata["duration"]
                            if duration > 0:
                                rate_limit = total_size / duration
                                chunk_size = 4096
                                bytes_written = 0
                                start_time = time.time()
                                
                                # Initialize tracking variable for percentage reporting
                                self._last_reported_percentage = -1
                                
                                while True:
                                    chunk = c_stream.read(chunk_size)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                                    bytes_written += len(chunk)
                                    
                                    # Calculate current percentage (as integer)
                                    current_time = time.time()
                                    current_percentage = int((bytes_written / total_size) * 100)
                                    
                                    # Only report when percentage increases by at least 1 point
                                    if current_percentage > self._last_reported_percentage:
                                        self._last_reported_percentage = current_percentage
                                        
                                        report_progress(
                                            reporter=Download_JOB.progress_reporter,
                                            report_type="track",
                                            status="real-time",
                                            song=self.__song_metadata.get("music", ""),
                                            artist=self.__song_metadata.get("artist", ""),
                                            url=self.__link,
                                            time_elapsed=int((current_time - start_time) * 1000),
                                            progress=current_percentage,
                                            convert_to=self.__convert_to,
                                            bitrate=self.__bitrate,
                                            current_track=getattr(self.__preferences, 'track_number', None),
                                            total_tracks=total_tracks_val,
                                            parent=parent_info
                                        )
                                        
                                    # Rate limiting (if needed)
                                    expected_time = bytes_written / rate_limit
                                    if expected_time > (time.time() - start_time):
                                        time.sleep(expected_time - (time.time() - start_time))
                        else:
                            # Non real-time download path
                            data = c_stream.read(total_size)
                            f.write(data)
                    
                    # Close the stream after successful write
                    c_stream.close()
                    
                    # After successful download, unregister the file
                    unregister_active_download(self.__song_path)
                    break
                    
                except Exception as e:
                    # Handle any exceptions that might occur during download
                    error_msg = f"Error during download process: {str(e)}"
                    logger.error(error_msg)
                    
                    # Clean up resources
                    if 'c_stream' in locals():
                        try:
                            c_stream.close()
                        except Exception:
                            pass
                    
                    # Remove partial download if it exists
                    if os.path.exists(self.__song_path):
                        try:
                            os.remove(self.__song_path)
                        except Exception:
                            pass
                    
                    # Unregister the download
                    unregister_active_download(self.__song_path)
                    
                # After successful download, unregister the file (moved here from below)
                unregister_active_download(self.__song_path)
                break
                
            except Exception as e:
                # Handle retry logic
                global GLOBAL_RETRY_COUNT
                GLOBAL_RETRY_COUNT += 1
                retries += 1
                
                # Clean up any incomplete file
                if os.path.exists(self.__song_path):
                    os.remove(self.__song_path)
                unregister_active_download(self.__song_path)
                progress_data = {
                    "type": "track",
                    "status": "retrying",
                    "retry_count": retries,
                    "seconds_left": retry_delay,
                    "song": self.__song_metadata.get('music', ''),
                    "artist": self.__song_metadata.get('artist', ''),
                    "album": self.__song_metadata.get('album', ''),
                    "error": str(e),
                    "url": self.__link,
                    "convert_to": self.__convert_to,
                    "bitrate": self.__bitrate
                }
                
                # Add parent info based on parent type
                if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
                    playlist_data = self.__preferences.json_data
                    playlist_name = playlist_data.get('name', 'unknown')
                    total_tracks = playlist_data.get('tracks', {}).get('total', 'unknown')
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    playlist_owner = playlist_data.get('owner', {}).get('display_name', 'unknown')
                    playlist_id = playlist_data.get('id', '')
                    
                    progress_data.update({
                        "current_track": current_track,
                        "total_tracks": total_tracks,
                        "parent": {
                            "type": "playlist",
                            "name": playlist_name,
                            "owner": playlist_owner,
                            "total_tracks": total_tracks,
                            "url": f"https://open.spotify.com/playlist/{playlist_id}"
                        }
                    })
                elif self.__parent == "album":
                    album_name = self.__song_metadata.get('album', '')
                    album_artist = self.__song_metadata.get('album_artist', self.__song_metadata.get('ar_album', ''))
                    total_tracks = self.__song_metadata.get('nb_tracks', 0)
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    album_id = self.__song_metadata.get('album_id', '')
                    
                    progress_data.update({
                        "current_track": current_track,
                        "total_tracks": total_tracks,
                        "parent": {
                            "type": "album",
                            "title": album_name,
                            "artist": album_artist,
                            "total_tracks": total_tracks,
                            "url": f"https://open.spotify.com/album/{album_id}"
                        }
                    })
                    
                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    report_type="track",
                    status="retrying",
                    retry_count=retries,
                    seconds_left=retry_delay,
                    song=self.__song_metadata.get('music', ''),
                    artist=self.__song_metadata.get('artist', ''),
                    album=self.__song_metadata.get('album', ''),
                    error=str(e),
                    url=self.__link,
                    convert_to=self.__convert_to,
                    bitrate=self.__bitrate,
                    current_track=getattr(self.__preferences, 'track_number', None),
                    total_tracks=total_tracks_val,
                    parent=parent_info
                )
                    
                if retries >= max_retries or GLOBAL_RETRY_COUNT >= GLOBAL_MAX_RETRIES:
                    # Final cleanup before giving up
                    if os.path.exists(self.__song_path):
                        os.remove(self.__song_path)
                    # Add track info to exception    
                    track_name = self.__song_metadata.get('music', 'Unknown Track')
                    artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
                    final_error_msg = f"Maximum retry limit reached for '{track_name}' by '{artist_name}' (local: {max_retries}, global: {GLOBAL_MAX_RETRIES}). Last error: {str(e)}"
                    # Store error on track object
                    if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                        self.__c_track.success = False
                        self.__c_track.error_message = final_error_msg
                    raise Exception(final_error_msg) from e
                time.sleep(retry_delay)
                retry_delay += retry_delay_increase  # Use the custom retry delay increase
                
        # Save cover image if requested, after successful download and before conversion
        if self.__preferences.save_cover and hasattr(self, '_EASY_DW__song_path') and self.__song_path and self.__song_metadata.get('image'):
            try:
                track_directory = dirname(self.__song_path)
                # Ensure the directory exists (it should, from os.makedirs earlier)
                save_cover_image(self.__song_metadata['image'], track_directory, "cover.jpg")
                logger.info(f"Saved cover image for track in {track_directory}")
            except Exception as e_img_save:
                logger.warning(f"Failed to save cover image for track: {e_img_save}")

        try:
            self.__convert_audio()
        except Exception as e:
            # Improve error message formatting
            original_error_str = str(e)
            if "codec" in original_error_str.lower():
                error_msg = "Audio conversion error - Missing codec or unsupported format"
            elif "ffmpeg" in original_error_str.lower():
                error_msg = "FFmpeg error - Audio conversion failed"
            else:
                error_msg = f"Audio conversion failed: {original_error_str}"
            
            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="track",
                status="error",
                song=self.__song_metadata.get('music', ''),
                artist=self.__song_metadata.get('artist', ''),
                error=error_msg,
                url=self.__link,
                convert_to=self.__convert_to,
                bitrate=self.__bitrate,
                current_track=getattr(self.__preferences, 'track_number', None),
                total_tracks=total_tracks_val,
                parent=parent_info
            )
            logger.error(f"Audio conversion error: {error_msg}")
            
            # If conversion fails, clean up the .ogg file
            if os.path.exists(self.__song_path):
                os.remove(self.__song_path)
                
            # Try one more time
            time.sleep(retry_delay)
            retry_delay += retry_delay_increase
            try:
                self.__convert_audio()
            except Exception as conv_e:
                # If conversion fails twice, create a final error report
                error_msg_2 = f"Audio conversion failed after retry for '{self.__song_metadata.get('music', 'Unknown Track')}'. Original error: {str(conv_e)}"
                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    report_type="track",
                    status="error",
                    song=self.__song_metadata.get('music', 'Unknown Track'),
                    artist=self.__song_metadata.get('artist', ''),
                    error=error_msg_2,
                    url=self.__link,
                    convert_to=self.__convert_to,
                    bitrate=self.__bitrate,
                    parent=parent_info,
                    current_track=getattr(self.__preferences, 'track_number', None),
                    total_tracks=total_tracks_val
                )
                logger.error(error_msg)
                
                if os.path.exists(self.__song_path):
                    os.remove(self.__song_path)
                # Store error on track object
                if hasattr(self, '_EASY_DW__c_track') and self.__c_track:
                    self.__c_track.success = False
                    self.__c_track.error_message = error_msg
                raise TrackNotFound(message=error_msg, url=self.__link) from conv_e

        if hasattr(self, '_EASY_DW__c_track') and self.__c_track: 
            self.__c_track.success = True
            write_tags(self.__c_track)
        
        # Create done status report
        song = self.__song_metadata.get("music", "")
        artist = self.__song_metadata.get("artist", "")
        parent_info, total_tracks_val = self._get_parent_info()
        current_track_val = None
        summary_data = None

        if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
            playlist_data = self.__preferences.json_data
            total_tracks_val = playlist_data.get('tracks', {}).get('total', 'unknown')
            current_track_val = getattr(self.__preferences, 'track_number', 0)
        elif self.__parent == "album":
            total_tracks_val = self.__song_metadata.get('nb_tracks', 0)
            current_track_val = getattr(self.__preferences, 'track_number', 0)

        if self.__parent is None:
            summary_data = {
                "successful_tracks": [f"{song} - {artist}"],
                "skipped_tracks": [],
                "failed_tracks": [],
                "total_successful": 1,
                "total_skipped": 0,
                "total_failed": 0,
            }

        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="track",
            status="done",
            song=song,
            artist=artist,
            url=self.__link,
            convert_to=self.__convert_to,
            bitrate=self.__bitrate,
            parent=parent_info,
            current_track=current_track_val,
            total_tracks=total_tracks_val,
            summary=summary_data,
        )

        if hasattr(self, '_EASY_DW__c_track') and self.__c_track and self.__c_track.success:
            # Unregister the final successful file path after all operations are done.
            unregister_active_download(self.__c_track.song_path)

        return self.__c_track

    def download_eps(self) -> Episode:
        # Use the customizable retry parameters
        retry_delay = getattr(self.__preferences, 'initial_retry_delay', 30)  # Default to 30 seconds
        retry_delay_increase = getattr(self.__preferences, 'retry_delay_increase', 30)  # Default to 30 seconds
        max_retries = getattr(self.__preferences, 'max_retries', 5)  # Default to 5 retries
        
        retries = 0
        # Initialize success to False for the episode, to be set True on completion
        if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
            self.__c_episode.success = False

        if isfile(self.__song_path) and check_track(self.__c_episode):
            ans = input(
                f"Episode \"{self.__song_path}\" already exists, do you want to redownload it?(y or n):"
            )
            if not ans in answers:
                 # If user chooses not to redownload, and file exists, consider it 'successful' for cleanup purposes if needed.
                 # However, the main .success might be for actual download processing.
                 # For now, just return. The file isn't in ACTIVE_DOWNLOADS from *this* run.
                return self.__c_episode
        episode_id = EpisodeId.from_base62(self.__ids)
        while True:
            try:
                stream = Download_JOB.session.content_feeder().load_episode(
                    episode_id,
                    AudioQuality(self.__dw_quality),
                    False,
                    None
                )
                # If load_episode is successful, break from retry loop
                break
            except Exception as e:
                global GLOBAL_RETRY_COUNT
                GLOBAL_RETRY_COUNT += 1
                retries += 1
                # Log retry attempt with structured data
                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    report_type="episode",
                    status="retrying",
                    retry_count=retries,
                    seconds_left=retry_delay,
                    song=self.__song_metadata.get('music', 'Unknown Episode'),
                    artist=self.__song_metadata.get('artist', 'Unknown Show'),
                    error=str(e),
                    url=self.__link,
                    convert_to=self.__convert_to,
                    bitrate=self.__bitrate
                )
                if retries >= max_retries or GLOBAL_RETRY_COUNT >= GLOBAL_MAX_RETRIES:
                    if os.path.exists(self.__song_path):
                        os.remove(self.__song_path) # Clean up partial file
                    track_name = self.__song_metadata.get('music', 'Unknown Episode')
                    artist_name = self.__song_metadata.get('artist', 'Unknown Show')
                    final_error_msg = f"Maximum retry limit reached for '{track_name}' by '{artist_name}' (local: {max_retries}, global: {GLOBAL_MAX_RETRIES}). Last error: {str(e)}"
                    if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                        self.__c_episode.success = False
                        self.__c_episode.error_message = final_error_msg
                    raise Exception(final_error_msg) from e
                time.sleep(retry_delay)
                retry_delay += retry_delay_increase
        
        total_size = stream.input_stream.size
        os.makedirs(dirname(self.__song_path), exist_ok=True)
        
        register_active_download(self.__song_path) # Register before writing
        
        try:
            with open(self.__song_path, "wb") as f:
                c_stream = stream.input_stream.stream()
                if self.__real_time_dl and self.__song_metadata.get("duration") and self.__song_metadata["duration"] > 0:
                    # Restored Real-time download logic for episodes
                    duration = self.__song_metadata["duration"]
                    rate_limit = total_size / duration
                    chunk_size = 4096
                    bytes_written = 0
                    start_time = time.time()
                    try:
                        while True:
                            chunk = c_stream.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            bytes_written += len(chunk)
                            # Optional: Real-time progress reporting for episodes (can be added here if desired)
                            # Matching the style of download_try, no specific progress report inside this loop for episodes by default.
                            expected_time = bytes_written / rate_limit
                            elapsed_time = time.time() - start_time
                            if expected_time > elapsed_time:
                                time.sleep(expected_time - elapsed_time)
                    except Exception as e_realtime:
                        # If any error occurs during real-time download, clean up
                        if not c_stream.closed:
                            try: 
                                c_stream.close()
                            except: 
                                pass
                        # f.close() is handled by with statement, but an explicit one might be here if not using with.
                        if os.path.exists(self.__song_path):
                            try: 
                                os.remove(self.__song_path) 
                            except: 
                                pass
                        unregister_active_download(self.__song_path)
                        episode_title = self.__song_metadata.get('music', 'Unknown Episode')
                        artist_name = self.__song_metadata.get('artist', 'Unknown Show')
                        final_error_msg = f"Error during real-time download for episode '{episode_title}' by '{artist_name}' (URL: {self.__link}). Error: {str(e_realtime)}"
                        logger.error(final_error_msg)
                        if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                            self.__c_episode.success = False
                            self.__c_episode.error_message = final_error_msg
                        raise TrackNotFound(message=final_error_msg, url=self.__link) from e_realtime
                else:
                    # Restored Non real-time download logic for episodes
                    try:
                        data = c_stream.read(total_size)
                        f.write(data)
                    except Exception as e_standard:
                         # If any error occurs during standard download, clean up
                        if not c_stream.closed:
                            try: 
                                c_stream.close()
                            except: 
                                pass
                        if os.path.exists(self.__song_path):
                            try: 
                                os.remove(self.__song_path) 
                            except: 
                                pass
                        unregister_active_download(self.__song_path)
                        episode_title = self.__song_metadata.get('music', 'Unknown Episode')
                        artist_name = self.__song_metadata.get('artist', 'Unknown Show')
                        final_error_msg = f"Error during standard download for episode '{episode_title}' by '{artist_name}' (URL: {self.__link}). Error: {str(e_standard)}"
                        logger.error(final_error_msg)
                        if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                            self.__c_episode.success = False
                            self.__c_episode.error_message = final_error_msg
                        raise TrackNotFound(message=final_error_msg, url=self.__link) from e_standard
                
                # If all went well with writing to file and reading stream:
                if not c_stream.closed: c_stream.close()

            # If with open completes without internal exceptions leading to TrackNotFound:
            unregister_active_download(self.__song_path) # Unregister after successful write of original file
        
        except TrackNotFound: # Re-raise if it was an internally handled download error
            raise
        except Exception as e_outer: # Catch other potential errors around file handling or unexpected issues
            # Cleanup for download part if an unexpected error occurs outside the inner try-excepts
            if 'c_stream' in locals() and hasattr(c_stream, 'closed') and not c_stream.closed:
                try: c_stream.close() 
                except: pass
            if os.path.exists(self.__song_path):
                try: os.remove(self.__song_path) 
                except: pass
            unregister_active_download(self.__song_path)
            episode_title = self.__song_metadata.get('music', 'Unknown Episode')
            error_message = f"Failed to download episode '{episode_title}' (URL: {self.__link}) during file operations. Error: {str(e_outer)}"
            logger.error(error_message)
            if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                self.__c_episode.success = False
                self.__c_episode.error_message = error_message
            raise TrackNotFound(message=error_message, url=self.__link) from e_outer
            
        # If download was successful, proceed to conversion and tagging
        try:
            self.__convert_audio() # This will update self.__c_episode.file_format and path if conversion occurs
                               # It also handles registration/unregistration of intermediate/final files during conversion.
        except Exception as conv_e:
            # Conversion failed. __convert_audio or underlying convert_audio should have cleaned up its own temps.
            # The original downloaded file (if __convert_audio started from it) might still exist or be the self.__song_path.
            # Or self.__song_path might be a partially converted file if convert_audio failed mid-way and didn't cleanup perfectly.
            episode_title = self.__song_metadata.get('music', 'Unknown Episode')
            error_message = f"Audio conversion for episode '{episode_title}' failed. Original error: {str(conv_e)}"
            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="episode",
                status="error",
                song=episode_title,
                artist=self.__song_metadata.get('artist', 'Unknown Show'),
                error=error_message,
                url=self.__link,
                convert_to=self.__convert_to,
                bitrate=self.__bitrate
            )
            # Attempt to remove self.__song_path, which is the latest known path for this episode
            if os.path.exists(self.__song_path):
                os.remove(self.__song_path)
                unregister_active_download(self.__song_path) # Unregister it as it failed/was removed
            
            logger.error(error_message)
            if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
                self.__c_episode.success = False
                self.__c_episode.error_message = error_message
            raise TrackNotFound(message=error_message, url=self.__link) from conv_e
                
        # If we reach here, download and any conversion were successful.
        if hasattr(self, '_EASY_DW__c_episode') and self.__c_episode:
            self.__c_episode.success = True 
            write_tags(self.__c_episode)
            # Unregister the final successful file path for episodes, as it's now complete.
            # self.__c_episode.episode_path would have been updated by __convert_audio__ if conversion occurred.
            unregister_active_download(self.__c_episode.episode_path)
            
        return self.__c_episode

def download_cli(preferences: Preferences) -> None:
    __link = preferences.link
    __output_dir = preferences.output_dir
    __not_interface = preferences.not_interface
    __quality_download = preferences.quality_download
    __recursive_download = preferences.recursive_download
    cmd = f"deez-dw.py -so spo -l \"{__link}\" "
    if __output_dir:
        cmd += f"-o {__output_dir} "
    if __not_interface:
        cmd += f"-g "
    if __quality_download:
        cmd += f"-q {__quality_download} "
    if __recursive_download:
        cmd += f"-rd "
    system(cmd)

class DW_TRACK:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:
        self.__preferences = preferences

    def dw(self) -> Track:
        track = EASY_DW(self.__preferences).easy_dw()
        # No error handling needed here - if track.success is False but was_skipped is True,
        # it's an intentional skip, not an error
        return track

class DW_ALBUM:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:
        self.__preferences = preferences
        self.__ids = self.__preferences.ids
        self.__make_zip = self.__preferences.make_zip
        self.__output_dir = self.__preferences.output_dir
        self.__song_metadata = self.__preferences.song_metadata
        self.__not_interface = self.__preferences.not_interface
        self.__song_metadata_items = self.__song_metadata.items()

    def dw(self) -> Album:
        # Helper function to find most frequent item in a list
        def most_frequent(items):
            if not items:
                return None
            # If items is a string with semicolons, split it
            if isinstance(items, str) and ";" in items:
                items = [item.strip() for item in items.split(";")]
            # If it's still a string, return it directly
            if isinstance(items, str):
                return items
            # Otherwise, find the most frequent item
            return max(set(items), key=items.count)
        
        # Report album initializing status
        album_name = self.__song_metadata.get('album', 'Unknown Album')
        
        # Process album artist to get the most representative one
        album_artist = self.__song_metadata.get('artist', 'Unknown Artist')
        if isinstance(album_artist, list):
            album_artist = most_frequent(album_artist)
        elif isinstance(album_artist, str) and ";" in album_artist:
            artists_list = [artist.strip() for artist in album_artist.split(";")]
            album_artist = most_frequent(artists_list) if artists_list else album_artist
        
        total_tracks = self.__song_metadata.get('nb_tracks', 0)
        album_id = self.__ids
        
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="album",
            artist=album_artist,
            status="initializing",
            total_tracks=total_tracks,
            title=album_name,
            url=f"https://open.spotify.com/album/{album_id}",
        )
        
        pic_url = self.__song_metadata['image'] # This is URL for spotify
        image_bytes = request(pic_url).content
        self.__song_metadata['image'] = image_bytes # Keep bytes for tagging
        
        album = Album(self.__ids)
        album.image = image_bytes # Store raw image bytes for cover saving
        album.nb_tracks = self.__song_metadata['nb_tracks']
        album.album_name = self.__song_metadata['album']
        album.upc = self.__song_metadata['upc']
        tracks = album.tracks
        album.md5_image = self.__ids
        album.tags = self.__song_metadata
        
        # Determine album base directory once
        album_base_directory = get_album_directory(
            self.__song_metadata, # Album level metadata
            self.__output_dir,
            custom_dir_format=self.__preferences.custom_dir_format,
            pad_tracks=self.__preferences.pad_tracks
        )
        
        c_song_metadata = {}
        for key, item in self.__song_metadata_items:
            if key == 'popularity_list':
                continue
            if not isinstance(item, list): # Changed from type() to isinstance()
                c_song_metadata[key] = item # Use item directly (it's self.__song_metadata[key])
        total_tracks = album.nb_tracks
        for a in range(total_tracks):
            for key, metadata_value_for_key in self.__song_metadata_items: # metadata_value_for_key is self.__song_metadata[key]
                if isinstance(metadata_value_for_key, list): # Changed from type() is list to isinstance()
                    if key == 'popularity_list':
                        continue
                    if a < len(metadata_value_for_key):
                        c_song_metadata[key] = metadata_value_for_key[a]
                    else:
                        # Log a warning because a per-track list is shorter than expected.
                        # This was causing the IndexError.
                        album_name_for_log = c_song_metadata.get('album', self.__song_metadata.get('album', 'Unknown Album'))
                        logger.warning(
                            f"In album '{album_name_for_log}', metadata list for key '{key}' is too short. "
                            f"Expected at least {a + 1} elements for track {a + 1} "
                            f"(list has {len(metadata_value_for_key)}). Assigning None to '{key}' for this track."
                        )
                        c_song_metadata[key] = None
            song_name = c_song_metadata['music']
            artist_name = c_song_metadata['artist']
            album_name = c_song_metadata['album']
            current_track = a + 1
            
            c_preferences = deepcopy(self.__preferences)
            c_preferences.song_metadata = c_song_metadata.copy()
            c_preferences.ids = c_song_metadata['ids']
            c_preferences.track_number = current_track  # Track number in the album
            c_preferences.link = f"https://open.spotify.com/track/{c_preferences.ids}"
            
            # Add album_id to song metadata for consistent parent info
            c_preferences.song_metadata['album_id'] = self.__ids
            
            try:
                # Use track-level reporting through EASY_DW
                track = EASY_DW(c_preferences, parent='album').download_try()
            except TrackNotFound as e_track:
                track = Track(c_song_metadata, None, None, None, None, None)
                track.success = False
                track.error_message = str(e_track) # Store the error message from TrackNotFound
                logger.warning(f"Track '{song_name}' by '{artist_name}' from album '{album.album_name}' not found or failed to download. Reason: {track.error_message}")
            except Exception as e_generic:
                track = Track(c_song_metadata, None, None, None, None, None)
                track.success = False
                track.error_message = f"An unexpected error occurred: {str(e_generic)}"
                logger.error(f"Unexpected error downloading track '{song_name}' by '{artist_name}' from album '{album.album_name}'. Reason: {track.error_message}")
            tracks.append(track)

        # Save album cover image
        if self.__preferences.save_cover and album.image and album_base_directory:
            save_cover_image(album.image, album_base_directory, "cover.jpg")

        if self.__make_zip:
            song_quality = tracks[0].quality
            custom_dir_format = getattr(self.__preferences, 'custom_dir_format', None)
            zip_name = create_zip(
                tracks,
                output_dir=self.__output_dir,
                song_metadata=self.__song_metadata,
                song_quality=song_quality,
                custom_dir_format=custom_dir_format
            )
            album.zip_path = zip_name
            
        # Report album done status
        album_name = self.__song_metadata.get('album', 'Unknown Album')
        
        # Process album artist for the done status (use the same logic as initializing)
        album_artist = self.__song_metadata.get('artist', 'Unknown Artist')
        if isinstance(album_artist, list):
            album_artist = most_frequent(album_artist)
        elif isinstance(album_artist, str) and ";" in album_artist:
            artists_list = [artist.strip() for artist in album_artist.split(";")]
            album_artist = most_frequent(artists_list) if artists_list else album_artist
        
        total_tracks = self.__song_metadata.get('nb_tracks', 0)
        album_id = self.__ids
        
        successful_tracks = []
        failed_tracks = []
        skipped_tracks = []
        for track in tracks:
            track_info = {
                "name": track.tags.get('music', 'Unknown Track'),
                "artist": track.tags.get('artist', 'Unknown Artist')
            }
            if getattr(track, 'was_skipped', False):
                skipped_tracks.append(track_info)
            elif track.success:
                successful_tracks.append(track_info)
            else:
                track_info["reason"] = getattr(track, 'error_message', 'Unknown reason')
                failed_tracks.append(track_info)

        summary = {
            "successful_tracks": [f"{t['name']} - {t['artist']}" for t in successful_tracks],
            "skipped_tracks": [f"{t['name']} - {t['artist']}" for t in skipped_tracks],
            "failed_tracks": [{
                "track": f"{t['name']} - {t['artist']}",
                "reason": t['reason']
            } for t in failed_tracks],
            "total_successful": len(successful_tracks),
            "total_skipped": len(skipped_tracks),
            "total_failed": len(failed_tracks)
        }
        
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="album",
            artist=album_artist,
            status="done",
            total_tracks=total_tracks,
            title=album_name,
            url=f"https://open.spotify.com/album/{album_id}",
            summary=summary,
        )
        
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

    def dw(self) -> Playlist:
        playlist_name = self.__json_data.get('name', 'unknown')
        total_tracks = self.__json_data.get('tracks', {}).get('total', 'unknown')
        playlist_owner = self.__json_data.get('owner', {}).get('display_name', 'Unknown Owner')
        playlist_id = self.__ids

        # Report playlist initializing status
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="playlist",
            owner=playlist_owner,
            status="initializing",
            total_tracks=total_tracks,
            name=playlist_name,
            url=f"https://open.spotify.com/playlist/{playlist_id}",
        )
        
        # --- Prepare the m3u playlist file ---
        playlist_m3u_dir = os.path.join(self.__output_dir, "playlists")
        os.makedirs(playlist_m3u_dir, exist_ok=True)
        playlist_name_sanitized = sanitize_name(playlist_name)
        m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u")
        if not os.path.exists(m3u_path):
            with open(m3u_path, "w", encoding="utf-8") as m3u_file:
                m3u_file.write("#EXTM3U\n")
        # -------------------------------------

        playlist = Playlist()
        tracks = playlist.tracks
        for idx, c_song_metadata in enumerate(self.__song_metadata):
            # Check if c_song_metadata indicates a pre-identified error from metadata fetching stage
            if isinstance(c_song_metadata, dict) and 'error_type' in c_song_metadata:
                track_name = c_song_metadata.get('name', 'Unknown Track')
                track_ids = c_song_metadata.get('ids', None)
                error_message = c_song_metadata.get('error_message', 'Unknown error during metadata retrieval.')
                error_type = c_song_metadata.get('error_type', 'UnknownError')
                
                logger.warning(f"Skipping download for track '{track_name}' (ID: {track_ids}) from playlist '{playlist_name}' due to {error_type}: {error_message}")
                
                # Create a placeholder Track object to represent this failure
                # The link might not be available or relevant if IDs itself was the issue
                failed_track_link = f"https://open.spotify.com/track/{track_ids}" if track_ids else None
                
                # Basic metadata for the Track object constructor
                # We use c_song_metadata itself as it contains name, ids, etc.
                # Ensure it's a dict for Track constructor
                track_obj_metadata = c_song_metadata if isinstance(c_song_metadata, dict) else {'name': track_name, 'ids': track_ids}

                track = Track(
                    tags=track_obj_metadata,
                    song_path=None,
                    file_format=None,
                    quality=None,
                    link=failed_track_link,
                    ids=track_ids
                )
                track.success = False
                track.error_message = error_message
                tracks.append(track)
                continue # Move to the next track in the playlist

            # Original handling for string type (though this should be less common with new error dicts)
            if type(c_song_metadata) is str:
                logger.warning(f"Encountered string as song metadata for a track in playlist '{playlist_name}': {c_song_metadata}. Treating as error.")
                # Attempt to create a basic Track object with this string as an error message.
                # This is a fallback for older error reporting styles.
                error_track_name = "Unknown Track (error)"
                error_track_ids = None
                # Try to parse some info if the string is very specific, otherwise use generic.
                if "Track not found" in c_song_metadata:
                    # This was an old message format, may not contain structured info.
                    pass # Keep generic error_track_name for now.
                
                track = Track(
                    tags={'name': error_track_name, 'ids': error_track_ids, 'artist': 'Unknown Artist'}, # Minimal metadata
                    song_path=None,
                    file_format=None,
                    quality=None,
                    link=None, # No reliable link from just an error string
                    ids=error_track_ids
                )
                track.success = False
                track.error_message = c_song_metadata # The string itself is the error
                tracks.append(track)
                continue
            
            # If c_song_metadata is a valid metadata dictionary (no 'error_type')
            c_preferences = deepcopy(self.__preferences)
            c_preferences.ids = c_song_metadata.get('ids') # Use .get for safety, though it should exist
            c_preferences.song_metadata = c_song_metadata
            c_preferences.json_data = self.__json_data  # Pass playlist data for reporting
            c_preferences.track_number = idx + 1  # Track number in the playlist
            c_preferences.link = f"https://open.spotify.com/track/{c_preferences.ids}" if c_preferences.ids else None

            easy_dw_instance = EASY_DW(c_preferences, parent='playlist')
            track = None # Initialize track for this iteration

            try:
                track = easy_dw_instance.easy_dw()
            except TrackNotFound as e_track_nf:
                track = easy_dw_instance.get_no_dw_track() # Retrieve the track instance from EASY_DW
                # Ensure track object is a valid Track instance and has error info
                if not isinstance(track, Track): # Fallback if get_no_dw_track didn't return a Track
                    track = Track(c_song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                track.success = False # Explicitly set success to False
                # Ensure error message is set, preferring the one from the exception if track doesn't have one
                if not getattr(track, 'error_message', None) or str(e_track_nf): # Prioritize exception message if available
                    track.error_message = str(e_track_nf)

                song_name_log = c_song_metadata.get('music', 'Unknown Song')
                artist_name_log = c_song_metadata.get('artist', 'Unknown Artist')
                playlist_name_log = self.__json_data.get('name', 'Unknown Playlist')
                logger.warning(
                    f"Failed to download track '{song_name_log}' by '{artist_name_log}' from playlist '{playlist_name_log}'. "
                    f"Reason: {track.error_message} (URL: {track.link or c_preferences.link})"
                )
            except Exception as e_generic:
                # Catch any other unexpected exceptions during the track download process
                track = Track(c_song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                track.success = False
                track.error_message = f"An unexpected error occurred while processing track: {str(e_generic)}"

                song_name_log = c_song_metadata.get('music', 'Unknown Song')
                artist_name_log = c_song_metadata.get('artist', 'Unknown Artist')
                playlist_name_log = self.__json_data.get('name', 'Unknown Playlist')
                logger.error(
                    f"Unexpected error downloading track '{song_name_log}' by '{artist_name_log}' from playlist '{playlist_name_log}'. "
                    f"Reason: {track.error_message} (URL: {track.link or c_preferences.link})"
                )
            
            # Ensure track is not None before appending (should be assigned in try/except)
            if track is None:
                # This is a fallback, should ideally not be reached.
                track = Track(c_song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                track.success = False
                track.error_message = "Track processing resulted in an unhandled null track object."
                logger.error(f"Track '{c_song_metadata.get('music', 'Unknown Track')}' from playlist '{self.__json_data.get('name', 'Unknown Playlist')}' "
                             f"was not properly processed.")

            tracks.append(track)

            # --- Append the final track path to the m3u file using a relative path ---
            if track.success and hasattr(track, 'song_path') and track.song_path:
                # Build the relative path from the playlists directory
                relative_path = os.path.relpath(
                    track.song_path,
                    start=os.path.join(self.__output_dir, "playlists")
                )
                with open(m3u_path, "a", encoding="utf-8") as m3u_file:
                    m3u_file.write(f"{relative_path}\n")
            # ---------------------------------------------------------------------
        
        if self.__make_zip:
            playlist_title = self.__json_data['name']
            zip_name = f"{self.__output_dir}/{playlist_title} [playlist {self.__ids}]"
            create_zip(tracks, zip_name=zip_name)
            playlist.zip_path = zip_name
            
        # Report playlist done status
        playlist_name = self.__json_data.get('name', 'Unknown Playlist')
        playlist_owner = self.__json_data.get('owner', {}).get('display_name', 'Unknown Owner')
        total_tracks = self.__json_data.get('tracks', {}).get('total', 0)
        playlist_id = self.__ids
        
        successful_tracks = []
        failed_tracks = []
        skipped_tracks = []
        for track in tracks:
            track_info = {
                "name": track.tags.get('music') or track.tags.get('name', 'Unknown Track'),
                "artist": track.tags.get('artist', 'Unknown Artist')
            }
            if getattr(track, 'was_skipped', False):
                skipped_tracks.append(track_info)
            elif track.success:
                successful_tracks.append(track_info)
            else:
                track_info["reason"] = getattr(track, 'error_message', 'Unknown reason')
                failed_tracks.append(track_info)

        summary = {
            "successful_tracks": [f"{t['name']} - {t['artist']}" for t in successful_tracks],
            "skipped_tracks": [f"{t['name']} - {t['artist']}" for t in skipped_tracks],
            "failed_tracks": [{
                "track": f"{t['name']} - {t['artist']}",
                "reason": t['reason']
            } for t in failed_tracks],
            "total_successful": len(successful_tracks),
            "total_skipped": len(skipped_tracks),
            "total_failed": len(failed_tracks)
        }
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="playlist",
            owner=playlist_owner,
            status="done",
            total_tracks=total_tracks,
            name=playlist_name,
            url=f"https://open.spotify.com/playlist/{playlist_id}",
            summary=summary,
        )
        
        return playlist

class DW_EPISODE:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:
        self.__preferences = preferences

    def dw(self) -> Episode:
        episode_id = self.__preferences.ids
        url = f"https://open.spotify.com/episode/{episode_id}" if episode_id else None
        
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="episode",
            song=self.__preferences.song_metadata.get('name', 'Unknown Episode'),
            artist=self.__preferences.song_metadata.get('show', 'Unknown Show'),
            status="initializing",
            url=url,
        )
        
        episode = EASY_DW(self.__preferences).download_eps()
        
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="episode",
            song=self.__preferences.song_metadata.get('name', 'Unknown Episode'),
            artist=self.__preferences.song_metadata.get('show', 'Unknown Show'),
            status="done",
            url=url,
        )
        
        return episode
