from dataclasses import dataclass
from typing import Optional

from e6sync.__about__ import __version__

USER_AGENT = f"e6sync/{__version__} (by xarblu on e621)"

@dataclass(frozen=True)
class E621Post:
    """
    An e621 post object as returned by /posts.json
    https://e621.net/wiki_pages/2425#posts_list
    """
    id: int
    created_at: str
    updated_at: str
    file: dict
    preview: dict
    sample: dict
    score: dict
    tags: dict
    locked_tags: dict
    change_seq: dict
    flags: dict
    rating: str
    fav_count: int
    sources: dict
    pools: dict
    relationships: dict
    description: str
    comment_count: int
    is_favorited: bool
    has_notes: bool
    approver_id: Optional[int] = None
    uploader_id: Optional[int] = None
    duration: Optional[float] = None
