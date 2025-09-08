# SPDX-FileCopyrightText: 2025-present Xarblu <xarblu@protonmail.com>
#
# SPDX-License-Identifier: MIT
import logging

from argparse import ArgumentParser
from pathlib import Path
from tqdm import tqdm

from e6sync.__about__ import __version__
from e6sync.api import E621ApiClient
from e6sync.storage import AssetRepository

logger = logging.getLogger(__name__)


def e6sync() -> int:
    """
    CLI entry point
    """
    parser = ArgumentParser(
            description="Sync E621 posts to your "
                        f"local filesystem (Version {__version__})")

    parser.add_argument("--user",
                        required=True,
                        help="Username")
    parser.add_argument("--key",
                        required=True,
                        help="API Key")
    parser.add_argument("--log",
                        required=False,
                        default="INFO",
                        type=str.upper,
                        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"])
    parser.add_argument("--library",
                        type=Path,
                        required=False)
    parser.add_argument("--version",
                        action="version",
                        version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    logging.basicConfig(level=args.log)

    api = E621ApiClient(user=args.user, api_key=args.key)
    repo = AssetRepository(root=args.library)

    logger.info("Fetching post lists")
    favorites = api.favorites()

    logger.info("Starting download")
    for favorite in tqdm(favorites):
        repo.update_post(post=favorite)
    logger.info("Download finished")

    repo.log_stats()

    return 0
