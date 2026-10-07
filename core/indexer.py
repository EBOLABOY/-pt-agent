import re
import logging
import urllib.parse
import httpx
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger("pt_agent.indexer")

class PTIndexer:
    """Ultra-lightweight PT search indexer for NexusPHP and public trackers"""
    def __init__(self, sites_config: List[Any]):
        self.sites = [s for s in sites_config if getattr(s, "enabled", True)]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

    async def _search_nexusphp(self, site, keyword: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        results = []
        base_url = site.base_url.rstrip("/")
        encoded_kw = urllib.parse.quote(keyword)
        search_url = f"{base_url}/torrents.php?search={encoded_kw}&notnewword=1"

        headers = dict(self.headers)
        if site.cookie:
            headers["Cookie"] = site.cookie

        try:
            resp = await client.get(search_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Search {site.name} failed with status {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            torrents_table = soup.find("table", class_="torrents")
            if not torrents_table:
                # Some sites use table without class 'torrents'
                tables = soup.find_all("table")
                for t in tables:
                    if t.find("a", href=re.compile(r"details\.php\?id=\d+")):
                        torrents_table = t
                        break

            if not torrents_table:
                return []

            rows = torrents_table.find_all("tr")
            for row in rows:
                detail_link = row.find("a", href=re.compile(r"details\.php\?id=\d+"))
                if not detail_link:
                    continue

                href = detail_link.get("href", "")
                m = re.search(r"id=(\d+)", href)
                if not m:
                    continue
                torrent_id = m.group(1)

                # Title
                title = detail_link.get("title") or detail_link.get_text().strip()

                # Subtitle
                subtitle = ""
                sub_span = detail_link.find_next_sibling()
                if sub_span:
                    subtitle = sub_span.get_text().strip()
                elif detail_link.parent:
                    # often second line in parent
                    all_text = detail_link.parent.get_text().strip()
                    subtitle = all_text.replace(title, "").strip()

                # Details URL
                details_url = f"{base_url}/{href.lstrip('/')}"

                # Download URL
                dl_link = row.find("a", href=re.compile(r"download\.php\?id=\d+"))
                if dl_link:
                    dl_href = dl_link.get("href", "")
                    download_url = f"{base_url}/{dl_href.lstrip('/')}"
                elif site.passkey:
                    download_url = f"{base_url}/download.php?id={torrent_id}&passkey={site.passkey}"
                else:
                    download_url = f"{base_url}/download.php?id={torrent_id}"

                # Promotion (Free / 2xFree / 50%)
                promo = "NORMAL"
                if row.find(class_=re.compile(r"free2up|2xfree", re.I)):
                    promo = "2XFREE"
                elif row.find(class_=re.compile(r"pro_free|free", re.I)):
                    promo = "FREE"
                elif row.find(class_=re.compile(r"pro_50|50", re.I)):
                    promo = "50%"

                # Text in row to find size, seeders, leechers
                cells = row.find_all(["td", "th"])
                size_str = "0 MB"
                seeders = 0
                leechers = 0

                # Search cells for size and seeders
                for idx, cell in enumerate(cells):
                    cell_text = cell.get_text().strip()
                    # Check size format
                    if re.match(r'^[\d.]+\s*(?:[KMGTPE]?B|Bytes)$', cell_text, re.I):
                        size_str = cell_text
                    # Check seeders
                    seed_link = cell.find("a", href=re.compile(r"viewsnatches|toseeders", re.I))
                    if seed_link:
                        try:
                            seeders = int(re.sub(r'\D', '', seed_link.get_text()) or 0)
                        except ValueError:
                            pass

                results.append({
                    "site": site.name,
                    "domain": site.domain,
                    "torrent_id": torrent_id,
                    "title": title,
                    "subtitle": subtitle,
                    "size": size_str,
                    "seeders": seeders,
                    "leechers": leechers,
                    "promo": promo,
                    "download_url": download_url,
                    "details_url": details_url
                })

        except Exception as e:
            logger.error(f"Error searching {site.name}: {e}")

        return results

    async def _search_nyaa(self, keyword: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        results = []
        try:
            url = f"https://nyaa.si/?f=0&c=0_0&q={urllib.parse.quote(keyword)}"
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.find_all("tr", class_=re.compile(r"default|success|danger"))
                for row in rows:
                    title_link = row.find("a", href=re.compile(r"^/view/\d+"))
                    dl_link = row.find("a", href=re.compile(r"^/download/\d+\.torrent"))
                    if title_link and dl_link:
                        title = title_link.get_text().strip()
                        dl_url = f"https://nyaa.si{dl_link.get('href')}"
                        details = f"https://nyaa.si{title_link.get('href')}"
                        cells = row.find_all("td")
                        size_str = cells[3].get_text().strip() if len(cells) > 3 else "0 MB"
                        seeders = int(cells[5].get_text().strip()) if len(cells) > 5 and cells[5].get_text().strip().isdigit() else 0
                        results.append({
                            "site": "Nyaa",
                            "domain": "nyaa.si",
                            "torrent_id": re.search(r'\d+', dl_url).group(0),
                            "title": title,
                            "subtitle": "",
                            "size": size_str,
                            "seeders": seeders,
                            "leechers": 0,
                            "promo": "FREE",  # Public tracker is always free ratio
                            "download_url": dl_url,
                            "details_url": details
                        })
        except Exception as e:
            logger.error(f"Error searching Nyaa: {e}")
        return results

    async def search(self, keyword: str, free_only: bool = False, site_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search across all enabled sites"""
        all_results = []
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, verify=False) as client:
            for site in self.sites:
                if site_filter and site_filter.lower() not in site.name.lower() and site_filter.lower() not in site.domain.lower():
                    continue

                if "nyaa" in site.domain.lower():
                    res = await self._search_nyaa(keyword, client)
                else:
                    res = await self._search_nexusphp(site, keyword, client)
                all_results.extend(res)

        # Filter by promo if required
        if free_only:
            all_results = [r for r in all_results if r["promo"] in ("FREE", "2XFREE")]

        # Sort: first by 2XFREE/FREE, then by seeders descending
        promo_rank = {"2XFREE": 2, "FREE": 1, "50%": 0, "NORMAL": -1}
        all_results.sort(key=lambda x: (promo_rank.get(x["promo"], -1), x["seeders"]), reverse=True)

        return all_results
