import os
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, TPOS, TSRC, TPE2, TCOM, USLT, TPUB, COMM, TCOP, TENC, TLAN, TYER, TXXX
from mutagen.mp4 import MP4
from mutagen import File
from deezspot.libutils.logging_utils import logger

def write_tags(track):
    """
    Write metadata tags to the audio file.
    
    Args:
        track: Track object containing metadata
    """
    try:
        if not track.song_path:
            logger.warning("No song path provided for tagging")
            return
            
        # Get the audio file
        audio = File(track.song_path)
        
        # Common metadata fields
        metadata = {
            'title': track.song_metadata['music'],
            'artist': track.song_metadata['artist'],
            'album': track.song_metadata['album'],
            'date': track.song_metadata.get('date', ''),
            'genre': track.song_metadata.get('genre', ''),
            'tracknumber': track.song_metadata.get('tracknum', ''),
            'discnumber': track.song_metadata.get('discnum', ''),
            'isrc': track.song_metadata.get('isrc', ''),
            'albumartist': track.song_metadata.get('album_artist', ''),
            'publisher': track.song_metadata.get('publisher', ''),
            'comment': track.song_metadata.get('comment', ''),
            'composer': track.song_metadata.get('composer', ''),
            'copyright': track.song_metadata.get('copyright', ''),
            'encodedby': track.song_metadata.get('encodedby', ''),
            'language': track.song_metadata.get('language', ''),
            'lyrics': track.song_metadata.get('lyrics', ''),
            'mood': track.song_metadata.get('mood', ''),
            'rating': track.song_metadata.get('rating', ''),
            'replaygain_album_gain': track.song_metadata.get('replaygain_album_gain', ''),
            'replaygain_album_peak': track.song_metadata.get('replaygain_album_peak', ''),
            'replaygain_track_gain': track.song_metadata.get('replaygain_track_gain', ''),
            'replaygain_track_peak': track.song_metadata.get('replaygain_track_peak', ''),
            'website': track.song_metadata.get('website', ''),
            'year': track.song_metadata.get('year', ''),
            'explicit': track.song_metadata.get('explicit', '0')
        }
        
        # Handle different file formats
        if isinstance(audio, FLAC):
            # FLAC specific handling
            for key, value in metadata.items():
                if value:
                    audio[key] = str(value)
                    
        elif isinstance(audio, MP3):
            # MP3 specific handling
            id3 = ID3()
            for key, value in metadata.items():
                if value:
                    if key == 'title':
                        id3.add(TIT2(encoding=3, text=value))
                    elif key == 'artist':
                        id3.add(TPE1(encoding=3, text=value))
                    elif key == 'album':
                        id3.add(TALB(encoding=3, text=value))
                    elif key == 'date':
                        id3.add(TDRC(encoding=3, text=value))
                    elif key == 'genre':
                        id3.add(TCON(encoding=3, text=value))
                    elif key == 'tracknumber':
                        id3.add(TRCK(encoding=3, text=value))
                    elif key == 'discnumber':
                        id3.add(TPOS(encoding=3, text=value))
                    elif key == 'isrc':
                        id3.add(TSRC(encoding=3, text=value))
                    elif key == 'albumartist':
                        id3.add(TPE2(encoding=3, text=value))
                    elif key == 'composer':
                        id3.add(TCOM(encoding=3, text=value))
                    elif key == 'lyrics':
                        id3.add(USLT(encoding=3, lang='eng', desc='', text=value))
                    elif key == 'publisher':
                        id3.add(TPUB(encoding=3, text=value))
                    elif key == 'comment':
                        id3.add(COMM(encoding=3, lang='eng', desc='', text=value))
                    elif key == 'copyright':
                        id3.add(TCOP(encoding=3, text=value))
                    elif key == 'encodedby':
                        id3.add(TENC(encoding=3, text=value))
                    elif key == 'language':
                        id3.add(TLAN(encoding=3, text=value))
                    elif key == 'year' and not metadata.get('date'):
                        id3.add(TYER(encoding=3, text=value))
                    elif key == 'mood':
                        id3.add(TXXX(encoding=3, desc='MOOD', text=value))
                    elif key == 'explicit':
                        id3.add(TXXX(encoding=3, desc='EXPLICIT', text=value))
                    elif key == 'rating':
                        id3.add(TXXX(encoding=3, desc='RATING', text=value))
                    elif key == 'website':
                        id3.add(TXXX(encoding=3, desc='WEBSITE', text=value))
                    elif key == 'replaygain_track_gain':
                        id3.add(TXXX(encoding=3, desc='REPLAYGAIN_TRACK_GAIN', text=value))
                    elif key == 'replaygain_track_peak':
                        id3.add(TXXX(encoding=3, desc='REPLAYGAIN_TRACK_PEAK', text=value))
                    elif key == 'replaygain_album_gain':
                        id3.add(TXXX(encoding=3, desc='REPLAYGAIN_ALBUM_GAIN', text=value))
                    elif key == 'replaygain_album_peak':
                        id3.add(TXXX(encoding=3, desc='REPLAYGAIN_ALBUM_PEAK', text=value))
                        
            audio.tags = id3
            
        elif isinstance(audio, MP4):
            # MP4 specific handling
            for key, value in metadata.items():
                if value:
                    if key == 'title':
                        audio['\xa9nam'] = value
                    elif key == 'artist':
                        audio['\xa9ART'] = value
                    elif key == 'album':
                        audio['\xa9alb'] = value
                    elif key == 'date':
                        audio['\xa9day'] = value
                    elif key == 'genre':
                        audio['\xa9gen'] = value
                    elif key == 'tracknumber':
                        parts = str(value).split('/')
                        track_num = int(parts[0])
                        total_tracks = int(parts[1]) if len(parts) > 1 else 0
                        audio['trkn'] = [(track_num, total_tracks)]
                    elif key == 'discnumber':
                        parts = str(value).split('/')
                        disc_num = int(parts[0])
                        total_discs = int(parts[1]) if len(parts) > 1 else 0
                        audio['disk'] = [(disc_num, total_discs)]
                    elif key == 'isrc':
                        audio['isrc'] = value
                    elif key == 'albumartist':
                        audio['aART'] = value
                    elif key == 'composer':
                        audio['\xa9wrt'] = value
                    elif key == 'lyrics':
                        audio['\xa9lyr'] = value
                    elif key == 'publisher':
                        audio['\xa9pub'] = value
                    elif key == 'comment':
                        audio['\xa9cmt'] = value
                    elif key == 'copyright':
                        audio['\xa9cpy'] = value
                    elif key == 'encodedby':
                        audio['\xa9too'] = value
                    elif key == 'explicit':
                        if value == '1': # True for explicit
                            audio['rtng'] = [4] # Explicit for iTunes
                        elif value == '0': # False for explicit
                            audio['rtng'] = [0] # None
                        # else: do not set rtng if value is not '0' or '1'
                        
        # Save the changes
        audio.save()
        logger.debug(f"Successfully wrote tags to {track.song_path}")
        
    except Exception as e:
        logger.error(f"Failed to write tags to {track.song_path}: {str(e)}")
        raise

def check_track(track):
    """
    Check if a track's metadata is valid.
    
    Args:
        track: Track object to check
        
    Returns:
        bool: True if track is valid, False otherwise
    """
    try:
        required_fields = ['music', 'artist', 'album']
        for field in required_fields:
            if field not in track.song_metadata or not track.song_metadata[field]:
                logger.warning(f"Missing required field: {field}")
                return False
                
        if not track.song_path or not os.path.exists(track.song_path):
            logger.warning("Track file does not exist")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to check track: {str(e)}")
        return False 