#!/usr/bin/python3

import logging
import sys
from typing import Optional, Callable, Dict, Any, Union
import json

# Create the main library logger
logger = logging.getLogger('deezspot')

def configure_logger(
    level: int = logging.INFO,
    to_file: Optional[str] = None,
    to_console: bool = True,
    format_string: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
) -> None:
    """
    Configure the deezspot logger with the specified settings.

    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG)
        to_file: Optional file path to write logs
        to_console: Whether to output logs to console
        format_string: Log message format
    """
    # Clear existing handlers to avoid duplicates
    logger.handlers = []
    logger.setLevel(level)

    formatter = logging.Formatter(format_string)

    if to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if to_file:
        file_handler = logging.FileHandler(to_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

class ProgressReporter:
    """
    Handles progress reporting for the deezspot library.
    Supports both logging and custom callback functions.
    """
    def __init__(
        self, 
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        silent: bool = False,
        log_level: int = logging.INFO
    ):
        self.callback = callback
        self.silent = silent
        self.log_level = log_level

    def report(self, progress_data: Dict[str, Any]) -> None:
        """
        Report progress using the configured method.
        
        Args:
            progress_data: Dictionary containing progress information
        """
        if self.callback:
            # Call the custom callback function if provided
            self.callback(progress_data)
        elif not self.silent:
            # Log using JSON format
            logger.log(self.log_level, json.dumps(progress_data))

# --- Standardized Progress Report Format ---
# The report_progress function generates a standardized dictionary (JSON object)
# to provide detailed feedback about the download process.
#
# Base Structure:
# {
#   "type": "track" | "album" | "playlist" | "episode",
#   "status": "initializing" | "skipped" | "retrying" | "real-time" | "error" | "done"
#   ... other fields based on type and status
# }
#
# --- Field Definitions ---
#
# [ General Fields ]
#   - url: (str) The URL of the item being processed.
#   - convert_to: (str) Target audio format for conversion (e.g., "mp3").
#   - bitrate: (str) Target bitrate for conversion (e.g., "320").
#
# [ Type: "track" ]
#   - song: (str) The name of the track.
#   - artist: (str) The artist of the track.
#   - album: (str, optional) The album of the track.
#   - parent: (dict, optional) Information about the container (album/playlist).
#     { "type": "album"|"playlist", "name": str, "owner": str, "artist": str, ... }
#   - current_track: (int, optional) The track number in the context of a parent.
#   - total_tracks: (int, optional) The total tracks in the context of a parent.
#
#   [ Status: "skipped" ]
#     - reason: (str) The reason for skipping (e.g., "Track already exists...").
#
#   [ Status: "retrying" ]
#     - retry_count: (int) The current retry attempt number.
#     - seconds_left: (int) The time in seconds until the next retry attempt.
#     - error: (str) The error message that caused the retry.
#
#   [ Status: "real-time" ]
#     - time_elapsed: (int) Time in milliseconds since the download started.
#     - progress: (int) Download percentage (0-100).
#
#   [ Status: "error" ]
#     - error: (str) The detailed error message.
#
#   [ Status: "done" (for single track downloads) ]
#     - summary: (dict) A summary of the operation.
#
# [ Type: "album" | "playlist" ]
#   - title / name: (str) The title of the album or name of the playlist.
#   - artist / owner: (str) The artist of the album or owner of the playlist.
#   - total_tracks: (int) The total number of tracks.
#
#   [ Status: "done" ]
#     - summary: (dict) A detailed summary of the entire download operation.
#       {
#         "successful_tracks": [str],
#         "skipped_tracks": [str],
#         "failed_tracks": [{"track": str, "reason": str}],
#         "total_successful": int,
#         "total_skipped": int,
#         "total_failed": int
#       }
#

def report_progress(
    reporter: Optional["ProgressReporter"],
    report_type: str,
    status: str,
    song: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    url: Optional[str] = None,
    convert_to: Optional[str] = None,
    bitrate: Optional[str] = None,
    parent: Optional[Dict[str, Any]] = None,
    current_track: Optional[int] = None,
    total_tracks: Optional[Union[int, str]] = None,
    reason: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    retry_count: Optional[int] = None,
    seconds_left: Optional[int] = None,
    time_elapsed: Optional[int] = None,
    progress: Optional[int] = None,
    owner: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
):
    """Builds and reports a standardized progress dictionary after validating the input."""
    
    # --- Input Validation ---
    # Enforce the standardized format to ensure consistent reporting.
    if report_type == "track":
        if not all([song, artist]):
            raise ValueError("For report_type 'track', 'song' and 'artist' parameters are required.")
        if status == "skipped" and reason is None:
            raise ValueError("For a 'skipped' track, a 'reason' is required.")
        if status == "retrying" and not all(p is not None for p in [retry_count, seconds_left, error]):
            raise ValueError("For a 'retrying' track, 'retry_count', 'seconds_left', and 'error' are required.")
        if status == "real-time" and not all(p is not None for p in [time_elapsed, progress]):
            raise ValueError("For a 'real-time' track, 'time_elapsed' and 'progress' are required.")
        if status == "error" and error is None:
            raise ValueError("For an 'error' track, an 'error' message is required.")

    elif report_type == "album":
        if not all(p is not None for p in [title, artist, total_tracks]):
             raise ValueError("For report_type 'album', 'title', 'artist', and 'total_tracks' are required.")
        if status == "done" and summary is None:
            raise ValueError("For an 'album' with status 'done', a 'summary' is required.")

    elif report_type == "playlist":
        if not all(p is not None for p in [name, owner, total_tracks]):
            raise ValueError("For report_type 'playlist', 'name', 'owner', and 'total_tracks' are required.")
        if status == "done" and summary is None:
            raise ValueError("For a 'playlist' with status 'done', a 'summary' is required.")

    elif report_type == "episode":
        if not all([song, artist]): # song=episode_title, artist=show_name
            raise ValueError("For report_type 'episode', 'song' and 'artist' parameters are required.")
        if status == "retrying" and not all(p is not None for p in [retry_count, seconds_left, error]):
            raise ValueError("For a 'retrying' episode, 'retry_count', 'seconds_left', and 'error' are required.")
        if status == "error" and error is None:
            raise ValueError("For an 'error' episode, an 'error' message is required.")

    # --- Report Building ---
    report = {"type": report_type, "status": status}
    
    data_fields = {
        "song": song, "artist": artist, "album": album, "url": url,
        "convert_to": convert_to, "bitrate": bitrate, "parent": parent,
        "current_track": current_track, "total_tracks": total_tracks,
        "reason": reason, "summary": summary, "error": error,
        "retry_count": retry_count, "seconds_left": seconds_left,
        "time_elapsed": time_elapsed, "progress": progress,
        "owner": owner, "name": name, "title": title
    }

    for key, value in data_fields.items():
        if value is not None:
            report[key] = value

    if reporter:
        reporter.report(report)
    else:
        logger.info(json.dumps(report)) 