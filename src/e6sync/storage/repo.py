import os
import logging
import requests
import subprocess

from typing import Annotated
from typing import Optional
from pathlib import Path
from requests.adapters import HTTPAdapter, Retry

from e6sync.api import E621Post, USER_AGENT

logger = logging.getLogger(__name__)


class AssetRepository:
    """
    Storage repository for the assets
    """

    root: Annotated[Path, "Storage root"]
    has_exiftool: Annotated[bool, "Whether exiftool is present"]
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

        if not self.root.is_dir():
            logger.info(f"Creating asset repository at {self.root}")
            os.mkdir(self.root)

        # check if we have exiftool here
        self.has_exiftool = True
        try:
            subprocess.run(["exiftool", "-ver"],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.warn("Could not find exiftool"
                        "- won't create XMP sidecars")
            self.has_exiftool = False

        # setup requests session with retries + backoff
        self.requests_session = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[500, 502, 503, 504])
        self.requests_session.mount("http://",
                                    HTTPAdapter(max_retries=retries))


    def _fetch_post(self, url: str, dest: Path) -> None:
        """
        Fetch a post from url and store it in dest
        Will initially fetch to a temporary file that then gets moved
        :param url   URL to fetch from
        :param dest  Destination file
        """
        temp: Path = dest.with_suffix(dest.suffix + ".__download__")
        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        res = self.requests_session.get(url, headers=headers, stream=True)

        try:
            with open(temp, "wb") as fd:
                for chunk in res.iter_content(chunk_size=512):
                    fd.write(chunk)
            os.rename(temp, dest)
        finally:
            if temp.is_file():
                os.remove(temp)

    def _tag_exif(self, post: E621Post, sidecar: Path) -> None:
        """
        Write post metadata to an XMP Sidecar
        :param post     An E621Post object
        :param sidecar  XMP Sidecar file to write
        """
        if not self.has_exiftool:
            return

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
            logger.error("exiftoool failed:\n"
                         f"stdout: {e.stdout}\n"
                         f"stderr: {e.stderr}\n")

    def update_post(self, post: E621Post) -> None:
        """
        Fetch a post if it isn't present and update
        its sidecar metadata
        :param post  An E621Post object
        """
        ext: str = os.path.splitext(post.file["url"])[1]
        dest: Path = self.root / str(str(post.id) + ext)
        sidecar: Path = dest.with_suffix(dest.suffix + ".xmp")

        if not dest.is_file():
            self._fetch_post(post.file["url"], dest)

        self._tag_exif(post, sidecar)
