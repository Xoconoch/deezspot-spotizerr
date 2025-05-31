#!/usr/bin/python3

import re
from os import makedirs
from datetime import datetime
from urllib.parse import urlparse
from requests import get as req_get
from zipfile import ZipFile, ZIP_DEFLATED
from deezspot.models.track import Track
from deezspot.exceptions import InvalidLink
from deezspot.libutils.others_settings import supported_link, header

from os.path import (
    isdir, basename,
    join, isfile
)

def link_is_valid(link):
    netloc = urlparse(link).netloc

    if not any(
        c_link == netloc
        for c_link in supported_link
    ):
        raise InvalidLink(link)

def get_ids(link):
    parsed = urlparse(link)
    path = parsed.path
    ids = path.split("/")[-1]

    return ids

def request(url):
    thing = req_get(url, headers=header)
    return thing

def __check_dir(directory):
    if not isdir(directory):
        makedirs(directory)

def sanitize_name(string, max_length=200):
    """Sanitize a string for use as a filename or directory name.
    
    Args:
        string: The string to sanitize
        max_length: Maximum length for the resulting string
        
    Returns:
        A sanitized string safe for use in file paths
    """
    if string is None:
        return "Unknown"
        
    # Convert to string if not already
    string = str(string)
    
    # Enhance character replacement for filenames
    replacements = {
        "\\": "-",  # Backslash to hyphen
        "/": "-",   # Forward slash to hyphen
        ":": "-",   # Colon to hyphen
        "*": "+",   # Asterisk to plus
        "?": "",     # Question mark removed
        "\"": "'",  # Double quote to single quote
        "<": "[",   # Less than to open bracket
        ">": "]",   # Greater than to close bracket
        "|": "-",   # Pipe to hyphen
        "&": "and", # Ampersand to 'and'
        "$": "s",   # Dollar to 's'
        ";": ",",   # Semicolon to comma
        "\t": " ",  # Tab to space
        "\n": " ",  # Newline to space
        "\r": " ",  # Carriage return to space
        "\0": "",   # Null byte removed
    }
    
    for old, new in replacements.items():
        string = string.replace(old, new)
    
    # Remove any other non-printable characters
    string = ''.join(char for char in string if char.isprintable())
    
    # Remove leading/trailing whitespace
    string = string.strip()
    
    # Replace multiple spaces with a single space
    string = re.sub(r'\s+', ' ', string)
    
    # Truncate if too long
    if len(string) > max_length:
        string = string[:max_length]
        
    # Ensure we don't end with a dot or space (can cause issues in some filesystems)
    string = string.rstrip('. ')
    
    # Provide a fallback for empty strings
    if not string:
        string = "Unknown"
        
    return string

# Keep the original function name for backward compatibility
def var_excape(string):
    """Legacy function name for backward compatibility."""
    return sanitize_name(string)

def convert_to_date(date: str):
    if date == "0000-00-00":
        date = "0001-01-01"
    elif date.isdigit():
        date = f"{date}-01-01"
    date = datetime.strptime(date, "%Y-%m-%d")
    return date

def what_kind(link):
    url = request(link).url
    if url.endswith("/"):
        url = url[:-1]
    return url

def __get_tronc(string):
    l_encoded = len(string.encode())
    if l_encoded > 242:
        n_tronc = len(string) - l_encoded - 242
    else:
        n_tronc = 242
    return n_tronc

