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
from deezspot.__taggers__ import write_tags, check_track
from deezspot.deezloader.__download_utils__ import decryptfile, gen_song_hash
from deezspot.exceptions import (
    TrackNotFound,
    NoRightOnMedia,
    QualityNotFound,
)
from deezspot.models import (
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
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen import File
from deezspot.libutils.logging_utils import logger, ProgressReporter, report_progress
from deezspot.libutils.skip_detection import check_track_exists
from deezspot.libutils.cleanup_utils import register_active_download, unregister_active_download
from deezspot.libutils.audio_converter import AUDIO_FORMATS # Added for parse_format_string

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
            self.__song_metadata = preferences.song_metadata
            self.__download_type = "track"

        self.__c_quality = qualities[self.__quality_download]
        self.__fallback_ids = self.__ids

        self.__set_quality()
        self.__write_track()

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
        if self.__infos_dw.get('__TYPE__') == 'episode':
            pic = self.__infos_dw.get('EPISODE_IMAGE_MD5', '')
        else:
            pic = self.__infos_dw['ALB_PICTURE']
        image = API.choose_img(pic)
        self.__song_metadata['image'] = image
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
            # self.__c_track.song_quality might need re-evaluation if we could determine
            # quality of existing file. For now, assume it's acceptable.
            
            self.__c_track.success = True
            self.__c_track.was_skipped = True

            parent = None
            current_track = None
            total_tracks = None
            summary = None

            # Add parent info based on parent type
            if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
                playlist_data = self.__preferences.json_data
                playlist_name = playlist_data.get('title', 'unknown')
                total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                current_track = getattr(self.__preferences, 'track_number', 0)
                
                # Format for playlist-parented tracks exactly as required
                parent = {
                    "type": "playlist",
                    "name": playlist_name,
                    "owner": playlist_data.get('creator', {}).get('name', 'unknown'),
                    "total_tracks": total_tracks,
                    "url": f"https://deezer.com/playlist/{self.__preferences.json_data.get('id', '')}"
                }
            elif self.__parent == "album":
                album_name = self.__song_metadata.get('album', '')
                album_artist = self.__song_metadata.get('album_artist', self.__song_metadata.get('album_artist', ''))
                total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                current_track = getattr(self.__preferences, 'track_number', 0)
                
                # Format for album-parented tracks exactly as required
                parent = {
                    "type": "album",
                    "title": album_name,
                    "artist": album_artist,
                    "total_tracks": total_tracks,
                    "url": f"https://deezer.com/album/{self.__preferences.song_metadata.get('album_id', '')}"
                }
        
            if self.__parent is None:
                track_info = {
                    "name": current_title,
                    "artist": current_artist
                }
                summary = {
                    "successful_tracks": [],
                    "skipped_tracks": [f"{track_info['name']} - {track_info['artist']}"],
                    "failed_tracks": [],
                    "total_successful": 0,
                    "total_skipped": 1,
                    "total_failed": 0,
                }

            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="track",
                song=current_title,
                artist=self.__song_metadata['artist'],
                status="skipped",
                url=self.__link,
                reason=f"Track already exists in desired format at {existing_file_path}",
                convert_to=self.__convert_to,
                bitrate=self.__bitrate,
                parent=parent,
                current_track=current_track,
                total_tracks=total_tracks,
                summary=summary
            )
            # self.__c_track might not be fully initialized here if __write_track() hasn't been called
            # Create a minimal track object for skipped scenario
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
                # download_episode_try should set self.__c_episode.success = True if successful
                self.download_episode_try() # This will modify self.__c_episode directly
            else:
                # download_try should set self.__c_track.success = True if successful
                self.download_try() # This will modify self.__c_track directly
                
                # Create done status report using the new required format (only if download_try didn't fail)
                # This part should only execute if download_try itself was successful (i.e., no exception)
                if self.__c_track.success : # Check if download_try marked it as successful
                    parent = None
                    current_track = None
                    total_tracks = None

                    spotify_url = getattr(self.__preferences, 'spotify_url', None)
                    url = spotify_url if spotify_url else self.__link

                    if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
                        playlist_data = self.__preferences.json_data
                        total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                        current_track = getattr(self.__preferences, 'track_number', 0)
                        parent = {
                            "type": "playlist",
                            "name": playlist_data.get('title', 'unknown'),
                            "owner": playlist_data.get('creator', {}).get('name', 'unknown'),
                            "total_tracks": total_tracks,
                            "url": f"https://deezer.com/playlist/{playlist_data.get('id', '')}"
                        }
                    elif self.__parent == "album":
                        album_name = self.__song_metadata.get('album', '')
                        album_artist = self.__song_metadata.get('album_artist', self.__song_metadata.get('album_artist', ''))
                        total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                        current_track = getattr(self.__preferences, 'track_number', 0)
                        parent = {
                            "type": "album",
                            "title": album_name,
                            "artist": album_artist,
                            "total_tracks": total_tracks,
                            "url": f"https://deezer.com/album/{self.__preferences.song_metadata.get('album_id', '')}"
                        }

                    report_progress(
                        reporter=Download_JOB.progress_reporter,
                        report_type="track",
                        song=self.__song_metadata['music'],
                        artist=self.__song_metadata['artist'],
                        status="done",
                        url=url,
                        parent=parent,
                        current_track=current_track,
                        total_tracks=total_tracks,
                        convert_to=self.__convert_to
                    )

        except Exception as e: # Covers failures within download_try or download_episode_try
            item_type = "Episode" if self.__infos_dw.get('__TYPE__') == 'episode' else "Track"
            item_name = self.__song_metadata.get('music', f'Unknown {item_type}')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            error_message = f"Download process failed for {item_type.lower()} '{item_name}' by '{artist_name}' (URL: {self.__link}). Error: {str(e)}"
            logger.error(error_message)
            
            current_item_obj = self.__c_episode if self.__infos_dw.get('__TYPE__') == 'episode' else self.__c_track
            if current_item_obj:
                current_item_obj.success = False
                current_item_obj.error_message = error_message
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
            write_tags(current_item)
        
        return current_item

    def download_try(self) -> Track:
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
            
            # Get track IDs and encryption information
            # The enhanced check_track_ids function will determine the encryption type
            self.__fallback_ids = check_track_ids(self.__infos_dw)
            encryption_type = self.__fallback_ids.get('encryption_type', 'unknown')
            logger.debug(f"Using encryption type: {encryption_type}")

            try:
                self.__write_track()
                
                # Send immediate progress status for the track
                parent = None
                current_track = None
                total_tracks = None
                spotify_url = getattr(self.__preferences, 'spotify_url', None)
                url = spotify_url if spotify_url else self.__link
                
                if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
                    playlist_data = self.__preferences.json_data
                    playlist_name = playlist_data.get('title', 'unknown')
                    total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    parent = {
                        "type": "playlist",
                        "name": playlist_name,
                        "owner": playlist_data.get('creator', {}).get('name', 'unknown'),
                        "total_tracks": total_tracks,
                        "url": f"https://deezer.com/playlist/{self.__preferences.json_data.get('id', '')}"
                    }
                elif self.__parent == "album":
                    album_name = self.__song_metadata.get('album', '')
                    album_artist = self.__song_metadata.get('album_artist', self.__song_metadata.get('album_artist', ''))
                    total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    parent = {
                        "type": "album",
                        "title": album_name,
                        "artist": album_artist,
                        "total_tracks": total_tracks,
                        "url": f"https://deezer.com/album/{self.__preferences.song_metadata.get('album_id', '')}"
                    }

                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    report_type="track",
                    song=self.__song_metadata.get("music", ""),
                    artist=self.__song_metadata.get("artist", ""),
                    status="initializing",
                    url=url,
                    parent=parent,
                    current_track=current_track,
                    total_tracks=total_tracks,
                )
                
                # Start of processing block (decryption, tagging, cover, conversion)
                register_active_download(self.__song_path)
                try:
                    # Decrypt the file using the utility function
                    decryptfile(c_crypted_audio, self.__fallback_ids, self.__song_path)
                    logger.debug(f"Successfully decrypted track using {encryption_type} encryption")
                    # self.__song_path is still registered
                except Exception as e_decrypt:
                    unregister_active_download(self.__song_path)
                    if isfile(self.__song_path):
                        try:
                            os.remove(self.__song_path)
                        except OSError: # Handle potential errors during removal
                            logger.warning(f"Could not remove partially downloaded file: {self.__song_path}")
                    self.__c_track.success = False
                    self.__c_track.error_message = f"Decryption failed: {str(e_decrypt)}"
                    raise TrackNotFound(f"Failed to process {self.__song_path}. Error: {str(e_decrypt)}") from e_decrypt

                self.__add_more_tags() # self.__song_metadata is updated here
                self.__c_track.tags = self.__song_metadata # IMPORTANT: Update track object's tags

                # Save cover image if requested
                if self.__preferences.save_cover and self.__song_metadata.get('image'):
                    try:
                        track_directory = os.path.dirname(self.__song_path)
                        save_cover_image(self.__song_metadata['image'], track_directory, "cover.jpg")
                        logger.info(f"Saved cover image for track in {track_directory}")
                    except Exception as e_img_save:
                        logger.warning(f"Failed to save cover image for track: {e_img_save}")

                # Apply audio conversion if requested
                if self.__convert_to:
                    format_name, bitrate = self._parse_format_string(self.__convert_to)
                    if format_name:
                        # Current self.__song_path (original decrypted file) is registered.
                        # convert_audio will handle unregistering it if it creates a new file,
                        # and will register the new file.
                        path_before_conversion = self.__song_path
                        try:
                            converted_path = convert_audio(
                                path_before_conversion, 
                                format_name, 
                                bitrate if bitrate else self.__bitrate, # Prefer specific bitrate from string, fallback to general
                                register_active_download,
                                unregister_active_download
                            )
                            if converted_path != path_before_conversion:
                                # convert_audio has unregistered path_before_conversion (if it existed and was different)
                                # and registered converted_path.
                                self.__song_path = converted_path
                                self.__c_track.song_path = converted_path
                                _, new_ext = os.path.splitext(converted_path)
                                self.__file_format = new_ext.lower() # Update internal state
                                self.__c_track.file_format = new_ext.lower()
                                # self.__song_path (the converted_path) is now the registered active download
                            # If converted_path == path_before_conversion, no actual file change, registration status managed by convert_audio
                        except Exception as conv_error:
                            logger.error(f"Audio conversion error: {str(conv_error)}. Proceeding with original format.")
                            # path_before_conversion should still be registered if convert_audio failed early
                            # or did not successfully unregister it.
                            # If conversion fails, the original file (path_before_conversion) remains the target.
                            # Its registration state should be preserved if convert_audio didn't affect it.
                            # For safety, ensure it is considered the active download if conversion fails:
                            register_active_download(path_before_conversion)


                # Write tags to the final file (original or converted)
                write_tags(self.__c_track)
                self.__c_track.success = True # Mark as successful only after all steps including tags
                unregister_active_download(self.__song_path) # Unregister the final successful file

            except Exception as e: # Handles errors from __write_track, decrypt, add_tags, save_cover, convert, write_tags
                # Ensure unregister is called for self.__song_path if it was registered and an error occurred
                # The specific error might have already unregistered it (e.g. decrypt error)
                # Call it defensively.
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
                
                # (Error reporting code as it exists)
                parent = None
                current_track = None
                total_tracks = None

                if self.__parent == "playlist" and hasattr(self.__preferences, "json_data"):
                    playlist_data = self.__preferences.json_data
                    playlist_name = playlist_data.get('title', 'unknown')
                    total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    parent = {
                        "type": "playlist", "name": playlist_name, 
                        "owner": playlist_data.get('creator', {}).get('name', 'unknown'), 
                        "total_tracks": total_tracks, 
                        "url": f"https://deezer.com/playlist/{playlist_data.get('id', '')}"
                    }
                elif self.__parent == "album":
                    album_name = self.__song_metadata.get('album', '')
                    album_artist = self.__song_metadata.get('album_artist', self.__song_metadata.get('album_artist', ''))
                    total_tracks = getattr(self.__preferences, 'total_tracks', 0)
                    current_track = getattr(self.__preferences, 'track_number', 0)
                    parent = {
                        "type": "album", "title": album_name, 
                        "artist": album_artist, 
                        "total_tracks": total_tracks, 
                        "url": f"https://deezer.com/album/{self.__preferences.song_metadata.get('album_id', '')}"
                    }

                report_progress(
                    reporter=Download_JOB.progress_reporter,
                    report_type="track",
                    status="error",
                    song=self.__song_metadata.get('music', ''),
                    artist=self.__song_metadata.get('artist', ''),
                    error=error_msg,
                    url=getattr(self.__preferences, 'spotify_url', None) or self.__link,
                    convert_to=self.__convert_to,
                    parent=parent,
                    current_track=current_track,
                    total_tracks=total_tracks
                )
                logger.error(f"Failed to process track: {error_msg}")
                
                self.__c_track.success = False
                self.__c_track.error_message = error_msg
                raise TrackNotFound(f"Failed to process {self.__song_path}. Error: {error_msg}. Original Exception: {str(e)}")

            return self.__c_track

        except Exception as e: # Outer exception for initial media checks, etc.
            song_title = self.__song_metadata.get('music', 'Unknown Song')
            artist_name = self.__song_metadata.get('artist', 'Unknown Artist')
            error_message = f"Download failed for '{song_title}' by '{artist_name}' (Link: {self.__link}). Error: {str(e)}"
            logger.error(error_message)
            # Store error on track object if possible
            # Ensure self.__song_path is unregistered if an error occurs before successful completion.
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
                write_tags(self.__c_track)
            
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

    def __add_more_tags(self) -> None:
        contributors = self.__infos_dw.get('SNG_CONTRIBUTORS', {})

        if "author" in contributors:
            self.__song_metadata['author'] = "; ".join(
                contributors['author']
            )
        else:
            self.__song_metadata['author'] = ""

        if "composer" in contributors:
            self.__song_metadata['composer'] = "; ".join(
                contributors['composer']
            )
        else:
            self.__song_metadata['composer'] = ""

        if "lyricist" in contributors:
            self.__song_metadata['lyricist'] = "; ".join(
                contributors['lyricist']
            )
        else:
            self.__song_metadata['lyricist'] = ""

        if "composerlyricist" in contributors:
            self.__song_metadata['composer'] = "; ".join(
                contributors['composerlyricist']
            )
        else:
            self.__song_metadata['composerlyricist'] = ""

        if "version" in self.__infos_dw:
            self.__song_metadata['version'] = self.__infos_dw['VERSION']
        else:
            self.__song_metadata['version'] = ""

        self.__song_metadata['lyric'] = ""
        self.__song_metadata['copyright'] = ""
        self.__song_metadata['lyricist'] = ""
        self.__song_metadata['lyric_sync'] = []

        if self.__infos_dw.get('LYRICS_ID', 0) != 0:
            need = API_GW.get_lyric(self.__ids)

            if "LYRICS_TEXT" in need:
                self.__song_metadata['lyric'] = need["LYRICS_TEXT"]

            if "LYRICS_SYNC_JSON" in need:
                self.__song_metadata['lyric_sync'] = trasform_sync_lyric(
                    need['LYRICS_SYNC_JSON']
                )

        # This method should only add tags. Error handling for download success/failure
        # is managed by easy_dw after calls to download_try/download_episode_try.
        # No error re-raising or success flag modification here.
        # write_tags is called after this in download_try if successful.

