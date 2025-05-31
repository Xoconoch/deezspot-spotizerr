#!/usr/bin/python3

class Preferences:
    def __init__(self) -> None:
        self.link = None
        self.song_metadata: dict = None
        self.quality_download = None
        self.output_dir = None
        self.ids = None
        self.json_data = None
        self.recursive_quality = None
        self.recursive_download = None
        self.not_interface = None
        self.method_save = None
        self.make_zip = None
        self.real_time_dl = None ,
        self.custom_dir_format = None,
        self.custom_track_format = None,
        self.pad_tracks = True  # Default to padded track numbers (01, 02, etc.)
        self.initial_retry_delay = 30  # Default initial retry delay in seconds
        self.retry_delay_increase = 30  # Default increase in delay between retries in seconds
        self.max_retries = 5  # Default maximum number of retries per track