def apply_custom_format(format_str, metadata: dict, pad_tracks=True) -> str:
    """
    Replaces placeholders in the format string with values from metadata.
    Placeholders are denoted by %key%, for example: "%ar_album%/%album%".
    The pad_tracks parameter controls whether track numbers are padded with leading zeros.
    """
    def replacer(match):
        key = match.group(1)
        # Alias and special keys
        if key == 'album_artist':
            raw_value = metadata.get('ar_album', metadata.get('album_artist'))
        elif key == 'year':
            raw_value = metadata.get('release_date', metadata.get('year'))
        elif key == 'date':
            raw_value = metadata.get('release_date', metadata.get('date'))
        elif key == 'discnum':
            raw_value = metadata.get('disc_number', metadata.get('discnum'))
        else:
            # All other placeholders map directly
            raw_value = metadata.get(key)
        
        # Friendly names for missing metadata
        key_mappings = {
            'ar_album': 'album artist',
            'album_artist': 'album artist',
            'artist': 'artist',
            'album': 'album',
            'tracknum': 'track number',
            'discnum': 'disc number',
            'date': 'release date',
            'year': 'year',
            'genre': 'genre',
            'isrc': 'ISRC',
            'explicit': 'explicit flag',
            'duration': 'duration',
            'publisher': 'publisher',
            'composer': 'composer',
            'copyright': 'copyright',
            'author': 'author',
            'lyricist': 'lyricist',
            'version': 'version',
            'comment': 'comment',
            'encodedby': 'encoded by',
            'language': 'language',
            'lyrics': 'lyrics',
            'mood': 'mood',
            'rating': 'rating',
            'website': 'website',
            'replaygain_album_gain': 'replaygain album gain',
            'replaygain_album_peak': 'replaygain album peak',
            'replaygain_track_gain': 'replaygain track gain',
            'replaygain_track_peak': 'replaygain track peak',
        }
        
        # Custom formatting for specific keys
        if key == 'tracknum' and pad_tracks and raw_value not in (None, ''):
            try:
                return sanitize_name(f"{int(raw_value):02d}")
            except (ValueError, TypeError):
                pass
        if key == 'discnum' and raw_value not in (None, ''):
            try:
                return sanitize_name(f"{int(raw_value):02d}")
            except (ValueError, TypeError):
                pass
        if key == 'year' and raw_value not in (None, ''):
            m = re.match(r"^(\d{4})", str(raw_value))
            if m:
                return sanitize_name(m.group(1))
        
        # Handle missing metadata with descriptive default
        if raw_value in (None, ''):
            friendly = key_mappings.get(key, key.replace('_', ' '))
            return sanitize_name(f"Unknown {friendly}")
        
        # Default handling
        return sanitize_name(str(raw_value))
    return re.sub(r'%(\w+)%', replacer, format_str)

def __get_dir(song_metadata, output_dir, method_save, custom_dir_format=None, pad_tracks=True):
    """
    Returns the final directory based either on a custom directory format string
    or the legacy method_save logic.
    """
    if song_metadata is None:
        raise ValueError("song_metadata cannot be None")
    
    if custom_dir_format is not None:
        # Use the custom format string
        dir_name = apply_custom_format(custom_dir_format, song_metadata, pad_tracks)
    else:
        # Legacy logic based on method_save (for episodes or albums)
        if 'show' in song_metadata and 'name' in song_metadata:
            show = var_excape(song_metadata.get('show', ''))
            episode = var_excape(song_metadata.get('name', ''))
            if show and episode:
                dir_name = f"{show} - {episode}"
            elif show:
                dir_name = show
            elif episode:
                dir_name = episode
            else:
                dir_name = "Unknown Episode"
        else:
            album = var_excape(song_metadata.get('album', ''))
            ar_album = var_excape(song_metadata.get('ar_album', ''))
            if method_save == 0:
                dir_name = f"{album} - {ar_album}"
            elif method_save == 1:
                dir_name = f"{ar_album}/{album}"
            elif method_save == 2:
                dir_name = f"{album} - {ar_album}"
            elif method_save == 3:
                dir_name = f"{album} - {ar_album}"
            else:
                dir_name = "Unknown"
    
    # Prevent absolute paths and sanitize each directory segment
    dir_name = dir_name.strip('/')
    dir_name = '/'.join(sanitize_name(seg) for seg in dir_name.split('/') if seg)
    final_dir = join(output_dir, dir_name)
    if not isdir(final_dir):
        makedirs(final_dir)
    return final_dir

