#!/usr/bin/python3

import os
import re
import subprocess
import logging
from os.path import exists, basename, dirname
from shutil import which

logger = logging.getLogger("deezspot")

# Define available audio formats and their properties
AUDIO_FORMATS = {
    "MP3": {
        "extension": ".mp3",
        "mime": "audio/mpeg",
        "ffmpeg_codec": "libmp3lame",
        "default_bitrate": "320k",
        "bitrates": ["32k", "64k", "96k", "128k", "192k", "256k", "320k"],
    },
    "AAC": {
        "extension": ".m4a",
        "mime": "audio/mp4",
        "ffmpeg_codec": "aac",
        "default_bitrate": "256k",
        "bitrates": ["32k", "64k", "96k", "128k", "192k", "256k"],
    },
    "OGG": {
        "extension": ".ogg",
        "mime": "audio/ogg",
        "ffmpeg_codec": "libvorbis",
        "default_bitrate": "256k",
        "bitrates": ["64k", "96k", "128k", "192k", "256k", "320k"],
    },
    "OPUS": {
        "extension": ".opus",
        "mime": "audio/opus",
        "ffmpeg_codec": "libopus",
        "default_bitrate": "128k",
        "bitrates": ["32k", "64k", "96k", "128k", "192k", "256k"],
    },
    "FLAC": {
        "extension": ".flac",
        "mime": "audio/flac",
        "ffmpeg_codec": "flac",
        "default_bitrate": None,  # Lossless, no bitrate needed
        "bitrates": [],
    },
    "WAV": {
        "extension": ".wav",
        "mime": "audio/wav",
        "ffmpeg_codec": "pcm_s16le",
        "default_bitrate": None,  # Lossless, no bitrate needed
        "bitrates": [],
    },
    "ALAC": {
        "extension": ".m4a",
        "mime": "audio/mp4",
        "ffmpeg_codec": "alac",
        "default_bitrate": None,  # Lossless, no bitrate needed
        "bitrates": [],
    }
}

def check_ffmpeg_available():
    """Check if FFmpeg is installed and available."""
    if which("ffmpeg") is None:
        logger.error("FFmpeg is not installed or not in PATH. Audio conversion is unavailable.")
        return False
    return True

def parse_format_string(format_string):
    """
    Parse a format string like "MP3_320" into (format, bitrate).
    Returns (format_name, bitrate) or (None, None) if invalid.
    """
    if not format_string or format_string.lower() == "false":
        return None, None
        
    # Check for format with bitrate specification
    format_match = re.match(r"^([A-Za-z]+)(?:_(\d+[kK]))?$", format_string)
    if format_match:
        format_name = format_match.group(1).upper()
        bitrate = format_match.group(2)
        
        # Validate format name
        if format_name not in AUDIO_FORMATS:
            logger.warning(f"Unknown audio format: {format_name}. Using original format.")
            return None, None
            
        # If format is lossless but bitrate was specified, log a warning
        if bitrate and AUDIO_FORMATS[format_name]["default_bitrate"] is None:
            logger.warning(f"Bitrate specified for lossless format {format_name}. Ignoring bitrate.")
            bitrate = None
            
        # If bitrate wasn't specified, use default
        if not bitrate and AUDIO_FORMATS[format_name]["default_bitrate"]:
            bitrate = AUDIO_FORMATS[format_name]["default_bitrate"]
            
        # Validate bitrate if specified
        if bitrate and AUDIO_FORMATS[format_name]["bitrates"] and bitrate.lower() not in [b.lower() for b in AUDIO_FORMATS[format_name]["bitrates"]]:
            logger.warning(f"Invalid bitrate {bitrate} for {format_name}. Using default {AUDIO_FORMATS[format_name]['default_bitrate']}.")
            bitrate = AUDIO_FORMATS[format_name]["default_bitrate"]
            
        return format_name, bitrate
        
    # Simple format name without bitrate
    if format_string.upper() in AUDIO_FORMATS:
        format_name = format_string.upper()
        bitrate = AUDIO_FORMATS[format_name]["default_bitrate"]
        return format_name, bitrate
        
    logger.warning(f"Invalid format specification: {format_string}. Using original format.")
    return None, None

