from typing import List
import asyncio
from .base import BaseScraper, Deal


def _appid(url: str):
    """Pull the numeric appid out of /app/<id>/ or /app/<id>/<slug>/."""
    parts = [p for p in url.split("/") if p]
    if "app" in parts:
        i = parts.index("app")
        if i + 1 < len(parts) and parts[i + 1].isdigit():
            return parts[i + 1]
    return None


class SteamScraper(BaseScraper):
    def __init__(self, session=None):
        super().__init__("Steam", "https://store.steampowered.com", session)

    async def _details(self, appid):
        """Steam's own answer about this app: real price, and whether it is a
        game at all. The search page's maxprice=free is a hint, not a promise —
        it also returns demos and DLC, and sometimes items that are not free."""
        api = (f"{self.base_url}/api/appdetails?appids={appid}"
               "&filters=basic,price_overview")
        async with self.session.get(api, headers=self.headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        node = data.get(appid) or {}
        if not node.get("success"):
            return None
        return node.get("data") or {}

    async def scrape(self) -> List[Deal]:
        deals = []
        try:
            url = f"{self.base_url}/search/?specials=1&maxprice=free&ignore_preferences=1&ndl=1"
            async with self.session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    from bs4 import BeautifulSoup
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    kandydaci = []
                    for row in soup.select("a.search_result_row")[:20]:
                        title_el = row.select_one(".title")
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        if self.is_garbage(title):
                            continue
                        kandydaci.append((self.clean_title(title),
                                          row.get("href", "").split("?")[0]))

                    # Ask Steam about each candidate instead of assuming. Six
                    # concurrent, not twenty-four sequential.
                    sem = asyncio.Semaphore(6)
                    async def one(title, href):
                        async with sem:
                            appid = _appid(href)
                            d = await self._details(appid) if appid else None
                            if not d:
                                return None
                            if d.get("type") != "game":
                                return None  # DLC, demo, mod — not a game offer
                            if d.get("is_free") is not True:
                                return None  # search filters are not proof of F2P
                            po = d.get("price_overview") or {}
                            claim = po.get("final_formatted") or "Free"
                            return Deal(
                                title=title,
                                url=href,
                                price=claim,
                                price_claim=claim,
                                price_source="api:steam",
                                original_price=po.get("initial_formatted", ""),
                                category="games",
                                source="Steam",
                                requires_login=True,
                            )
                    wyniki = await asyncio.gather(*(one(t, h) for t, h in kandydaci))
                    deals = [d for d in wyniki if d]
        except Exception as e:
            print(f"[Steam] Error: {e}")
        return [d for d in deals if self.is_valid(d)]
