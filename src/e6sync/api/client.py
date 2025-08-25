import logging
import requests
import time

from enum import Enum
from typing import Annotated
from typing import Any
from typing import Optional
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter, Retry

from e6sync.__about__ import __version__
from .types import E621Post, USER_AGENT

logger = logging.getLogger(__name__)


class HTTPMethod(Enum):
    """
    Enum for HTTP methods
    """
    GET = 1


class E621ApiClient:
    """
    API client class for E621
    """

    user: Annotated[str, "E621 user name"]
    api_key: Annotated[str, "E621 api key associated with user"]
    last_request: Annotated[float, "Monotonic clock time of last request"
                                   "used to enforce E6's "
                                   "1 request per second limit"]
    requests_session: Annotated[requests.Session, "Session for requests"]

    def __init__(self, user: str, api_key: str):
        """
        Constructor
        :param user     E621 user name
        :param api_key  E621 api key associated with user
        """
        self.user = user
        self.api_key = api_key
        self.last_request = time.monotonic()

        # setup requests session with retries + backoff
        self.requests_session = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[500, 502, 503, 504])
        self.requests_session.mount("http://",
                                    HTTPAdapter(max_retries=retries))

    def _request(self,
                 endpoint: str,
                 method: HTTPMethod = HTTPMethod.GET,
                 **kwargs
                 ) -> requests.Response:
        """
        Genric request method
        All requests should go through this to ensure
        proper auth, headers and respect E6's "1 request a second" rule
        :param endpoint  Endpoint where request should go
        :param method    HTTP Method used (Default GET)
        :param kwargs    Leftover keyword args passed to requests.METHOD
        """
        # ensure we don't send more than one request a second
        if (elapsed := time.monotonic() - self.last_request) < 1.0:
            time.sleep(1.0 - elapsed)
        self.last_request = time.monotonic()

        url = urljoin("https://e621.net/", endpoint.lstrip("/"))

        headers: dict[str, str] = {"User-Agent": USER_AGENT}

        auth = requests.auth.HTTPBasicAuth(self.user, self.api_key)

        match method:
            case HTTPMethod.GET:
                logger.debug(f"Sending GET {url}")
                return self.requests_session.get(url=url, headers=headers,
                                                 auth=auth, **kwargs)
            case _:
                raise NotImplementedError(f"HTTP method {method} "
                                          "is not implemented")

    def favorites(self, user: Optional[str] = None) -> list[E621Post]:
        """
        Grab a list of favorite posts
        Uses /posts.json with a fav:<user> tag search.
        /favorites.json is a thing but it acts kinda weird
        :param user  If set grab favorites of this user,
                     else of the user set in constructor
        """
        posts: list[E621Post] = []
        if user is None:
            user = self.user

        logger.info(f"Fetching favorite post list for {user}")
        logger.info("If there are a lot of posts this might take a while")

        # iterate over each page until now new posts appear
        while True:
            params: dict[str, str] = {}

            # always fetch max amount per page
            params["limit"] = "320"

            # if this isn't the initial fetch we have to
            # fetch a specific page
            if posts:
                params["page"] = "b" + str(posts[-1].id)

            # search query and ensure proper ordering
            params["tags"] = f"fav:{user} order:id_desc"

            if "page" not in params:
                logger.debug("Fetching inital page")
            else:
                logger.debug(f"Fetching page {params['page']}")

            batch: list[dict[str, Any]] = self._request(
                    "/posts.json",
                    params=params
                    ).json()["posts"]

            if batch:
                logger.debug(f"Got batch with {len(batch)} posts")
                posts += [E621Post(**x) for x in batch]
            else:
                logger.debug("Got empty batch - done")
                break

            # XXX: just for dev break after first
            break

        logger.info(f"Fetched a total of {len(posts)} posts")

        return posts
