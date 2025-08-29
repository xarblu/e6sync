from __future__ import annotations

import json
import logging

from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen, PIPE, DEVNULL
from time import struct_time, strftime, strptime
from typing import Annotated
from typing import Any
from typing import Optional

from e6sync.api import E621Post

logger = logging.getLogger(__name__)


@dataclass
class ExifData:
    """
    Class for exif data we manage
    """

    # exif tags
    DateTimeOriginal: Annotated[Optional[struct_time],
                                "post created_at"] = None
    Description: Annotated[Optional[str], "post description"] = None
    TagsList: Annotated[Optional[list[str]], "post flattened tags"] = None

    @staticmethod
    def fromPost(post: E621Post) -> ExifData:
        """
        Parse E621 post to ExifData
        """
        DateTimeOriginal = strptime(post.created_at, "%Y-%m-%dT%H:%M:%S.%f%z")

        Description = None
        if (val := post.description) != "":
            Description = val

        TagsList = []

        # e6 splits tags into types, we'll just write them as is
        for _, tags in post.tags.items():
            for tag in tags:
                TagsList.append(tag)

        return ExifData(
                DateTimeOriginal=DateTimeOriginal,
                Description=Description,
                TagsList=TagsList)

    @staticmethod
    def fromExiftool(post: dict[str, str | list[str]]) -> ExifData:
        """
        Parse exiftool json ouput to ExifData
        """
        DateTimeOriginal = None
        if isinstance(val := post.get("DateTimeOriginal"), str):
            # apparently this can have multiple formats
            for fmt in ["%Y:%m:%d %H:%M:%S.%f%z", "%Y:%m:%d %H:%M:%S"]:
                try:
                    DateTimeOriginal = strptime(val, fmt)
                    break
                except ValueError:
                    pass
            else:
                raise ValueError(f"Could not parse DateTimeOriginal: {val}")

        Description = None
        if isinstance(val := post.get("Description"), str):
            Description = val

        TagsList = []
        if isinstance(val := post.get("TagsList"), list):
            TagsList = val

        return ExifData(
                DateTimeOriginal=DateTimeOriginal,
                Description=Description,
                TagsList=TagsList)

    def asExiftoolArgs(self) -> list[str]:
        """
        Create a list of exiftool args representing this ExifData
        """
        args: list[str] = []

        if self.DateTimeOriginal is not None:
            args += ["-DateTimeOriginal=" + strftime("%Y:%m:%d %H:%M:%S.%f%z",
                                                     self.DateTimeOriginal)]

        if self.Description is not None:
            args += ["-Description=" + self.Description]

        if self.TagsList is not None:
            args += ["-TagsList=" + tag for tag in self.TagsList]

        return args


class SidecarManager:
    """
    Class to manage XMP sidecar files with exiftool
    """

    exiftool: Annotated[Popen, "exiftool process"]

    def __init__(self) -> None:
        """
        Constructor
        """
        self.exiftool = Popen(["exiftool",
                               "-stay_open", "True",
                               "-@", "-"],
                              stdin=PIPE,
                              stdout=PIPE,
                              stderr=DEVNULL)

    def __del__(self) -> None:
        """
        Desctructor
        """
        # let exiftool finish (with 30s timeout), then kill it
        if (stdin := self.exiftool.stdin) is not None:
            stdin.write("-stay_open\nFalse\n".encode("utf-8"))
            stdin.flush()
        else:
            logger.error("exiftool stdin is bad")

        try:
            self.exiftool.wait(30)
        except TimeoutError:
            self.exiftool.kill()

    def _exiftoolSubmit(self, args: list[str]) -> Any:
        """
        Submit args to exiftool,
        """

        logger.debug("exiftool call: {args}")

        if (stdin := self.exiftool.stdin) is not None:
            for arg in args + ["-j", "-execute"]:
                # exiftool -@ ARGFILE:
                # for lines beginning with "#[CSTR]" the
                # rest of the line is treated as a C string
                # allowing standard C escape sequences such as "\n"
                #
                # without this newlines stay escaped e.g. in Description
                arg_enc = ("#[CSTR]".encode("utf-8")
                           + arg.encode("unicode_escape")
                           + b"\n")
                stdin.write(arg_enc)
            stdin.flush()
        else:
            logger.error("exiftool stdin is bad")

        if (stdout := self.exiftool.stdout) is not None:
            # read until '\n{ready}'
            # not sure if there's a better way...
            # most read operations block indefinetly
            # because technically EOF is never reached
            response: bytes = b""
            while True:
                response += stdout.read(1)
                if response[-8:] == b"\n{ready}":
                    break

            response = response[:-8]

            logger.debug(f"exiftool response: {response.decode()}")

            if response:
                return json.loads(response)
            else:
                return None
        else:
            logger.error("exiftool stdout is bad")

    def read_sidecar(self, sidecar: Path) -> ExifData:
        """
        Read a XMP file
        :param sidecar  A XMP sidecar file
        :return json  exiftool -j output as ExifData
        """
        if not sidecar.is_file():
            return ExifData()

        args: list[str] = [str(sidecar)]

        return ExifData.fromExiftool(self._exiftoolSubmit(args)[0])

    def update_sidecar(self, post: E621Post, sidecar: Path) -> None:
        """
        Write post metadata to an XMP Sidecar
        :param post     An E621Post object
        :param sidecar  XMP Sidecar file to write
        """
        current_exif: ExifData = self.read_sidecar(sidecar)
        new_exif: ExifData = ExifData.fromPost(post)

        logger.debug(f"Current: {current_exif}")
        logger.debug(f"New: {new_exif}")

        # speedup: skip if there is no changed info
        if current_exif == new_exif:
            logger.debug(f"Skipped sidecar: {sidecar} - already up-to-date")
            return

        logger.debug(f"Creating/Updating sidecar: {sidecar}")

        args: list[str] = []

        # exif options
        args += new_exif.asExiftoolArgs()

        # file options
        args += ["-overwrite_original", str(sidecar)]

        self._exiftoolSubmit(args)
