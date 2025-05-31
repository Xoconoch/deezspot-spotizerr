# DeezSpot

DeezSpot is a Python library that enables downloading songs, albums, playlists, and podcasts from both Deezer and Spotify. This fork includes tweaks for use with the [spotizerr](https://github.com/Xoconoch/spotizerr) project.

## Features

- Download tracks, albums, playlists, and podcasts from both Deezer and Spotify
- Search for music by name or download directly using links
- Support for different audio quality options
- Download an artist's discography
- Smart link detection to identify and process different types of content
- Tag downloaded files with correct metadata
- Customizable file and directory naming formats

## Installation

### From PyPI (recommended)

```bash
pip install git+https://github.com/Xoconoch/deezspot-fork-again.git
```

### From Source

```bash
git clone https://github.com/Xoconoch/deezspot-fork-again.git
cd deezspot-fork-again
pip install -e .
```

## Configuration

### Deezer Authentication

DeezSpot supports two methods of authentication for Deezer:

1. Using ARL token:
```python
from deezspot.deezloader import DeeLogin

# Authenticate with ARL
downloader = DeeLogin(arl="your_arl_token")
```

2. Using email and password:
```python
from deezspot.deezloader import DeeLogin

# Authenticate with email and password
downloader = DeeLogin(email="your_email", password="your_password")
```

### Spotify Authentication

For Spotify, you'll need a credentials file:

```python
from deezspot.spotloader import SpoLogin

# Authenticate with credentials file
downloader = SpoLogin(credentials_path="/path/to/credentials.json")
```

To create a credentials file, use a tool like [librespot-java](https://github.com/librespot-org/librespot-java) to generate it.

## Usage

### Downloading from Deezer

```python
from deezspot.deezloader import DeeLogin

# Initialize with your credentials
downloader = DeeLogin(arl="your_arl_token")

# Download a track
track = downloader.download_trackdee(
    "https://www.deezer.com/track/123456789",
    output_dir="./downloads",
    quality_download="FLAC"  # Options: MP3_320, FLAC, MP3_128
)

# Download an album
album = downloader.download_albumdee(
    "https://www.deezer.com/album/123456789",
    output_dir="./downloads",
    quality_download="MP3_320",
    make_zip=True  # Create a zip archive of the album
)

# Download a playlist
playlist = downloader.download_playlistdee(
    "https://www.deezer.com/playlist/123456789",
    output_dir="./downloads",
    quality_download="MP3_320"
)

# Download an artist's top tracks
tracks = downloader.download_artisttopdee(
    "https://www.deezer.com/artist/123456789",
    output_dir="./downloads"
)

# Search and download by name
track = downloader.download_name(
    artist="Artist Name",
    song="Song Title",
    output_dir="./downloads"
)
```

### Downloading from Spotify

```python
from deezspot.spotloader import SpoLogin
import logging
from deezspot import set_log_level, enable_file_logging

# Configure logging
set_log_level(logging.INFO)
enable_file_logging("spotify_downloads.log")

# Custom progress callback
def spotify_progress_callback(progress_data):
    status = progress_data.get("status")
    if status == "real_time":
        song = progress_data.get("song", "Unknown")
        percentage = progress_data.get("percentage", 0) * 100
        print(f"Downloading '{song}': {percentage:.1f}%")
    elif status == "downloading":
        print(f"Starting download: {progress_data.get('song', 'Unknown')}")
    elif status == "done":
        print(f"Completed: {progress_data.get('song', 'Unknown')}")

# Initialize Spotify client with progress callback
spotify = SpoLogin(
    credentials_path="credentials.json",
    spotify_client_id="your_client_id",
    spotify_client_secret="your_client_secret",
    progress_callback=spotify_progress_callback
)

# Or use silent mode for background operations
spotify_silent = SpoLogin(
    credentials_path="credentials.json",
    spotify_client_id="your_client_id",
    spotify_client_secret="your_client_secret",
    silent=True
)

# Download a track
spotify.download_track(
    "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
    output_dir="downloads",
    quality_download="HIGH",
    real_time_dl=True
)

# Download an album
album = spotify.download_album(
    "https://open.spotify.com/album/123456789",
    output_dir="./downloads",
    quality_download="HIGH",
    make_zip=True  # Create a zip archive of the album
)

# Download a playlist
playlist = spotify.download_playlist(
    "https://open.spotify.com/playlist/123456789",
    output_dir="./downloads"
)

# Download a podcast episode
episode = spotify.download_episode(
    "https://open.spotify.com/episode/123456789",
    output_dir="./downloads"
)

# Download an artist's discography
spotify.download_artist(
    "https://open.spotify.com/artist/123456789",
    album_type="album,single",  # Options: album, single, compilation, appears_on
    limit=50,  # Number of albums to retrieve
    output_dir="./downloads"
)
```

### Smart Download

Both the Deezer and Spotify interfaces provide a "smart" download function that automatically detects the type of content from the link:

```python
# For Deezer
result = downloader.download_smart("https://www.deezer.com/track/123456789")

# For Spotify
result = downloader.download_smart("https://open.spotify.com/album/123456789")
```

### Converting Spotify links to Deezer

DeezSpot can also convert Spotify links to Deezer for downloading with higher quality:

```python
# Convert and download a Spotify track using Deezer
track = downloader.download_trackspo("https://open.spotify.com/track/123456789")

# Convert and download a Spotify album using Deezer
album = downloader.download_albumspo("https://open.spotify.com/album/123456789")

# Convert and download a Spotify playlist using Deezer
playlist = downloader.download_playlistspo("https://open.spotify.com/playlist/123456789")
```

## Available Quality Options

### Deezer
- `MP3_320`: 320 kbps MP3
- `FLAC`: Lossless audio
- `MP3_128`: 128 kbps MP3

### Spotify
- `VERY_HIGH`: 320 kbps OGG
- `HIGH`: 160 kbps OGG
- `NORMAL`: 96 kbps OGG

## Common Parameters

Most download methods accept these common parameters:

- `output_dir`: Output directory for downloaded files (default: "Songs/")
- `quality_download`: Quality of audio files (see options above)
- `recursive_quality`: Try another quality if the selected one is not available (default: True)
- `recursive_download`: Try another API if the current one fails (default: True)
- `not_interface`: Hide download progress (default: False)
- `make_zip`: Create a zip archive for albums/playlists (default: False)
- `method_save`: How to save the downloads (default: varies by function)
- `custom_dir_format`: Custom directory naming format
- `custom_track_format`: Custom track naming format

## Custom Naming Formats

You can customize the output directory and file naming patterns:

```python
# Example of custom directory format
result = downloader.download_albumdee(
    "https://www.deezer.com/album/123456789",
    custom_dir_format="{artist}/{album} [{year}]"
)

# Example of custom track format
result = downloader.download_trackdee(
    "https://www.deezer.com/track/123456789",
    custom_track_format="{tracknumber} - {title}"
)
```

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Credits

This project is a fork of the [original deezspot library](https://github.com/jakiepari/deezspot).

# Deezspot Logging System

This document explains the enhanced logging system implemented in the Deezspot library, making it more suitable for production environments, Celery integrations, and other enterprise applications.

## Overview

The logging system in Deezspot provides:

- Standardized, structured log messages
- Multiple logging levels for different verbosity needs
- File logging capabilities for persistent logs
- Console output for interactive use
- JSON-formatted progress updates
- Custom progress callbacks for integration with other systems
- Silent mode for background operation

## Basic Configuration

### Setting Log Level

```python
from deezspot import set_log_level
import logging

# Available log levels:
# - logging.DEBUG (most verbose)
# - logging.INFO (default)
# - logging.WARNING
# - logging.ERROR
# - logging.CRITICAL (least verbose)

set_log_level(logging.INFO)  # Default level shows important information
set_log_level(logging.DEBUG)  # For detailed debugging information
set_log_level(logging.WARNING)  # For warnings and errors only
```

### Enabling File Logging

```python
from deezspot import enable_file_logging

# Enable logging to a file (in addition to console)
enable_file_logging("/path/to/logs/deezspot.log")

# With custom log level
enable_file_logging("/path/to/logs/deezspot.log", level=logging.DEBUG)
```

### Disabling Logging

```python
from deezspot import disable_logging

# Completely disable logging (except critical errors)
disable_logging()
```

## Progress Reporting

The library uses a structured JSON format for progress reporting, making it easy to integrate with other systems.

### Progress JSON Structure

For tracks:
```json
{
  "status": "downloading|progress|done|skipped|retrying",
  "type": "track",
  "album": "Album Name",
  "song": "Song Title",
  "artist": "Artist Name"
}
```

For real-time downloads:
```json
{
  "status": "real_time",
  "song": "Song Title",
  "artist": "Artist Name",
  "time_elapsed": 1500,
  "percentage": 0.75
}
```

For albums:
```json
{
  "status": "initializing|progress|done",
  "type": "album",
  "album": "Album Name",
  "artist": "Artist Name",
  "track": "Current Track Title",
  "current_track": "3/12"
}
```

For playlists:
```json
{
  "status": "initializing|progress|done",
  "type": "playlist",
  "name": "Playlist Name",
  "track": "Current Track Title",
  "current_track": "5/25",
  "total_tracks": 25
}
```

## Custom Progress Callbacks

For integration with other systems (like Celery), you can provide a custom progress callback function when initializing the library.

### Example with Custom Callback

```python
from deezspot.deezloader import DeeLogin

def my_progress_callback(progress_data):
    """
    Custom callback function to handle progress updates
    
    Args:
        progress_data: Dictionary containing progress information
    """
    status = progress_data.get("status")
    track_title = progress_data.get("song", "")
    
    if status == "downloading":
        print(f"Starting download: {track_title}")
    elif status == "progress":
        current = progress_data.get("current_track", "")
        print(f"Progress: {current} - {track_title}")
    elif status == "done":
        print(f"Completed: {track_title}")
    elif status == "real_time":
        percentage = progress_data.get("percentage", 0) * 100
        print(f"Downloading: {track_title} - {percentage:.1f}%")

# Initialize with custom callback
deezer = DeeLogin(
    arl="your_arl_token",
    progress_callback=my_progress_callback
)
```

### Silent Mode

If you want to disable progress reporting completely (for background operations), use silent mode:

```python
deezer = DeeLogin(
    arl="your_arl_token",
    silent=True
)
```

## Spotify Integration

For Spotify downloads, the same logging principles apply. Here's an example using the Spotify client:

```python
from deezspot.spotloader import SpoLogin
import logging
from deezspot import set_log_level, enable_file_logging

# Configure logging
set_log_level(logging.INFO)
enable_file_logging("spotify_downloads.log")

# Custom progress callback
def spotify_progress_callback(progress_data):
    status = progress_data.get("status")
    if status == "real_time":
        song = progress_data.get("song", "Unknown")
        percentage = progress_data.get("percentage", 0) * 100
        print(f"Downloading '{song}': {percentage:.1f}%")
    elif status == "downloading":
        print(f"Starting download: {progress_data.get('song', 'Unknown')}")
    elif status == "done":
        print(f"Completed: {progress_data.get('song', 'Unknown')}")

# Initialize Spotify client with progress callback
spotify = SpoLogin(
    credentials_path="credentials.json",
    spotify_client_id="your_client_id",
    spotify_client_secret="your_client_secret",
    progress_callback=spotify_progress_callback
)

# Or use silent mode for background operations
spotify_silent = SpoLogin(
    credentials_path="credentials.json",
    spotify_client_id="your_client_id",
    spotify_client_secret="your_client_secret",
    silent=True
)

# Download a track
spotify.download_track(
    "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
    output_dir="downloads",
    quality_download="HIGH",
    real_time_dl=True
)
```

## Celery Integration Example

Here's how to integrate the logging system with Celery for task progress reporting:

```python
from celery import Celery
from deezspot.deezloader import DeeLogin
import logging
from deezspot import enable_file_logging

# Configure Celery
app = Celery('tasks', broker='pyamqp://guest@localhost//')

# Configure logging
enable_file_logging("/path/to/logs/deezspot.log", level=logging.INFO)

@app.task(bind=True)
def download_music(self, link, output_dir):
    # Create a progress callback that updates the Celery task state
    def update_progress(progress_data):
        status = progress_data.get("status")
        
        if status == "downloading":
            self.update_state(
                state="DOWNLOADING",
                meta={
                    "track": progress_data.get("song", ""),
                    "progress": 0
                }
            )
        elif status == "progress":
            current, total = progress_data.get("current_track", "1/1").split("/")
            progress = int(current) / int(total)
            self.update_state(
                state="PROGRESS",
                meta={
                    "track": progress_data.get("track", ""),
                    "progress": progress
                }
            )
        elif status == "real_time":
            self.update_state(
                state="PROGRESS",
                meta={
                    "track": progress_data.get("song", ""),
                    "progress": progress_data.get("percentage", 0)
                }
            )
        elif status == "done":
            self.update_state(
                state="COMPLETED",
                meta={
                    "track": progress_data.get("song", ""),
                    "progress": 1.0
                }
            )
    
    # Initialize the client with the progress callback
    deezer = DeeLogin(
        arl="your_arl_token",
        progress_callback=update_progress
    )
    
    # Download the content
    result = deezer.download_smart(
        link=link,
        output_dir=output_dir,
        quality_download="MP3_320"
    )
    
    return {"status": "completed", "output": result.track.song_path}
```

## Direct Logger Access

For advanced use cases, you can directly access and use the logger:

```python
from deezspot.libutils.logging_utils import logger

# Use the logger directly
logger.debug("Detailed debugging information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical error message")

# Log structured data
import json
logger.info(json.dumps({
    "custom_event": "download_started",
    "metadata": {
        "source": "spotify",
        "track_id": "1234567890"
    }
}))
```

## Log Format

The default log format is:
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

Example:
```
2023-10-15 12:34:56,789 - deezspot - INFO - {"status": "downloading", "type": "track", "album": "Album Name", "song": "Song Title", "artist": "Artist Name"}
```

## Console vs File Logging

- By default, the library is configured to log at WARNING level to the console only
- You can enable file logging in addition to console logging
- File and console logging can have different log levels

## Using the Logger in Your Code

If you're extending the library or integrating it deeply into your application, you can use the logger directly:

```python
from deezspot.libutils.logging_utils import logger, ProgressReporter

# Create a custom progress reporter
my_reporter = ProgressReporter(
    callback=my_callback_function,
    silent=False,
    log_level=logging.INFO
)

# Report progress
my_reporter.report({
    "status": "custom_status",
    "message": "Custom progress message",
    "progress": 0.5
})

# Log directly
logger.info("Processing started")
```

## Test Script Example

Here's a complete example script that tests the Spotify functionality with logging enabled:

```python
#!/usr/bin/env python3

import os
import logging
from deezspot import set_log_level, enable_file_logging
from deezspot.spotloader import SpoLogin

def main():
    # Configure logging
    set_log_level(logging.INFO)  # Set to logging.DEBUG for more detailed output
    enable_file_logging("deezspot.log")

    # Spotify API credentials
    SPOTIFY_CLIENT_ID = "your_client_id"
    SPOTIFY_CLIENT_SECRET = "your_client_secret"
    
    # Path to your Spotify credentials file (from librespot)
    CREDENTIALS_PATH = "credentials.json"
    
    # Output directory for downloads
    OUTPUT_DIR = "downloads"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        # Initialize the Spotify client
        spotify = SpoLogin(
            credentials_path=CREDENTIALS_PATH,
            spotify_client_id=SPOTIFY_CLIENT_ID,
            spotify_client_secret=SPOTIFY_CLIENT_SECRET
        )

        # Test track download
        print("\nTesting track download...")
        track_url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
        spotify.download_track(
            track_url,
            output_dir=OUTPUT_DIR,
            quality_download="HIGH",
            real_time_dl=True,
            custom_dir_format="{artist}/{album}",
            custom_track_format="{tracknum} - {title}"
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        logging.error(f"Test failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
```

This logging system provides flexibility for both simple scripts and complex production applications, making it easier to monitor and integrate Deezspot in any environment.

## Callback Functionality

Both the Deezer and Spotify components of the deezspot library now support progress callbacks, allowing you to integrate download progress into your applications. This feature enables:

1. **Real-time Progress Tracking**: Monitor download progress for tracks, albums, playlists, and episodes
2. **Custom UI Integration**: Update your application's UI with download status
3. **Background Processing**: Run downloads silently in background tasks
4. **Task Management**: Integrate with task systems like Celery for distributed processing

### Common Callback Events

The progress callback function receives a dictionary with the following common fields:

- `status`: The current status of the operation (`initializing`, `downloading`, `progress`, `done`, `skipped`, `retrying`, `real_time`)
- `type`: The type of content (`track`, `album`, `playlist`, `episode`)
- Additional fields depending on the status and content type

### Usage in Both Components

Both the Deezer and Spotify components use the same callback system:

```python
# For Deezer
deezer = DeeLogin(
    arl="your_arl_token",
    progress_callback=my_callback_function,
    silent=False  # Set to True to disable progress reporting
)

# For Spotify
spotify = SpoLogin(
    credentials_path="credentials.json",
    spotify_client_id="your_client_id",
    spotify_client_secret="your_client_secret",
    progress_callback=my_callback_function,
    silent=False  # Set to True to disable progress reporting
)
```

The standardized callback system ensures that your application can handle progress updates consistently regardless of whether the content is being downloaded from Deezer or Spotify.