def set_path(
    song_metadata, output_dir,
    song_quality, file_format, method_save,
    is_episode=False,
    custom_dir_format=None,
    custom_track_format=None,
    pad_tracks=True
):
    if song_metadata is None:
        raise ValueError("song_metadata cannot be None")
    
    if is_episode:
        if custom_track_format is not None:
            song_name = apply_custom_format(custom_track_format, song_metadata, pad_tracks)
        else:
            show = var_excape(song_metadata.get('show', ''))
            episode = var_excape(song_metadata.get('name', ''))
            if show and episode:
                song_name = f"{show} - {episode}"
            elif show:
                song_name = show
            elif episode:
                song_name = episode
            else:
                song_name = "Unknown Episode"
    else:
        if custom_track_format is not None:
            song_name = apply_custom_format(custom_track_format, song_metadata, pad_tracks)
        else:
            album = var_excape(song_metadata.get('album', ''))
            artist = var_excape(song_metadata.get('artist', ''))
            music = var_excape(song_metadata.get('music', ''))  # Track title
            discnum = song_metadata.get('discnum', '')
            tracknum = song_metadata.get('tracknum', '')

            if method_save == 0:
                song_name = f"{album} CD {discnum} TRACK {tracknum}"
            elif method_save == 1:
                try:
                    if pad_tracks:
                        tracknum = f"{int(tracknum):02d}"  # Format as two digits with padding
                    else:
                        tracknum = f"{int(tracknum)}"  # Format without padding
                except (ValueError, TypeError):
                    pass  # Fallback to raw value
                tracknum_clean = var_excape(str(tracknum))
                tracktitle_clean = var_excape(music)
                song_name = f"{tracknum_clean}. {tracktitle_clean}"
            elif method_save == 2:
                isrc = song_metadata.get('isrc', '')
                song_name = f"{music} - {artist} [{isrc}]"
            elif method_save == 3:
                song_name = f"{discnum}|{tracknum} - {music} - {artist}"
    
    # Sanitize song_name to remove invalid chars and prevent '/'
    song_name = sanitize_name(song_name)
    # Truncate to avoid filesystem limits
    max_length = 255 - len(output_dir) - len(file_format)
    song_name = song_name[:max_length]

    # Build final path
    song_dir = __get_dir(song_metadata, output_dir, method_save, custom_dir_format, pad_tracks)
    __check_dir(song_dir)
    n_tronc = __get_tronc(song_name)
    song_path = f"{song_dir}/{song_name[:n_tronc]}{file_format}"
    return song_path

def create_zip(
    tracks: list[Track],
    output_dir=None,
    song_metadata=None,
    song_quality=None,
    method_save=0,
    zip_name=None
):
    if not zip_name:
        album = var_excape(song_metadata.get('album', ''))
        song_dir = __get_dir(song_metadata, output_dir, method_save)
        if method_save == 0:
            zip_name = f"{album}"
        elif method_save == 1:
            artist = var_excape(song_metadata.get('ar_album', ''))
            zip_name = f"{album} - {artist}"
        elif method_save == 2:
            artist = var_excape(song_metadata.get('ar_album', ''))
            upc = song_metadata.get('upc', '')
            zip_name = f"{album} - {artist} {upc}"
        elif method_save == 3:
            artist = var_excape(song_metadata.get('ar_album', ''))
            upc = song_metadata.get('upc', '')
            zip_name = f"{album} - {artist} {upc}"
        n_tronc = __get_tronc(zip_name)
        zip_name = zip_name[:n_tronc]
        zip_name += ".zip"
        zip_path = f"{song_dir}/{zip_name}"
    else:
        zip_path = zip_name

    z = ZipFile(zip_path, "w", ZIP_DEFLATED)
    for track in tracks:
        if not track.success:
            continue
        c_song_path = track.song_path
        song_path = basename(c_song_path)
        if not isfile(c_song_path):
            continue
        z.write(c_song_path, song_path)
    z.close()
    return zip_path

def trasform_sync_lyric(lyric):
    sync_array = []
    for a in lyric:
        if "milliseconds" in a:
            arr = (a['line'], int(a['milliseconds']))
            sync_array.append(arr)
    return sync_array
