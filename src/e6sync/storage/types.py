from dataclasses import dataclass
from typing import Annotated
from enum import Enum


@dataclass
class StatCounter:
    """
    Repository stat counter
    """

    processed: Annotated[int, "Total processed assets"] = 0
    updated: Annotated[int, "Updated assets"] = 0
    new: Annotated[int, "New assets"] = 0


class AssetChange(Enum):
    """
    Asset change status
    """
    UNCHANGED = 0
    UPDATED = 1
    NEW = 2
