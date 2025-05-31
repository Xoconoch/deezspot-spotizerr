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