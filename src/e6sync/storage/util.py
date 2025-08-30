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
