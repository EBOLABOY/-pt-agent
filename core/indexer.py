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

    def _calculate_quality_score(self, title: str, subtitle: str) -> int:
        """Score torrent based on flagship Home-Theater hardware (TCL Q9M Pro + Samsung Q930B)"""
        text = f"{title} {subtitle}".upper()
        
        # 1. Reject unplayable or bootleg formats
        if any(k in text for k in ["3D", "CAM", "HDCAM", "TELESYNC", "TS-", "TC-", "TC "]):
            return -9999
            
        score = 0
        
        # 2. Master packaging (REMUX & UHD BluRay are King)
        if "REMUX" in text:
            score += 1200
        elif any(k in text for k in ["UHD BLURAY", "UHD BLU-RAY", "BDMV", "ISO", "BLURAY", "BLU-RAY"]):
            score += 1000
        elif any(k in text for k in ["WEB-DL", "WEBDL", "HQ WEB-DL"]):
            score += 500
        elif any(k in text for k in ["BDRIP", "HDRIP"]):
            score += 350

        # 3. Resolution (4K / 2160p)
        if any(k in text for k in ["2160P", "4K", "UHD"]):
            score += 600
        elif "1080P" in text:
            score += 200

        # 4. Premium Video Dynamics (TCL Q9M Pro Mini-LED powerhouse)
        if any(k in text for k in ["DOVI", "DOLBY VISION", "DV"]):
            score += 500
        if "HDR10+" in text:
            score += 450
        elif "HDR" in text:
            score += 300

        # 5. Premium Lossless Audio (Samsung Q930B 9.1.4 Atmos powerhouse)
        if any(k in text for k in ["ATMOS", "TRUEHD"]):
            score += 500
        if any(k in text for k in ["DTS:X", "DTS-HD", "DTS-HD MA"]):
            score += 450
        elif any(k in text for k in ["DDP5.1", "E-AC-3", "AC-3 5.1", "DTS 5.1"]):
            score += 150

        return score

    def is_strictly_top_tier(self, title: str, subtitle: str) -> bool:
        """Strictly determine if release is Top-Tier (4K/1080p REMUX or Original BluRay Disc)"""
        text = f"{title} {subtitle}".upper()
        
        # 1. 绝对剔除枪版、3D和一切有损/低码率压制版/WEB-DL
        if any(k in text for k in ["3D", "CAM", "HDCAM", "TELESYNC", "TS-", "TC-", "TC ", "WEB-DL", "WEBDL", "WEBRIP", "BDRIP", "HDRIP", "HDTV", "DVDRIP", "720P", "X264", "H264"]):
            return False
            
        # 2. 必须具备母盘无损封装: REMUX 或 原盘 (UHD BluRay / BDMV / ISO / BluRay)
        has_remux = "REMUX" in text
        has_disc = any(k in text for k in ["UHD BLURAY", "UHD BLU-RAY", "BDMV", "ISO", "BLURAY", "BLU-RAY"])
        
        if not (has_remux or has_disc):
            return False

        # 3. 必须具备超清或高清分辨率
        has_resolution = any(k in text for k in ["2160P", "4K", "UHD", "1080P"])
        if not has_resolution:
            return False
            
        return True

    async def search(self, keyword: str, free_only: bool = False, site_filter: Optional[str] = None, top_tier_only: bool = True) -> List[Dict[str, Any]]:
        """Search across all enabled sites with strict cinephile top-tier filtering"""
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

        # Enforce strict top-tier filter (REMUX / 原盘 only)
        filtered = []
        promo_bonus = {"2XFREE": 300, "FREE": 200, "50%": 50, "NORMAL": 0}
        
        for r in all_results:
            title = r.get("title", "")
            subtitle = r.get("subtitle", "")
            
            # If top_tier_only is enabled, strictly filter out everything else
            if top_tier_only and not self.is_strictly_top_tier(title, subtitle):
                continue
                
            q_score = self._calculate_quality_score(title, subtitle)
            if q_score < 0:
                continue
            if free_only and r["promo"] not in ("FREE", "2XFREE"):
                continue
                
            p_bonus = promo_bonus.get(r.get("promo", "NORMAL"), 0)
            s_bonus = min(r.get("seeders", 0) * 5, 200)  # Seeders bonus up to 200
            
            r["_score"] = q_score + p_bonus + s_bonus
            filtered.append(r)

        # Sort: highest overall cinephile score first
        filtered.sort(key=lambda x: x["_score"], reverse=True)
        return filtered
