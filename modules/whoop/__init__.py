"""WHOOP API Integration Module"""

from .module import WhoopAPI, get_whoop_client
from .recommendations import WhoopRecommendations

__all__ = ["WhoopAPI", "get_whoop_client", "WhoopRecommendations"]
