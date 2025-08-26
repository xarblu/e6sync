import json
import logging
import os
import requests
import subprocess
import time

from pathlib import Path
from requests.adapters import HTTPAdapter, Retry
from typing import Annotated
from typing import Any
from typing import Optional

from .util import date2path
from e6sync.api import E621Post, USER_AGENT

logger = logging.getLogger(__name__)


class AssetRepository:
    """
    Storage repository for the assets
    """

    # version history:
    # 0 - base version dumping everything in root
    # 1 - sort into directories by creation date YYYY/MM/DD
    latest_version: Annotated[int, "Latest library version"] = 1

    root: Annotated[Path, "Storage root"]
    metadata: Annotated[dict[str, Any], "Loaded content of library.json"]
    requests_session: Annotated[requests.Session, "Session for requests"]

    def __init__(self, root: Optional[Path]) -> None:
        """
        Constructor
        :param root  Storage root (Default ./library)
        """
        if root:
            self.root = root
        else:
            self.root = Path(os.getcwd()) / "library"

        # initialise library
        if not self.root.is_dir():
            logger.info(f"Creating library at {self.root}")
            os.mkdir(self.root)
            with open(self.root / "library.json", "w") as fp:
                json.dump({"version": AssetRepository.latest_version}, fp)

        if (f := self.root / "library.json").is_file():
            logger.info(f"Loading existing library data from {f}")
            with open(f, "r") as fp:
                self.metadata = json.load(fp)
        else:
            logger.warn(f"{f} missing - assuming version 0")
            self.metadata = {"version": 0}

        # check if we have exiftool here
        try:
            subprocess.run(["exiftool", "-ver"],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error("Could not find exiftool")
            raise RuntimeError("exiftool not found") from e

        # setup requests session with retries + backoff
        self.requests_session = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[500, 502, 503, 504])
        self.requests_session.mount("http://",
                                    HTTPAdapter(max_retries=retries))

        # perform migrations if needed
        if self.metadata["version"] < AssetRepository.latest_version:
            self.perform_migrations()

    def _fetch_post(self, url: str, dest: Path) -> None:
        """
        Fetch a post from url and store it in dest
        Will initially fetch to a temporary file that then gets moved
        :param url   URL to fetch from
        :param dest  Destination file
        """
        temp: Path = dest.with_suffix(dest.suffix + ".__part__")
        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        res = self.requests_session.get(url, headers=headers, stream=True)

        try:
            with open(temp, "wb") as fd:
                for chunk in res.iter_content(chunk_size=512):
                    fd.write(chunk)
            temp.rename(dest)
        finally:
            temp.unlink(missing_ok=True)

    def _write_metadata(self) -> None:
        """
        Write self.metadata to library.json
        """
        with open(self.root / "library.json", "w") as fp:
            json.dump(self.metadata, fp)

    def _write_sidecar(self, post: E621Post, sidecar: Path) -> None:
        """
        Write post metadata to an XMP Sidecar
        :param post     An E621Post object
        :param sidecar  XMP Sidecar file to write
        """
        argv: list[str] = ["exiftool"]

        argv += ["-DateTimeOriginal=" + post.created_at]

        # e6 splits tags into types, we'll just write them as is
        for _, tags in post.tags.items():
            for tag in tags:
                argv += ["-TagsList=" + tag]

        argv += ["-Description=" + post.description]

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

    def _read_sidecar(self, sidecar: Path) -> dict[str, str | list[str]]:
        """
        Read a XMP file
        :param sidecar  A XMP sidecar file
        :return json  exiftool -j output as dict
        """
        if not sidecar.is_file():
            raise FileNotFoundError(f"sidecar file {sidecar} does not exist")

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

        return json.loads(exif.stdout)[0]

    def update_post(self, post: E621Post) -> None:
        """
        Fetch a post if it isn't present and update
        its sidecar metadata
        :param post  An E621Post object
        """
        ext: str = os.path.splitext(post.file["url"])[1]

        # parse date, we only care about YYYY-MM-DD
        date = time.strptime(post.created_at[:10], "%Y-%m-%d")

        # library/YYYY/MM/DD/ID.EXT
        dest: Path = self.root / date2path(date) / str(str(post.id) + ext)

        # library/YYYY/MM/DD/ID.EXT.xmp
        sidecar: Path = dest.with_suffix(dest.suffix + ".xmp")

        # ensure the target dir exists here, all following methods expect it
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not dest.is_file():
            self._fetch_post(post.file["url"], dest)

        self._write_sidecar(post, sidecar)

    def _migration_0(self) -> None:
        """
        Migrate 0 -> 1
        For each file in root parse DateTimeOriginal from exif
        and sort into date directories
        """
        logger.info("Starting migration 0 -> 1")
        for path in self.root.iterdir():
            if path.name == "library.json":
                continue

            # don't migrate just xmp, always asset + xmp
            if path.suffix == ".xmp":
                continue

            # we have asset and its sidecar - this looks good
            if ((asset := path).is_file() and
               (sidecar := path.with_suffix(path.suffix + ".xmp")).is_file()):

                exif = self._read_sidecar(sidecar)

                if not isinstance(exif["DateTimeOriginal"], str):
                    raise TypeError("DateTimeOriginal should be str")

                # parse date, we only care about YYYY:MM:DD
                date = time.strptime(exif["DateTimeOriginal"][:10], "%Y:%m:%d")
                dest = self.root / date2path(date)

                dest.mkdir(parents=True, exist_ok=True)

                logger.debug(f"Moving {asset} to {dest}")
                asset.rename(dest / asset.name)
                sidecar.rename(dest / sidecar.name)

        logger.info("Migration 0 -> 1 succeeded")
        self.metadata["version"] = 1
        self._write_metadata()

    def perform_migrations(self) -> None:
        """
        Perform storage migrations to new directory structure
        """
        for migration in range(self.metadata["version"],
                               AssetRepository.latest_version):
            match migration:
                case 0:
                    self._migration_0()
                case _:
                    raise ValueError(f"Unknown migration {migration}")
