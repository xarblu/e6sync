import time

from pathlib import Path


def date2path(date: time.struct_time) -> Path:
    """
    Convert a time.struct_time to a Path of form YYYY/MM/DD
    :param date  A date
    """
    return (Path(str(date.tm_year).rjust(4, "0"))
            / Path(str(date.tm_mon).rjust(2, "0"))
            / Path(str(date.tm_mday).rjust(2, "0")))