def get_output_path(input_path, format_name):
    """Get the output path with the new extension based on the format."""
    if not format_name or format_name not in AUDIO_FORMATS:
        return input_path
        
    dir_name = dirname(input_path)
    file_name = basename(input_path)
    
    # Find the position of the last period to replace extension
    dot_pos = file_name.rfind('.')
    if dot_pos > 0:
        new_file_name = file_name[:dot_pos] + AUDIO_FORMATS[format_name]["extension"]
    else:
        new_file_name = file_name + AUDIO_FORMATS[format_name]["extension"]
        
    return os.path.join(dir_name, new_file_name)

def register_active_download(path):
    """
    Register a file as being actively downloaded.
    This is a placeholder that both modules implement, so we declare it here
    to maintain the interface.
    """
    # This function is expected to be overridden by the module
    pass

def unregister_active_download(path):
    """
    Unregister a file from the active downloads list.
    This is a placeholder that both modules implement, so we declare it here
    to maintain the interface.
    """
    # This function is expected to be overridden by the module
    pass

def convert_audio(input_path, format_name=None, bitrate=None, register_func=None, unregister_func=None):
    """
    Convert audio file to the specified format and bitrate.
    
    Args:
        input_path: Path to the input audio file
        format_name: Target format name (e.g., 'MP3', 'OGG', 'FLAC')
        bitrate: Target bitrate (e.g., '320k', '128k')
        register_func: Function to register a file as being actively downloaded
        unregister_func: Function to unregister a file from the active downloads list
        
    Returns:
        Path to the converted file, or the original path if no conversion was done
    """
    # Initialize the register and unregister functions
    if register_func:
        global register_active_download
        register_active_download = register_func
    
    if unregister_func:
        global unregister_active_download
        unregister_active_download = unregister_func
    
    # If no format specified or FFmpeg not available, return the original path
    if not format_name or not check_ffmpeg_available():
        return input_path
        
    # Validate format and get format details
    if format_name not in AUDIO_FORMATS:
        logger.warning(f"Unknown format: {format_name}. Using original format.")
        return input_path
        
    format_details = AUDIO_FORMATS[format_name]
    
    # Skip conversion if the file is already in the target format
    if input_path.lower().endswith(format_details["extension"].lower()):
        # Only do conversion if a specific bitrate is requested
        if not bitrate or format_details["default_bitrate"] is None:
            logger.info(f"File {input_path} is already in {format_name} format. Skipping conversion.")
            return input_path
    
    # Get the output path
    output_path = get_output_path(input_path, format_name)
    
    # Use a temporary file for the conversion to avoid conflicts
    temp_output = output_path + ".tmp"
    
    # Register the temporary file
    register_active_download(temp_output)
    
    try:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", input_path]
        
        # Add bitrate parameter for lossy formats
        if bitrate and format_details["bitrates"]:
            cmd.extend(["-b:a", bitrate])
        
        # Add codec parameter
        cmd.extend(["-c:a", format_details["ffmpeg_codec"]])
        
        # For some formats, add additional parameters
        if format_name == "MP3":
            # Use high quality settings for MP3
            if not bitrate or int(bitrate.replace('k', '')) >= 256:
                cmd.extend(["-q:a", "0"])
        
        # Add output file
        cmd.append(temp_output)
        
        # Run the conversion
        logger.info(f"Converting {input_path} to {format_name}" + (f" at {bitrate}" if bitrate else ""))
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if process.returncode != 0:
            logger.error(f"Audio conversion failed: {process.stderr}")
            if exists(temp_output):
                os.remove(temp_output)
                unregister_active_download(temp_output)
            return input_path
        
        # Register the output file and unregister the temp file
        register_active_download(output_path)
        
        # Rename the temporary file to the final file
        os.rename(temp_output, output_path)
        unregister_active_download(temp_output)
        
        # Remove the original file if the conversion was successful and the files are different
        if exists(output_path) and input_path != output_path and exists(input_path):
            os.remove(input_path)
            unregister_active_download(input_path)
        
        logger.info(f"Successfully converted to {format_name}" + (f" at {bitrate}" if bitrate else ""))
        return output_path
        
    except Exception as e:
        logger.error(f"Error during audio conversion: {str(e)}")
        # Clean up temp files
        if exists(temp_output):
            os.remove(temp_output)
            unregister_active_download(temp_output)
        # Return the original file path
        return input_path
