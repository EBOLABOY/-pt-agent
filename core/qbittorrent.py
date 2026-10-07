import logging
import httpx
from typing import Optional, List, Dict, Any

logger = logging.getLogger("pt_agent.qbittorrent")

class QBittorrentClient:
    """Lightweight asynchronous client for qBittorrent WebAPI"""
    def __init__(self, host: str, username: str = "", password: str = ""):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self._logged_in = False

    async def login(self) -> bool:
        try:
            url = f"{self.host}/api/v2/auth/login"
            resp = await self.client.post(url, data={"username": self.username, "password": self.password})
            if resp.status_code == 200 and "Ok." in resp.text:
                self._logged_in = True
                logger.info("Successfully connected to qBittorrent")
                return True
            # Some versions return 200 with set-cookie directly even without "Ok."
            if resp.status_code == 200 and "SID" in resp.cookies:
                self._logged_in = True
                return True
            logger.error(f"Failed to login to qBittorrent: status={resp.status_code}, response={resp.text}")
            return False
        except Exception as e:
            logger.error(f"Connection error to qBittorrent: {e}")
            return False

    async def _ensure_logged_in(self):
        if not self._logged_in:
            await self.login()

    async def get_torrents(self, filter_type: str = "all", category: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._ensure_logged_in()
        params = {"filter": filter_type}
        if category:
            params["category"] = category
        try:
            resp = await self.client.get(f"{self.host}/api/v2/torrents/info", params=params)
            if resp.status_code == 403:
                # retry login
                await self.login()
                resp = await self.client.get(f"{self.host}/api/v2/torrents/info", params=params)
            return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.error(f"Error fetching torrents: {e}")
            return []

    async def get_all_hashes(self) -> Dict[str, str]:
        """Returns {info_hash_lower: save_path} for active/seeding torrents"""
        torrents = await self.get_torrents()
        hash_dict = {}
        for t in torrents:
            h = t.get("hash", "").lower()
            save_path = t.get("save_path", "")
            if h and save_path:
                hash_dict[h] = save_path
        return hash_dict

    async def add_torrent(
        self,
        urls: Optional[str] = None,
        torrent_content: Optional[bytes] = None,
        torrent_name: Optional[str] = "torrent.torrent",
        save_path: Optional[str] = None,
        category: str = "Media",
        is_paused: bool = False,
        skip_checking: bool = False,
        tags: str = "PT_AGENT"
    ) -> bool:
        await self._ensure_logged_in()
        data = {
            "category": category,
            "paused": "true" if is_paused else "false",
            "skip_checking": "true" if skip_checking else "false",
            "autoTMM": "false",
            "tags": tags
        }
        if save_path:
            data["savepath"] = save_path

        files = None
        if torrent_content:
            files = {"torrents": (torrent_name, torrent_content, "application/x-bittorrent")}
        elif urls:
            data["urls"] = urls
        else:
            logger.error("Neither torrent_content nor urls provided to add_torrent")
            return False

        try:
            resp = await self.client.post(f"{self.host}/api/v2/torrents/add", data=data, files=files)
            if resp.status_code in (200, 204) and "Fails" not in resp.text:
                logger.info(f"Torrent successfully added to qB: tags={tags}, save_path={save_path}")
                return True
            logger.error(f"Failed to add torrent: code={resp.status_code}, response={resp.text}")
            return False
        except Exception as e:
            logger.error(f"Error adding torrent: {e}")
            return False

    async def get_transfer_info(self) -> Dict[str, Any]:
        await self._ensure_logged_in()
        try:
            resp = await self.client.get(f"{self.host}/api/v2/transfer/info")
            return resp.json() if resp.status_code == 200 else {}
        except Exception as e:
            logger.error(f"Error fetching transfer info: {e}")
            return {}

    async def close(self):
        await self.client.aclose()
