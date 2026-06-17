import asyncio
import random
from datetime import datetime

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .schema import Place
from .browser import random_delay, human_scroll, check_captcha


def parse_place_id(url: str) -> str | None:
    if "1s0x" in url:
        try:
            return url.split("1s")[1].split("!")[0]
        except Exception:
            pass
    try:
        return url.split("/maps/place/")[1].split("/")[0]
    except Exception:
        return None


async def parse_coordinates(page: Page, place_id: str | None) -> tuple[float | None, float | None]:
    # try extracting from URL
    for _ in range(8):
        url = page.url
        if "@" in url and "," in url.split("@")[1]:
            try:
                parts = url.split("@")[1].split(",")
                lat, lng = float(parts[0]), float(parts[1])
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
            except Exception:
                pass
        await asyncio.sleep(0.4)

    # try decoding from place_id hex
    if place_id and ":" in place_id:
        try:
            hex_lat, hex_lng = place_id.split(":")[:2]
            lat_int = int(hex_lat, 16)
            lng_int = int(hex_lng, 16)
            if lat_int >= 2**31:
                lat_int -= 2**32
            if lng_int >= 2**31:
                lng_int -= 2**32
            return round(lat_int * 1e-7, 6), round(lng_int * 1e-7, 6)
        except Exception:
            pass

    # try meta tags
    try:
        meta_lat = await page.query_selector('meta[itemprop="latitude"]')
        meta_lng = await page.query_selector('meta[itemprop="longitude"]')
        if meta_lat and meta_lng:
            lat = float(await meta_lat.get_attribute("content"))
            lng = float(await meta_lng.get_attribute("content"))
            return lat, lng
    except Exception:
        pass

    return None, None


async def parse_price_histogram(page: Page) -> dict:
    result = {
        "is_price_reviewed": False,
        "price_summary": None,
        "price_voter_count": None,
        "price_rp1_25k_count": None,
        "price_rp25_50k_count": None,
        "price_rp50_75k_count": None,
        "price_rp75_100k_count": None,
        "price_rp100k_plus_count": None,
    }

    price_table = await page.query_selector('table.rqRH4d[aria-label*="Histogram rentang harga"]')
    if not price_table:
        price_table = await page.query_selector('table[aria-label*="harga"]')
    if not price_table:
        return result

    try:
        result["is_price_reviewed"] = True

        price_header = await page.query_selector("div.MNVeJb")
        if price_header:
            voter_el = await price_header.query_selector("div.BfVpR")
            if voter_el:
                raw_voter = (await voter_el.inner_text()).strip()
                try:
                    result["price_voter_count"] = int("".join(filter(str.isdigit, raw_voter)))
                except Exception:
                    pass
                full_text = (await price_header.inner_text()).strip()
                voter_text = (await voter_el.inner_text()).strip()
                result["price_summary"] = full_text.replace(voter_text, "").strip().replace("\xa0", " ")

        rows = await price_table.query_selector_all("tr")
        for row in rows:
            label_el = await row.query_selector("td.fsAi0e")
            bar_el = await row.query_selector("span.QANbtc")
            if not label_el or not bar_el:
                continue
            label = (await label_el.inner_text()).strip().replace("\xa0", "").replace(".", "").replace(" ", "")
            pct_str = await bar_el.get_attribute("aria-label")
            try:
                pct = float(pct_str.replace("%", "").strip()) / 100.0
            except Exception:
                pct = 0.0
            count = round(pct * result["price_voter_count"]) if result["price_voter_count"] else None

            if "1" in label and "25" in label:
                result["price_rp1_25k_count"] = count
            elif "25" in label and "50" in label:
                result["price_rp25_50k_count"] = count
            elif "50" in label and "75" in label:
                result["price_rp50_75k_count"] = count
            elif "75" in label and "100" in label:
                result["price_rp75_100k_count"] = count
            elif "100" in label:
                result["price_rp100k_plus_count"] = count
    except Exception:
        pass

    return result


