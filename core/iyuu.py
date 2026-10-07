import logging
import time
import json
import httpx
from typing import Dict, List, Any, Optional
from .qbittorrent import QBittorrentClient

logger = logging.getLogger("pt_agent.iyuu")

class IYUUClient:
    """Lightweight IYUU Auto-Reseed client in Python, no PHP/MySQL required"""
    BASE_API = "http://2025.iyuu.cn"

    def __init__(self, token: str, qb_client: QBittorrentClient, sites_config: List[Any]):
        self.token = token
        self.qb = qb_client
        self.sites_config = {s.name.lower(): s for s in sites_config if getattr(s, "enabled", True)}
        self.raw_sites = [s for s in sites_config if getattr(s, "enabled", True)]
        self.client = httpx.AsyncClient(timeout=30.0, headers={"token": token})

    async def get_sites(self) -> Dict[str, Any]:
        """Fetch supported PT sites from IYUU"""
        try:
            resp = await self.client.get(f"{self.BASE_API}/reseed/sites/index")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    sites = data.get("data", {}).get("sites", [])
                    return {s["site"].lower(): s for s in sites}
            logger.error(f"Failed to fetch IYUU sites: {resp.text}")
            return {}
        except Exception as e:
            logger.error(f"IYUU API error: {e}")
            return {}

    async def report_existing_sites(self, sid_list: List[int]) -> Optional[str]:
        """Reports the user's active sites to IYUU, returns sid_sha1 token"""
        try:
            resp = await self.client.post(
                f"{self.BASE_API}/reseed/sites/reportExisting",
                json={"sid_list": sid_list}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("data", {}).get("sid_sha1")
            logger.error(f"Failed to report sites to IYUU: {resp.text}")
            return None
        except Exception as e:
            logger.error(f"IYUU report error: {e}")
            return None

    async def reseed_batch(self, hashes: List[str], sid_sha1: str) -> Dict[str, Any]:
        """Query IYUU for reseed matches for a list of info_hashes"""
        data = {
            "hash": json.dumps(hashes),
            "sha1": "",
            "sid_sha1": sid_sha1,
            "timestamp": int(time.time()),
            "version": "3.0.0"
        }
        try:
            resp = await self.client.post(f"{self.BASE_API}/reseed/index/index", data=data)
            if resp.status_code == 200:
                res = resp.json()
                if res.get("code") == 0:
                    return res.get("data", {})
            logger.error(f"IYUU reseed query failed: {resp.text}")
            return {}
        except Exception as e:
            logger.error(f"Error calling IYUU reseed: {e}")
            return {}

    async def run_reseed(self) -> Dict[str, Any]:
        """Execute full auto-reseed flow"""
        if not self.token:
            return {"error": "IYUU token is empty"}

        logger.info("Starting IYUU Auto-Reseed process...")
        # 1. Fetch current torrents from qB
        hash_dict = await self.qb.get_all_hashes()
        if not hash_dict:
            return {"status": "success", "message": "No torrents found in qBittorrent", "reseed_added": 0}

        # 2. Get site metadata
        iyuu_sites = await self.get_sites()
        matched_sids = []
        for name, site_cfg in self.sites_config.items():
            if name in iyuu_sites:
                matched_sids.append(iyuu_sites[name]["id"])

        if not matched_sids:
            logger.warning("No configured sites match IYUU site list. Using all recommended sites.")
            # fallback to reporting all sites user might have
            matched_sids = [s["id"] for s in iyuu_sites.values()]

        sid_sha1 = await self.report_existing_sites(matched_sids)
        if not sid_sha1:
            return {"error": "Failed to authenticate site list with IYUU"}

        # 3. Chunk hashes in batches of 200
        all_hashes = list(hash_dict.keys())
        batch_size = 200
        total_matched = 0
        total_added = 0
        total_skipped = 0

        for i in range(0, len(all_hashes), batch_size):
            chunk = all_hashes[i:i + batch_size]
            results = await self.reseed_batch(chunk, sid_sha1)

            for orig_hash, reseed_info in results.items():
                orig_dir = hash_dict.get(orig_hash)
                torrents = reseed_info.get("torrent", [])
                total_matched += len(torrents)

                for item in torrents:
                    r_hash = item.get("info_hash", "").lower()
                    r_sid = item.get("sid")
                    r_torrent_id = item.get("torrent_id")

                    # Skip if already exists in qB
                    if r_hash in hash_dict:
                        total_skipped += 1
                        continue

                    # Find site metadata from IYUU
                    s_info = None
                    for _, info in iyuu_sites.items():
                        if info.get("id") == r_sid:
                            s_info = info
                            break

                    if not s_info:
                        total_skipped += 1
                        continue

                    # Match with user's local site configs
                    site_cfg = None
                    iyuu_s_name = s_info.get("site", "").lower()
                    iyuu_nick = s_info.get("nickname", "")
                    iyuu_domain = s_info.get("base_url", "").lower()

                    for sc in self.raw_sites:
                        sc_name = sc.name.lower()
                        sc_dom = sc.domain.lower()
                        if (iyuu_s_name in sc_name or sc_name in iyuu_s_name or
                            iyuu_s_name in sc_dom or sc_dom in iyuu_domain or
                            iyuu_domain in sc_dom or
                            (iyuu_nick and (iyuu_nick in sc.name or sc.name in iyuu_nick))):
                            site_cfg = sc
                            break

                    if not site_cfg or not site_cfg.passkey:
                        total_skipped += 1
                        continue

                    # Construct download URL with passkey
                    dl_template = s_info.get("download_page") or "download.php?id={}&passkey={passkey}"
                    dl_path = dl_template.replace("{}", str(r_torrent_id)).replace("{passkey}", site_cfg.passkey)
                    base = site_cfg.base_url.rstrip("/")
                    download_url = f"{base}/{dl_path.lstrip('/')}"

                    if download_url:
                        # Add torrent to qB with skip_checking=True
                        success = await self.qb.add_torrent(
                            urls=download_url,
                            save_path=orig_dir,
                            skip_checking=True,
                            is_paused=False,
                            tags="IYUU,PT_AGENT"
                        )
                        if success:
                            total_added += 1
                            # record to prevent duplicate in same run
                            hash_dict[r_hash] = orig_dir
                        else:
                            total_skipped += 1
                    else:
                        total_skipped += 1

        summary = {
            "status": "success",
            "total_local_torrents": len(all_hashes),
            "total_matched": total_matched,
            "total_added": total_added,
            "total_skipped": total_skipped
        }
        logger.info(f"Reseed finished: {summary}")
        return summary

    async def close(self):
        await self.client.aclose()
