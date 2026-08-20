"""Minimal ID3v2 text-frame reader (stdlib only; mutagen is unavailable here).

Reads just the two frames that matter as an independent metadata vote —
TPE1 (artist) and TIT2 (title) — plus TLEN (duration, ms) when present.
Deliberately not a general tag library: anything unusual returns None rather
than guessing, and the caller simply falls back to the other four sources.
"""

import struct
from typing import Dict, Optional

_WANTED = {"TPE1": "artist", "TIT2": "title", "TLEN": "length",
           "TPE2": "album_artist", "TALB": "album"}


def _decode(raw: bytes) -> Optional[str]:
    if not raw:
        return None
    enc, body = raw[0], raw[1:]
    try:
        if enc == 0:
            s = body.decode("latin-1")
        elif enc == 1:
            s = body.decode("utf-16")          # honours the BOM
        elif enc == 2:
            s = body.decode("utf-16-be")
        elif enc == 3:
            s = body.decode("utf-8")
        else:
            return None
    except (UnicodeDecodeError, LookupError):
        return None
    return s.split("\x00")[0].strip() or None


def _synchsafe(b: bytes) -> int:
    n = 0
    for byte in b:
        n = (n << 7) | (byte & 0x7F)
    return n


def read_tags(path: str) -> Dict[str, Optional[str]]:
    """Return {'artist','title','length',...} for an MP3; {} if not readable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(10)
            if len(head) < 10 or head[:3] != b"ID3":
                return {}
            major = head[3]
            size = _synchsafe(head[6:10])
            blob = fh.read(size)
    except OSError:
        return {}

    out: Dict[str, Optional[str]] = {}
    pos = 0
    # v2.2 uses 3-byte ids/sizes; only v2.3/v2.4 are handled here.
    if major < 3:
        return {}
    while pos + 10 <= len(blob):
        fid = blob[pos:pos + 4]
        if not fid.strip(b"\x00"):
            break
        try:
            fid_s = fid.decode("ascii")
        except UnicodeDecodeError:
            break
        raw_size = blob[pos + 4:pos + 8]
        fsize = _synchsafe(raw_size) if major >= 4 else struct.unpack(">I", raw_size)[0]
        pos += 10
        if fsize <= 0 or pos + fsize > len(blob):
            break
        if fid_s in _WANTED:
            out[_WANTED[fid_s]] = _decode(blob[pos:pos + fsize])
        pos += fsize
    return out
