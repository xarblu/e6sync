from __future__ import annotations

import json
import logging
import subprocess

from concurrent.futures import ProcessPoolExecutor, Future
from pathlib import Path
from typing import Annotated
from typing import Optional
from dataclasses import dataclass
from time import struct_time, strftime, strptime

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
    Class to manage XMP sidecar files concurrently
    """

    executor: Annotated[ProcessPoolExecutor, "Executor for exiftool calls"]
    updates: Annotated[list[Future[None]], "Pending update operations"]

    def __init__(self):
        """
        Constructor
        """
        # check if we have exiftool here
        try:
            subprocess.run(["exiftool", "-ver"],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error("Could not find exiftool")
            raise RuntimeError("exiftool not found") from e

        # for now always use 4 workers which should be enough
        # TODO: maybe make this user configurable
        self.executor = ProcessPoolExecutor(max_workers=4)
        self.updates = []

    def __del__(self):
        """
        Desctructor
        """
        self.executor.shutdown(wait=True)

    @staticmethod
    def _read_sidecar(sidecar: Path) -> ExifData:
        """
        Read a XMP file, sync version
        :param sidecar  A XMP sidecar file
        :return json  exiftool -j output as ExifData
        """
        if not sidecar.is_file():
            return ExifData()

        argv: list[str] = ["exiftool", "-j", str(sidecar)]

        logger.debug("Invoking " + " ".join(argv))
        try:
            exif = subprocess.run(argv, check=True,
                                  capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error("exiftool failed:\n"
                         f"stdout: {e.stdout}\n"
                         f"stderr: {e.stderr}\n")
            raise RuntimeError("exiftool failure") from e

        return ExifData.fromExiftool(json.loads(exif.stdout)[0])

    @staticmethod
    def _update_sidecar(post: E621Post, sidecar: Path) -> None:
        """
        Write post metadata to an XMP Sidecar, sync version
        :param post     An E621Post object
        :param sidecar  XMP Sidecar file to write
        """
        current_exif: ExifData = SidecarManager._read_sidecar(sidecar)
        new_exif: ExifData = ExifData.fromPost(post)

        logger.debug(f"Current: {current_exif}")
        logger.debug(f"New: {new_exif}")

        # speedup: skip if there is no changed info
        if current_exif == new_exif:
            logger.debug(f"Skipped sidecar: {sidecar} - already up-to-date")
            return

        logger.debug(f"Creating/Updating sidecar: {sidecar}")

        argv: list[str] = ["exiftool"]

        # exif options
        argv += new_exif.asExiftoolArgs()

        # file options
        argv += ["-overwrite_original", str(sidecar)]

        logger.debug("Invoking " + " ".join(argv))
        try:
            subprocess.run(argv, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error("exiftool failed:\n"
                         f"stdout: {e.stdout}\n"
                         f"stderr: {e.stderr}\n")
            raise RuntimeError("exiftool failure") from e

    def read_sidecar(self, sidecar: Path) -> ExifData:
        """
        Read a XMP file, async version
        :param sidecar  A XMP sidecar file
        :return json  exiftool -j output as dict
        """
        return self.executor.submit(
                SidecarManager._read_sidecar,
                sidecar
                ).result()

    def update_sidecar(self, post: E621Post, sidecar: Path) -> None:
        """
        Write post metadata to an XMP Sidecar, async version
        :param post     An E621Post object
        :param sidecar  XMP Sidecar file to write
        """
        self.updates.append(
                self.executor.submit(
                    SidecarManager._update_sidecar,
                    post, sidecar))
