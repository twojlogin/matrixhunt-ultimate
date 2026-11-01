from typing import List
from .base import BaseScraper, Deal


class FreeToGameScraper(BaseScraper):
    """freetogame.com indexes free-to-play games. That is the entire site.

    A F2P title is not free-to-keep: you get a client, and the game lives
    behind a purchase, battle pass, gacha or energy timer. So this source
    cannot produce a valid offer for this project, and the 30 entries it
    returns every run were all rejected. Kept wired up, returns nothing.
    """

    def __init__(self, session=None):
        super().__init__("FreeToGame", "https://www.freetogame.com", session)

    async def scrape(self) -> List[Deal]:
        return []
