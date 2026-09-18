from abc import ABC, abstractmethod
from typing import Optional
from core.models import MatchData
from core.browser_manager import BrowserManager

class BaseScraper(ABC):
    """
    Abstract Base Class for website-specific cricket match scrapers.
    All scrapers implement fetch_and_parse(browser_mgr) returning standard MatchData.
    """
    def __init__(self, match_url: str):
        self.raw_url = match_url
        self.match_id = self.extract_match_id(match_url)

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Returns the name of the cricket statistics website (e.g. 'CricketWorld')"""
        pass

    @abstractmethod
    def extract_match_id(self, url: str) -> str:
        """Extracts unique match ID from the given URL"""
        pass

    @abstractmethod
    async def fetch_and_parse(self, browser_mgr: BrowserManager) -> MatchData:
        """
        Loads the required web pages for the match, renders JavaScript DOM,
        and parses everything into a standardized MatchData object.
        """
        pass
