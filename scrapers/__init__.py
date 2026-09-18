import urllib.parse
from typing import Dict, Type, List
from core.base_scraper import BaseScraper

_SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {}

def register_scraper(domains: List[str]):
    """Decorator to register a scraper class for one or more domains"""
    def decorator(cls: Type[BaseScraper]):
        for domain in domains:
            _SCRAPER_REGISTRY[domain.lower()] = cls
        return cls
    return decorator

def get_scraper_for_url(url: str) -> BaseScraper:
    """
    Parses URL domain and returns an instantiated Scraper from the registry.
    Raises ValueError if no matching scraper is found.
    """
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    
    # Check exact match or suffix match (e.g. www.cricketworld.com -> cricketworld.com)
    for domain, scraper_cls in _SCRAPER_REGISTRY.items():
        if netloc == domain or netloc.endswith("." + domain):
            return scraper_cls(url)
            
    supported = list(_SCRAPER_REGISTRY.keys())
    raise ValueError(f"No scraper registered for domain '{netloc}'. Supported platforms: {supported}")

# Auto-import scrapers to populate registry
from scrapers.cricketworld import CricketWorldScraper
from scrapers.cricinfo import CricinfoScraper
from scrapers.cricbuzz import CricbuzzScraper
from scrapers.crex import CrexScraper
from scrapers.template_scraper import TemplateCricketScraper
