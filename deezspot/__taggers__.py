#!/usr/bin/python3

from base64 import b64encode
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
from deezspot.models import Track, Episode
import requests

def request(url):
    response = requests.get(url)
    response.raise_for_status()
    return response

from mutagen.id3 import (
	ID3NoHeaderError,
	ID3, APIC, USLT, SYLT,
	COMM, TSRC, TRCK, TIT2,
	TLEN, TEXT, TCON, TALB, TBPM,
	TPE1, TYER, TDAT, TPOS, TPE2,
	TPUB, TCOP, TXXX, TCOM, IPLS
)

def __write_flac(song, data):
	tag = FLAC(song)
	tag.delete()
	images = Picture()
	images.type = 3
	images.mime = 'image/jpeg'
	images.data = data['image']
	tag.clear_pictures()
	tag.add_picture(images)
	tag['lyrics'] = data['lyric']
	tag['artist'] = data['artist']
	tag['title'] = data['music']
	tag['date'] = f"{data['year'].year}/{data['year'].month}/{data['year'].day}"
	tag['album'] = data['album']
	tag['tracknumber'] = f"{data['tracknum']}"
	tag['discnumber'] = f"{data['discnum']}"
	tag['genre'] = data['genre']
	tag['albumartist'] = data['ar_album']
	tag['author'] = data['author']
	tag['composer'] = data['composer']
	tag['copyright'] = data['copyright']
	tag['bpm'] = f"{data['bpm']}"
	tag['length'] = f"{int(data['duration'] * 1000)}"
	tag['organization'] = data['label']
	tag['isrc'] = data['isrc']
	tag['lyricist'] = data['lyricist']
	tag['version'] = data['version']
	tag.save()


def __write_mp3(song, data):
	try:
		audio = ID3(song)
		audio.delete()
	except ID3NoHeaderError:
		audio = ID3()

	audio.add(
		APIC(
			mime = "image/jpeg",
			type = 3,
			desc = "album front cover",
			data = data['image']
		)
	)

	audio.add(
		COMM(
			lang = "eng",
			desc = "my comment",
			text = "DO NOT USE FOR YOUR OWN EARNING"
		)
	)

	audio.add(
		USLT(
			text = data['lyric']
		)
	)

	audio.add(
		SYLT(
			type = 1,
			format = 2,
			desc = "sync lyric song",
			text = data['lyric_sync']
		)
	)

	audio.add(
		TSRC(
			text = data['isrc']
		)
	)

	audio.add(
		TRCK(
			text = f"{data['tracknum']}/{data['nb_tracks']}"
		)
	)

	audio.add(
		TIT2(
			text = data['music']
		)
	)

	audio.add(
		TLEN(
			text = f"{data['duration']}"
		)
	)

	audio.add(
		TEXT(
			text = data['lyricist']
		)
	)

	audio.add(
		TCON(
			text = data['genre']
		)
	)

	audio.add(
		TALB(
			text = data['album']
		)
	)

	audio.add(
		TBPM(
			text = f"{data['bpm']}" 
		)
	)

	audio.add(
		TPE1(
			text = data['artist']
		)
	)

	audio.add(
		TYER(
			text = f"{data['year'].year}"
		)
	)

	audio.add(
		TDAT(
			text = f"{data['year'].day}{data['year'].month}"
		)
	)

	audio.add(
		TPOS(
			text = f"{data['discnum']}/{data['discnum']}"
		)
	)

	audio.add(
		TPE2(
			text = data['ar_album']
		)
	)

	audio.add(
		TPUB(
			text = data['label']
		)
	)

	audio.add(
		TCOP(
			text = data['copyright']
		)
	)

	audio.add(
		TXXX(
			desc = "REPLAYGAIN_TRACK_GAIN",
			text = f"{data['gain']}"
		)
	)

	audio.add(
		TCOM(
			text = data['composer']
		)
	)

	audio.add(
		IPLS(
			people = [
				data['author']
			]
		)
	)

	audio.save(song, v2_version = 3)

def __write_ogg(song, song_metadata):
    audio = OggVorbis(song)
    audio.delete()

    # Standard Vorbis comment fields mapping
    field_mapping = {
        'music': 'title',
        'artist': 'artist',
        'album': 'album',
        'tracknum': 'tracknumber',
        'discnum': 'discnumber',
        'year': 'date',
        'genre': 'genre',
        'isrc': 'isrc',
        'description': 'description',
        'ar_album': 'albumartist',
        'composer': 'composer',
        'copyright': 'copyright',
        'bpm': 'bpm',
        'lyricist': 'lyricist',
        'version': 'version'
    }

    # Add standard text metadata
    for source_key, vorbis_key in field_mapping.items():
        if source_key in song_metadata:
            value = song_metadata[source_key]
            
            # Special handling for date field
            if vorbis_key == 'date':
                # Convert datetime object to YYYY-MM-DD string format
                if hasattr(value, 'strftime'):
                    value = value.strftime('%Y-%m-%d')
                # Handle string timestamps if necessary
                elif isinstance(value, str) and ' ' in value:
                    value = value.split()[0]
            
            # Skip "Unknown" BPM values or other non-numeric BPM values
            if vorbis_key == 'bpm' and (value == "Unknown" or not isinstance(value, (int, float)) and not str(value).isdigit()):
                continue
                
            audio[vorbis_key] = [str(value)]

    # Add lyrics if present
    if 'lyric' in song_metadata:
        audio['lyrics'] = [str(song_metadata['lyric'])]

    # Handle cover art
    if 'image' in song_metadata:
        try:
            image = Picture()
            image.type = 3  # Front cover
            image.mime = 'image/jpeg'
            image.desc = 'Cover'
            
            if isinstance(song_metadata['image'], bytes):
                image.data = song_metadata['image']
            else:
                image.data = request(song_metadata['image']).content
                
            # Encode using base64 as required by Vorbis spec
            audio['metadata_block_picture'] = [
                b64encode(image.write()).decode('utf-8')
            ]
        except Exception as e:
            print(f"Error adding cover art: {e}")

    # Additional validation for numeric fields - exclude BPM since we already handled it
    numeric_fields = ['tracknumber', 'discnumber']
    for field in numeric_fields:
        if field in audio:
            try:
                int(audio[field][0])
            except ValueError:
                print(f"Warning: Invalid numeric value for {field}")
                del audio[field]

    audio.save()

def write_tags(media):
    if isinstance(media, Track):
        song = media.song_path
    elif isinstance(media, Episode):
        song = media.episode_path
    else:
        raise ValueError("Unsupported media type")

    song_metadata = media.tags
    f_format = media.file_format

    if f_format == ".flac":
        __write_flac(song, song_metadata)
    elif f_format == ".ogg":
        __write_ogg(song, song_metadata)
    else:
        __write_mp3(song, song_metadata)

def check_track(media):
    if isinstance(media, Track):
        song = media.song_path
    elif isinstance(media, Episode):
        song = media.episode_path
    else:
        raise ValueError("Unsupported media type")

    f_format = media.file_format
    is_ok = False

    # Add your logic to check the track/episode here

    return is_ok