from datetime import datetime
from pathlib import Path


def date2path(date: datetime) -> Path:
    """
    Convert a time.struct_time to a Path of form YYYY/MM/DD
    :param date  A date
    """
    return (Path(str(date.year).rjust(4, "0"))
            / Path(str(date.month).rjust(2, "0"))
            / Path(str(date.day).rjust(2, "0")))


def exiftool_sanitize(s: str | int) -> str:
    """
    :param s  Exiftool "strings"
    """
    # to find more weirdness:
    # e6sync ... --log debug |& tee e6sync.log
    # perl -e 'my $current; my $new; while (my $line = <>) { if ($line =~ /^DEBUG:e6sync.storage.sidecar_manager:Current: (.*)$/) { $current = $1; } if ($line =~ /^DEBUG:e6sync.storage.sidecar_manager:New: (.*)$/) { $new = $1; if ($current ne $new) { print "Diff:\n$current\n$new\n\n"; } } }' < e6sync.log

    # exiftool decides to encode items as int in their json response
    # if they are pure numbers e.g. for year numbers
    s = str(s)

    # for some reason exiftool escapes some chars
    # in the sidecar's XML and thus in its json response
    # so we need to manually remove those \
    # we'll do this conservatively on an as-needed basis
    # to avoid issuses with chars that need escaping
    for char in ["$", "@"]:
        s = s.replace(f"\\{char}", char)

    # hex encoded chars like \xa0 (non breaking space)
    # get double escaped (\\xa0) in exiftool's response
    s_bytes = s.encode("utf-8")
    s_bytes_san = b""
    idx = 0
    while idx < len(s_bytes):
        # not an escape sequence
        if (seq := s_bytes[idx:idx+1]) != b"\\":
            s_bytes_san += seq
            idx += len(seq)
            continue

        # literal (escaped) \
        if (seq := s_bytes[idx:idx+2]) != b"\\x":
            s_bytes_san += seq
            idx += len(seq)
            continue

        # '\xa0'.encode("utf-8") -> b'\xc2\xa0'
        # this is basically the inverse
        seq = s_bytes[idx+2:idx+4]
        s_bytes_san += b"\xc2" + bytes.fromhex(seq.decode("utf-8"))
        idx += 4

    s = s_bytes_san.decode("utf-8")

    return s
