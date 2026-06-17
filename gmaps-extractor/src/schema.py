from dataclasses import dataclass, fields, asdict
from datetime import datetime


FIELDNAMES = [
    "place_id", "name", "lat", "lng", "rating", "total_reviews", "tags",
    "address", "website", "permanently_closed", "hours", "price_level_google",
    "is_price_reviewed", "price_summary", "price_voter_count",
    "price_rp1_25k_count", "price_rp25_50k_count", "price_rp50_75k_count",
    "price_rp75_100k_count", "price_rp100k_plus_count",
    "scraped_at", "scraped_reviews",
    "source_cell_id", "search_keyword",
]


@dataclass
class Place:
    place_id: str
    name: str = ""
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    total_reviews: int | None = None
    tags: str = ""
    address: str = ""
    website: str = ""
    permanently_closed: bool = False
    hours: str = ""
    price_level_google: str = ""
    is_price_reviewed: bool = False
    price_summary: str | None = None
    price_voter_count: int | None = None
    price_rp1_25k_count: int | None = None
    price_rp25_50k_count: int | None = None
    price_rp50_75k_count: int | None = None
    price_rp75_100k_count: int | None = None
    price_rp100k_plus_count: int | None = None
    scraped_at: str = ""
    scraped_reviews: bool = False
    source_cell_id: str | None = None
    search_keyword: str | None = None

    def to_row(self) -> dict:
        return asdict(self)

    @staticmethod
    def stamp() -> str:
        return datetime.now().isoformat()
