import os
import time

from pathlib import Path

from e6sync.api import E621Post


def date2path(date: time.struct_time) -> Path:
    """
    Convert a time.struct_time to a Path of form YYYY/MM/DD
    :param date  A date
    """
    return (Path(str(date.tm_year).rjust(4, "0"))
            / Path(str(date.tm_mon).rjust(2, "0"))
            / Path(str(date.tm_mday).rjust(2, "0")))


def file_mtime(file: Path) -> int:
    """
    Get modification time of a file in unix epoch seconds
    """
    if not file.is_file():
        raise FileNotFoundError(f"{file} does not exist")

    # XXX: not sure if this is actually unix seconds...
    stat = os.stat(file)

    return int(stat.st_mtime)


def post_mtime(post: E621Post) -> int:
    """
    Get modification time of a post in unix epoch seconds
    """
    parsed = time.strptime(post.updated_at, "%Y-%m-%dT%H:%M:%S.%f%z")

    # XXX: not sure if this is actually unix seconds...
    return int(time.mktime(parsed))
