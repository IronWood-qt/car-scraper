"""
Car scraper package for otomoto.pl.

A car listing scraper with comprehensive features:
- Individual listing price tracking over time
- Advanced data analysis and visualization
- Multiple export formats and storage options
- Professional logging and error handling
- Modular architecture following Python best practices
"""

__version__ = "0.1.0"
__author__ = "Szymon Piskorz"
__email__ = "sim.piskorz@gmail.com"

# Main exports
from src.car_scraper.config import Config
from src.car_scraper.models import (
    CarListing,
    CarListingHistory,
    ScrapingResults,
    YearAnalysisData,
)
from src.car_scraper.scrapers import CarScraper
from src.car_scraper.storage import SimplifiedListingsStorage
from src.car_scraper.utils import DataProcessor

__all__ = [
    # Core classes
    "Config",
    "CarScraper",
    # Data models
    "CarListing",
    "CarListingHistory",
    "ScrapingResults",
    "YearAnalysisData",
    # Storage
    "SimplifiedListingsStorage",
    # Utilities
    "DataProcessor",
]