async def search_cell(
    page: Page,
    lat: float,
    lng: float,
    keyword: str,
    seen_fn=None,
    headed: bool = False,
    worker_id: int = 0,
) -> list[str]:
    """Navigate to Maps search, scroll feed, return list of place detail hrefs."""
    query = keyword.replace(" ", "+")
    url = f"https://www.google.com/maps/search/{query}/@{lat},{lng},17z/data=!3m1!4b1"
    hrefs = []

    try:
        await page.goto(url, timeout=30000)
        if await check_captcha(page, headed, worker_id):
            return []
        await random_delay(2.0, 3.5)

        # click "search this area" if visible
        try:
            btn = await page.query_selector('button[class*="search-this-area"]')
            if btn:
                await btn.click()
                await random_delay(1.5, 2.5)
        except Exception:
            pass

        try:
            await page.wait_for_selector('div[role="feed"]', timeout=8000)
        except PlaywrightTimeout:
            return []

        await human_scroll(page, 'div[role="feed"]')

        cards = await page.query_selector_all('a[href*="/maps/place/"]')
        seen = set()
        for card in cards:
            href = await card.get_attribute("href")
            if href and "/maps/place/" in href and href not in seen:
                seen.add(href)
                pid = parse_place_id(href)
                if pid and seen_fn and seen_fn(pid):
                    continue
                hrefs.append(href)

    except Exception as e:
        print(f"  [search error] {keyword} @ {lat},{lng}: {e}")

    return hrefs


async def extract_place(
    page: Page,
    href: str,
    filter_address: str | None = None,
    headed: bool = False,
    worker_id: int = 0,
) -> Place | None:
    """Navigate to a place detail page and extract all fields."""
    try:
        if not href.startswith("http"):
            href = "https://www.google.com" + href

        await page.goto(href, timeout=30000)
        if await check_captcha(page, headed, worker_id):
            return None
        await random_delay(1.5, 2.5)

        url = page.url
        place_id = parse_place_id(url)
        if not place_id:
            return None

        name_el = await page.query_selector("h1.DUwDvf")
        name = (await name_el.inner_text()).strip() if name_el else ""

        address = ""
        addr_el = await page.query_selector('button[data-item-id="address"] div.Io6YTe')
        if addr_el:
            address = (await addr_el.inner_text()).strip()

        # skip places outside the target area if filter is set
        if filter_address and address and filter_address.lower() not in address.lower():
            return None

        lat, lng = await parse_coordinates(page, place_id)

        rating = None
        rating_el = await page.query_selector('div.F7nice span[aria-hidden="true"]')
        if rating_el:
            try:
                rating = float((await rating_el.inner_text()).replace(",", ".").strip())
            except Exception:
                pass

        total_reviews = None
        reviews_el = await page.query_selector('div.F7nice span[aria-label*="ulasan"]')
        if not reviews_el:
            reviews_el = await page.query_selector('div.F7nice span[aria-label*="review"]')
        if reviews_el:
            try:
                raw = await reviews_el.inner_text()
                total_reviews = int(raw.strip().replace("(", "").replace(")", "").replace(".", "").replace(",", ""))
            except Exception:
                pass

        tags_list = []
        tag_els = await page.query_selector_all("button.DkEaL")
        for el in tag_els:
            t = (await el.inner_text()).strip()
            if t:
                tags_list.append(t)
        tags = "|".join(tags_list)

        website = ""
        web_el = await page.query_selector('a[data-item-id="authority"]')
        if web_el:
            website = (await web_el.get_attribute("href") or "").strip()

        permanently_closed = False
        closed_el = await page.query_selector("div.e2moi")
        if closed_el:
            closed_text = (await closed_el.inner_text()).lower()
            if "permanen" in closed_text or "permanently" in closed_text:
                permanently_closed = True

        hours = ""
        hours_el = await page.query_selector("div.OMl5r.hH0dDd.jBYmhd")
        if not hours_el:
            hours_el = await page.query_selector('div[jsaction*="openhours"]')
        if hours_el:
            try:
                await hours_el.click()
                await asyncio.sleep(1.0)
                table_rows = await page.query_selector_all("table.eK4R0e tr, table.rqRH4d tr")
                if not table_rows:
                    table_rows = await page.query_selector_all("tr[class]")
                parts = []
                for row in table_rows:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 2:
                        day = (await cells[0].inner_text()).strip()
                        time = (await cells[1].inner_text()).strip().replace("\n", " ")
                        if day and time:
                            parts.append(f"{day} {time}")
                hours = "|".join(parts)
            except Exception:
                pass

        price_level_google = ""
        price_el = await page.query_selector("span.mgr77e")
        if price_el:
            price_level_google = (await price_el.inner_text()).strip().lstrip("·").strip()

        price_data = await parse_price_histogram(page)

        return Place(
            place_id=place_id,
            name=name,
            lat=lat,
            lng=lng,
            rating=rating,
            total_reviews=total_reviews,
            tags=tags,
            address=address,
            website=website,
            permanently_closed=permanently_closed,
            hours=hours,
            price_level_google=price_level_google,
            scraped_at=Place.stamp(),
            scraped_reviews=False,
            **price_data,
        )

    except Exception as e:
        print(f"  [detail error] {href}: {e}")
        return None
