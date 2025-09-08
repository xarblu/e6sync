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
    # exiftool decides to encode items as int in their json response
    # if they are pure numbers e.g. for year numbers
    s = str(s)

    # for some reason exiftool escapes some chars
    # in the sidecar's XML and thus in its json response
    # so we need to manually remove those \
    # we'll do this conservatively on an as-needed basis
    # to avoid issuses with chars that need escaping
    for char in ["@"]:
        s = s.replace(f"\\{char}", char)

    return s