class DW_TRACK:
    def __init__(
        self,
        preferences: Preferences
    ) -> None:

        self.__preferences = preferences
        self.__ids = self.__preferences.ids
        self.__song_metadata = self.__preferences.song_metadata
        self.__quality_download = self.__preferences.quality_download

    def dw(self) -> Track:
        infos_dw = API_GW.get_song_data(self.__ids)

        media = Download_JOB.check_sources(
            [infos_dw], self.__quality_download
        )

        infos_dw['media_url'] = media[0]

        # For individual tracks, parent is None (not part of album or playlist)
        track = EASY_DW(infos_dw, self.__preferences, parent=None).easy_dw()

        # Check if track failed but was NOT intentionally skipped
        if not track.success and not getattr(track, 'was_skipped', False):
            song = f"{self.__song_metadata['music']} - {self.__song_metadata['artist']}"
            # Attempt to get the original error message if available from the track object
            original_error = getattr(track, 'error_message', "it's not available in this format or an error occurred.")
            error_msg = f"Cannot download '{song}'. Reason: {original_error}"
            current_link = track.link if hasattr(track, 'link') and track.link else self.__preferences.link
            logger.error(f"{error_msg} (Link: {current_link})")
            raise TrackNotFound(message=error_msg, url=current_link)

        if track.success and not getattr(track, 'was_skipped', False):
            track_info = {
                "name": track.tags.get('music', 'Unknown Track'),
                "artist": track.tags.get('artist', 'Unknown Artist')
            }
            summary = {
                "successful_tracks": [f"{track_info['name']} - {track_info['artist']}"],
                "skipped_tracks": [],
                "failed_tracks": [],
                "total_successful": 1,
                "total_skipped": 0,
                "total_failed": 0,
            }
            report_progress(
                reporter=Download_JOB.progress_reporter,
                report_type="track",
                song=track_info['name'],
                artist=track_info['artist'],
                status="done",
                url=track.link,
                summary=summary
            )

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
        self.__not_interface = self.__preferences.not_interface
        self.__quality_download = self.__preferences.quality_download
        self.__recursive_quality = self.__preferences.recursive_quality
        self.__song_metadata = self.__preferences.song_metadata

        self.__song_metadata_items = self.__song_metadata.items()

    def dw(self) -> Album:
        # Helper function to find most frequent item in a list
        def most_frequent(items):
            if not items:
                return None
            return max(set(items), key=items.count)
        
        # Derive album_artist strictly from the album's API contributors
        album_api_contributors = self.__preferences.json_data.get('contributors', [])
        derived_album_artist_from_contributors = "Unknown Artist" # Default

        if album_api_contributors: # Check if contributors list is not empty
            main_contributor_names = [
                c.get('name') for c in album_api_contributors
                if c.get('name') and c.get('role', '').lower() == 'main'
            ]

            if main_contributor_names:
                derived_album_artist_from_contributors = "; ".join(main_contributor_names)
            else: # No 'Main' contributors, try all contributors with a name
                all_contributor_names = [
                    c.get('name') for c in album_api_contributors if c.get('name')
                ]
                if all_contributor_names:
                    derived_album_artist_from_contributors = "; ".join(all_contributor_names)
        # If album_api_contributors is empty or no names were found, it remains "Unknown Artist"


        # Report album initializing status
        album_name_for_report = self.__song_metadata.get('album', 'Unknown Album')
        total_tracks_for_report = self.__song_metadata.get('nb_tracks', 0)
        album_link_for_report = self.__preferences.link # Get album link from preferences
        
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="album",
            artist=derived_album_artist_from_contributors,
            status="initializing",
            total_tracks=total_tracks_for_report,
            title=album_name_for_report,
            url=album_link_for_report
        )
        
        infos_dw = API_GW.get_album_data(self.__ids)['data']

        md5_image = infos_dw[0]['ALB_PICTURE']
        image_bytes = API.choose_img(md5_image, size="1400x1400") # Fetch highest quality
        self.__song_metadata['image'] = image_bytes # Store for tagging if needed, already bytes

        album = Album(self.__ids)
        album.image = image_bytes # Store raw image bytes
        album.md5_image = md5_image
        album.nb_tracks = self.__song_metadata['nb_tracks']
        album.album_name = self.__song_metadata['album']
        album.upc = self.__song_metadata['upc']
        tracks = album.tracks
        album.tags = self.__song_metadata

        # Get media URLs using the splitting approach
        medias = Download_JOB.check_sources(
            infos_dw, self.__quality_download
        )
        
        # Determine album base directory once
        album_base_directory = get_album_directory(
            self.__song_metadata, # Album level metadata
            self.__output_dir,
            custom_dir_format=self.__preferences.custom_dir_format,
            pad_tracks=self.__preferences.pad_tracks
        )
        
        total_tracks = len(infos_dw)
        for a in range(total_tracks):
            track_number = a + 1
            # c_infos_dw is from API_GW.get_album_data, used for SNG_ID, SNG_TITLE etc.
            c_infos_dw_item = infos_dw[a] 
            
            # self.__song_metadata is the dict-of-lists from API.tracking_album
            # We need to construct c_song_metadata_for_easydw for the current track 'a'
            # by picking the ath element from each list in self.__song_metadata.
            
            current_track_constructed_metadata = {}
            potential_error_marker = None
            is_current_track_error = False

            # Check the 'music' field first for an error dict from API.tracking_album
            if 'music' in self.__song_metadata and isinstance(self.__song_metadata['music'], list) and len(self.__song_metadata['music']) > a:
                music_field_value = self.__song_metadata['music'][a]
                if isinstance(music_field_value, dict) and 'error_type' in music_field_value:
                    is_current_track_error = True
                    potential_error_marker = music_field_value
                    # The error marker dict itself will serve as the metadata for the failed track object
                    current_track_constructed_metadata = potential_error_marker
            
            if not is_current_track_error:
                # Populate current_track_constructed_metadata from self.__song_metadata lists
                for key, value_list_template in self.__song_metadata_items: # self.__song_metadata_items is items() of dict-of-lists
                    if isinstance(value_list_template, list): # e.g. self.__song_metadata['artist']
                        if len(self.__song_metadata[key]) > a:
                            current_track_constructed_metadata[key] = self.__song_metadata[key][a]
                        else:
                            current_track_constructed_metadata[key] = "Unknown" # Fallback if list is too short
                    else: # Album-wide metadata (e.g. 'album', 'label')
                        current_track_constructed_metadata[key] = self.__song_metadata[key]
                
                # Ensure essential fields from c_infos_dw_item are preferred or added if missing from API.tracking_album results
                current_track_constructed_metadata['music'] = current_track_constructed_metadata.get('music') or c_infos_dw_item.get('SNG_TITLE', 'Unknown')
                # artist might be complex due to contributors, rely on what API.tracking_album prepared
                # current_track_constructed_metadata['artist'] = current_track_constructed_metadata.get('artist') # Already populated or None
                current_track_constructed_metadata['tracknum'] = current_track_constructed_metadata.get('tracknum') or f"{track_number}"
                current_track_constructed_metadata['discnum'] = current_track_constructed_metadata.get('discnum') or f"{c_infos_dw_item.get('DISK_NUMBER', 1)}"
                current_track_constructed_metadata['isrc'] = current_track_constructed_metadata.get('isrc') or c_infos_dw_item.get('ISRC', '')
                current_track_constructed_metadata['duration'] = current_track_constructed_metadata.get('duration') or int(c_infos_dw_item.get('DURATION', 0))
                current_track_constructed_metadata['explicit'] = current_track_constructed_metadata.get('explicit') or ('1' if c_infos_dw_item.get('EXPLICIT_LYRICS', '0') == '1' else '0')
                current_track_constructed_metadata['album_artist'] = current_track_constructed_metadata.get('album_artist') or derived_album_artist_from_contributors

            if is_current_track_error:
                error_type = potential_error_marker.get('error_type', 'UnknownError')
                error_message = potential_error_marker.get('message', 'An unknown error occurred.')
                track_name_for_log = potential_error_marker.get('name', c_infos_dw_item.get('SNG_TITLE', f'Track {track_number}'))
                track_id_for_log = potential_error_marker.get('ids', c_infos_dw_item.get('SNG_ID'))
                
                # Construct market_info string based on actual checked_markets from error dict or preferences fallback
                checked_markets_str = ""
                if error_type == 'MarketAvailabilityError':
                    # Prefer checked_markets from the error dict if available
                    if 'checked_markets' in c_infos_dw_item and c_infos_dw_item['checked_markets']:
                        checked_markets_str = c_infos_dw_item['checked_markets']
                    # Fallback to preferences.market if not in error dict (though it should be)
                    elif self.__preferences.market:
                        if isinstance(self.__preferences.market, list):
                            checked_markets_str = ", ".join([m.upper() for m in self.__preferences.market])
                        elif isinstance(self.__preferences.market, str):
                            checked_markets_str = self.__preferences.market.upper()
                market_log_info = f" (Market(s): {checked_markets_str})" if checked_markets_str else ""

                logger.warning(f"Skipping download of track '{track_name_for_log}' (ID: {track_id_for_log}) in album '{album.album_name}' due to {error_type}{market_log_info}: {error_message}")
                
                failed_track_link = f"https://deezer.com/track/{track_id_for_log}" if track_id_for_log else self.__preferences.link # Fallback to album link
                
                # current_track_constructed_metadata is already the error_marker dict
                track = Track(
                    tags=current_track_constructed_metadata, 
                    song_path=None, file_format=None, quality=None, 
                    link=failed_track_link, 
                    ids=track_id_for_log
                )
                track.success = False
                track.error_message = error_message
                tracks.append(track)
                # Optionally, report progress for this failed track within the album context here
                continue # to the next track in the album

            # Merge album-level metadata (only add fields not already set in c_song_metadata)
            # This was the old logic, current_track_constructed_metadata should be fairly complete now or an error dict.
            # for key, item in self.__song_metadata_items:
            #     if key not in current_track_constructed_metadata:
            #         if isinstance(item, list):
            #             current_track_constructed_metadata[key] = self.__song_metadata[key][a] if len(self.__song_metadata[key]) > a else 'Unknown'
            #         else:
            #             current_track_constructed_metadata[key] = self.__song_metadata[key]
            
            # Continue with the rest of your processing (media handling, download, etc.)
            c_infos_dw_item['media_url'] = medias[a] # medias is from Download_JOB.check_sources(infos_dw, ...)
            c_preferences = deepcopy(self.__preferences)
            c_preferences.song_metadata = current_track_constructed_metadata.copy()
            c_preferences.ids = c_infos_dw_item['SNG_ID']
            c_preferences.track_number = track_number
            
            # Add additional information for consistent parent info
            c_preferences.song_metadata['album_id'] = self.__ids
            c_preferences.song_metadata['total_tracks'] = total_tracks
            c_preferences.total_tracks = total_tracks
            c_preferences.link = f"https://deezer.com/track/{c_preferences.ids}"
            
            current_track_object = None
            try:
                # This is where EASY_DW().easy_dw() or EASY_DW().download_try() is effectively called
                current_track_object = EASY_DW(c_infos_dw_item, c_preferences, parent='album').easy_dw()

            except TrackNotFound as e_tnf:
                logger.error(f"Track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' by '{c_preferences.song_metadata.get('artist', 'Unknown Artist')}' (Album: {album.album_name}) failed: {str(e_tnf)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_tnf)
            except QualityNotFound as e_qnf:
                logger.error(f"Quality issue for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Album: {album.album_name}): {str(e_qnf)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_qnf)
            except requests.exceptions.ConnectionError as e_conn:
                logger.error(f"Connection error for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Album: {album.album_name}): {str(e_conn)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_conn) # Store specific connection error
            except Exception as e_general: # Catch any other unexpected error during this track's processing
                logger.error(f"Unexpected error for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Album: {album.album_name}): {str(e_general)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_general)
            
            if current_track_object:
                tracks.append(current_track_object)
            else: # Should not happen if exceptions are caught, but as a fallback
                logger.error(f"Track object was not created for SNG_ID {c_infos_dw_item['SNG_ID']} in album {album.album_name}. Skipping.")
                # Create a generic failed track to ensure list length matches expectation if needed elsewhere
                failed_placeholder = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                failed_placeholder.success = False
                failed_placeholder.error_message = "Track processing failed to produce a result object."
                tracks.append(failed_placeholder)

        # Save album cover image
        if self.__preferences.save_cover and album.image and album_base_directory:
            save_cover_image(album.image, album_base_directory, "cover.jpg")

        if self.__make_zip:
            song_quality = tracks[0].quality if tracks else 'Unknown'
            # Pass along custom directory format if set
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
        total_tracks = self.__song_metadata.get('nb_tracks', 0)
        
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

        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="album",
            artist=derived_album_artist_from_contributors,
            status="done",
            total_tracks=total_tracks,
            title=album_name,
            url=album_link_for_report, # Use the actual album link
            summary={
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
        self.__quality_download = self.__preferences.quality_download

    def dw(self) -> Playlist:
        # Extract playlist metadata for reporting
        playlist_name = self.__json_data.get('title', 'Unknown Playlist')
        playlist_owner = self.__json_data.get('creator', {}).get('name', 'Unknown Owner')
        total_tracks = self.__json_data.get('nb_tracks', 0)
        
        # Report playlist initializing status
        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="playlist",
            owner=playlist_owner,
            status="initializing",
            total_tracks=total_tracks,
            name=playlist_name,
            url=f"https://deezer.com/playlist/{self.__ids}"
        )
        
        # Retrieve playlist data from API
        infos_dw = API_GW.get_playlist_data(self.__ids)['data']
        
        # Extract playlist metadata - we'll use this in the track-level reporting
        playlist_name_sanitized = sanitize_name(self.__json_data['title'])
        total_tracks = len(infos_dw)

        playlist = Playlist()
        tracks = playlist.tracks

        # --- Prepare the m3u playlist file ---
        # m3u file will be placed in output_dir/playlists
        playlist_m3u_dir = os.path.join(self.__output_dir, "playlists")
        os.makedirs(playlist_m3u_dir, exist_ok=True)
        m3u_path = os.path.join(playlist_m3u_dir, f"{playlist_name_sanitized}.m3u")
        if not os.path.exists(m3u_path):
            with open(m3u_path, "w", encoding="utf-8") as m3u_file:
                m3u_file.write("#EXTM3U\n")
        # -------------------------------------

        # Get media URLs for each track in the playlist
        medias = Download_JOB.check_sources(
            infos_dw, self.__quality_download
        )

        # Process each track
        for idx, (c_infos_dw_item, c_media, c_song_metadata_item) in enumerate(zip(infos_dw, medias, self.__song_metadata), 1):

            # Skip if song metadata indicates an error (e.g., from market availability or NoDataApi)
            if isinstance(c_song_metadata_item, dict) and 'error_type' in c_song_metadata_item:
                track_name = c_song_metadata_item.get('name', 'Unknown Track')
                track_ids = c_song_metadata_item.get('ids')
                error_message = c_song_metadata_item.get('message', 'Unknown error.')
                error_type = c_song_metadata_item.get('error_type', 'UnknownError')
                # market_info = f" (Market: {self.__preferences.market})" if self.__preferences.market and error_type == 'MarketAvailabilityError' else ""
                # Construct market_info string based on actual checked_markets from error dict or preferences fallback
                checked_markets_str = ""
                if error_type == 'MarketAvailabilityError':
                    # Prefer checked_markets from the error dict if available
                    if 'checked_markets' in c_song_metadata_item and c_song_metadata_item['checked_markets']:
                        checked_markets_str = c_song_metadata_item['checked_markets']
                    # Fallback to preferences.market if not in error dict (though it should be)
                    elif self.__preferences.market:
                        if isinstance(self.__preferences.market, list):
                            checked_markets_str = ", ".join([m.upper() for m in self.__preferences.market])
                        elif isinstance(self.__preferences.market, str):
                            checked_markets_str = self.__preferences.market.upper()
                market_log_info = f" (Market(s): {checked_markets_str})" if checked_markets_str else ""

                logger.warning(f"Skipping download for track '{track_name}' (ID: {track_ids}) from playlist '{playlist_name_sanitized}' due to {error_type}{market_log_info}: {error_message}")
                
                failed_track_link = f"https://deezer.com/track/{track_ids}" if track_ids else self.__preferences.link # Fallback to playlist link
                                
                # c_song_metadata_item is the error dict, use it as tags for the Track object
                track = Track(
                    tags=c_song_metadata_item, 
                    song_path=None, file_format=None, quality=None, 
                    link=failed_track_link, 
                    ids=track_ids
                )
                track.success = False
                track.error_message = error_message
                tracks.append(track)
                # Optionally, report progress for this failed track within the playlist context here
                continue # Move to the next track in the playlist

            # Original check for string type, should be less common if API returns dicts for errors
            if type(c_song_metadata_item) is str: 
                logger.warning(f"Track metadata is a string for a track in playlist '{playlist_name_sanitized}': '{c_song_metadata_item}'. Skipping.")
                # Create a basic failed track object if metadata is just a string error
                # This is a fallback, ideally c_song_metadata_item would be an error dict
                error_placeholder_tags = {'name': 'Unknown Track (metadata error)', 'artist': 'Unknown Artist', 'error_type': 'StringError', 'message': c_song_metadata_item}
                track = Track(
                    tags=error_placeholder_tags,
                    song_path=None, file_format=None, quality=None,
                    link=self.__preferences.link, # Playlist link
                    ids=None # No specific ID available from string error
                )
                track.success = False
                track.error_message = c_song_metadata_item
                tracks.append(track)
                continue

            c_infos_dw_item['media_url'] = c_media
            c_preferences = deepcopy(self.__preferences)
            c_preferences.ids = c_infos_dw_item['SNG_ID']
            c_preferences.song_metadata = c_song_metadata_item # This is the full metadata dict for a successful track
            c_preferences.track_number = idx
            c_preferences.total_tracks = total_tracks

            # Download the track using the EASY_DW downloader
            # Wrap this in a try-except block to handle individual track failures
            current_track_object = None
            try:
                current_track_object = EASY_DW(c_infos_dw_item, c_preferences, parent='playlist').easy_dw()
            except TrackNotFound as e_tnf:
                logger.error(f"Track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' by '{c_preferences.song_metadata.get('artist', 'Unknown Artist')}' (Playlist: {playlist_name_sanitized}) failed: {str(e_tnf)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_tnf)
            except QualityNotFound as e_qnf:
                logger.error(f"Quality issue for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Playlist: {playlist_name_sanitized}): {str(e_qnf)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_qnf)
            except requests.exceptions.ConnectionError as e_conn: # Catch connection errors specifically
                logger.error(f"Connection error for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Playlist: {playlist_name_sanitized}): {str(e_conn)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_conn) # Store specific connection error
            except Exception as e_general: # Catch any other unexpected error during this track's processing
                logger.error(f"Unexpected error for track '{c_preferences.song_metadata.get('music', 'Unknown Track')}' (Playlist: {playlist_name_sanitized}): {str(e_general)}")
                current_track_object = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                current_track_object.success = False
                current_track_object.error_message = str(e_general)

            # Track-level progress reporting is handled in EASY_DW
            if current_track_object: # Ensure a track object was created
                tracks.append(current_track_object)
                # Only log a warning if the track failed and was NOT intentionally skipped
                if not current_track_object.success and not getattr(current_track_object, 'was_skipped', False):
                    # The error logging is now done within the except blocks above, more specifically.
                    pass # logger.warning(f"Cannot download '{song}'. Reason: {error_detail} (Link: {track.link or c_preferences.link})")
            else:
                 # This case should ideally not be reached if exceptions are handled correctly.
                logger.error(f"Track object was not created for SNG_ID {c_infos_dw_item['SNG_ID']} in playlist {playlist_name_sanitized}. Skipping.")
                # Create a generic failed track to ensure list length matches expectation if needed elsewhere
                failed_placeholder = Track(c_preferences.song_metadata, None, None, None, c_preferences.link, c_preferences.ids)
                failed_placeholder.success = False
                failed_placeholder.error_message = "Track processing failed to produce a result object."
                tracks.append(failed_placeholder)

            # --- Append the final track path to the m3u file ---
            # Build a relative path from the playlists directory
            if current_track_object and current_track_object.success and hasattr(current_track_object, 'song_path') and current_track_object.song_path:
                relative_song_path = os.path.relpath(
                    current_track_object.song_path,
                    start=os.path.join(self.__output_dir, "playlists")
                )
                with open(m3u_path, "a", encoding="utf-8") as m3u_file:
                    m3u_file.write(f"{relative_song_path}\n")
            # --------------------------------------------------

        if self.__make_zip:
            playlist_title = self.__json_data['title']
            zip_name = f"{self.__output_dir}/{playlist_title} [playlist {self.__ids}]"
            create_zip(tracks, zip_name=zip_name)
            playlist.zip_path = zip_name

        # Report playlist done status
        playlist_name = self.__json_data.get('title', 'Unknown Playlist')
        playlist_owner = self.__json_data.get('creator', {}).get('name', 'Unknown Owner')
        total_tracks = self.__json_data.get('nb_tracks', 0)
        
        successful_tracks = []
        failed_tracks = []
        skipped_tracks = []
        for track in tracks:
            track_name = track.tags.get('music') or track.tags.get('name', 'Unknown Track')
            artist_name = track.tags.get('artist', 'Unknown Artist')
            track_info = {
                "name": track_name,
                "artist": artist_name
            }
            if getattr(track, 'was_skipped', False):
                skipped_tracks.append(track_info)
            elif track.success:
                successful_tracks.append(track_info)
            else:
                track_info["reason"] = getattr(track, 'error_message', 'Unknown reason')
                failed_tracks.append(track_info)

        report_progress(
            reporter=Download_JOB.progress_reporter,
            report_type="playlist",
            owner=playlist_owner,
            status="done",
            total_tracks=total_tracks,
            name=playlist_name,
            url=f"https://deezer.com/playlist/{self.__ids}",
            summary={
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
