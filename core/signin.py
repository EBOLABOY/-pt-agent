import re
import logging
import httpx
from typing import List, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger("pt_agent.signin")

class PTSignIn:
    """Automated sign-in & statistics scraper for PT sites"""
    def __init__(self, sites_config: List[Any]):
        self.sites = [
            s for s in sites_config 
            if getattr(s, "enabled", True) and (getattr(s, "cookie", "") or "rousi" in getattr(s, "domain", "").lower())
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    async def _signin_rousi(self, site) -> Dict[str, Any]:
        result = {
            "site": site.name,
            "domain": site.domain,
            "status": "unknown",
            "message": "",
            "bonus": None,
            "ratio": None,
            "uploaded": None,
            "downloaded": None
        }
        token = getattr(site, "passkey", "") or getattr(site, "apikey", "")
        if not token:
            result["status"] = "failed"
            result["message"] = "未配置 API Key"
            return result

        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.headers["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}"
        }

        async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
            try:
                # 1. Signin (mode: fixed)
                res = await client.post("https://rousi.pro/api/points/attendance", json={"mode": "fixed"}, headers=headers)
                if res.status_code == 200 and res.json().get("code") == 0:
                    data = res.json().get("data", {})
                    reward = data.get("reward", 0)
                    streak = data.get("current_streak", 0)
                    result["status"] = "success"
                    result["message"] = f"签到成功 (+{reward}魔力，连续{streak}天)"
                elif res.status_code == 400 or (res.status_code == 200 and res.json().get("code") != 0):
                    result["status"] = "success"
                    result["message"] = "今日已签到"
                else:
                    result["status"] = "failed"
                    result["message"] = f"HTTP {res.status_code}"

                # 2. Get profile stats
                prof_res = await client.get("https://rousi.pro/api/v1/profile", headers=headers)
                if prof_res.status_code == 200 and prof_res.json().get("code") == 0:
                    p = prof_res.json().get("data", {})
                    result["bonus"] = str(p.get("karma", 0))
                    result["ratio"] = f"{p.get('ratio', 0):.2f}"
                    dl_bytes = p.get("downloaded", 0)
                    up_bytes = int(dl_bytes * p.get("ratio", 0))
                    result["downloaded"] = f"{dl_bytes / (1024**3):.2f} GB"
                    result["uploaded"] = f"{up_bytes / (1024**3):.2f} GB"
            except Exception as e:
                result["status"] = "failed"
                result["message"] = str(e)

        return result

    async def signin_site(self, site) -> Dict[str, Any]:
        if "rousi" in getattr(site, "domain", "").lower() or getattr(site, "type", "") == "peergo":
            return await self._signin_rousi(site)

        result = {
            "site": site.name,
            "domain": site.domain,
            "status": "unknown",
            "message": "",
            "bonus": None,
            "ratio": None,
            "uploaded": None,
            "downloaded": None
        }
        base_url = site.base_url.rstrip("/")
        headers = dict(self.headers)
        headers["Cookie"] = site.cookie

        async with httpx.AsyncClient(timeout=25.0, headers=headers, follow_redirects=True, verify=False) as client:
            try:
                # 1. Try standard NexusPHP attendance.php
                att_url = f"{base_url}/attendance.php"
                resp = await client.get(att_url)
                text = resp.text

                if "签到成功" in text or "这是您的第" in text or "获得了" in text:
                    result["status"] = "success"
                    result["message"] = "签到成功"
                elif "已经签到" in text or "已签到" in text or "今日已签到" in text:
                    result["status"] = "success"
                    result["message"] = "今日已签到"
                else:
                    # 2. Try index.php
                    index_resp = await client.get(f"{base_url}/index.php")
                    text = index_resp.text
                    if "已经签到" in text or "今日已签到" in text:
                        result["status"] = "success"
                        result["message"] = "今日已签到"
                    elif "签到" in text and ("attendance" in text or "sign" in text):
                        result["status"] = "success"
                        result["message"] = "访问成功（或无需签到）"
                    elif index_resp.status_code == 200:
                        result["status"] = "success"
                        result["message"] = "在线（Cookie有效）"
                    else:
                        result["status"] = "failed"
                        result["message"] = f"HTTP {index_resp.status_code}"

                # 3. Parse user stats (Magic points, Ratio, Upload/Download)
                soup = BeautifulSoup(text, "html.parser")
                text_clean = soup.get_text()

                # Bonus / 魔力
                bonus_match = re.search(r'(?:魔力值|积分|Karma|Bonus)[：:\s]*([\d,.]+)', text_clean, re.I)
                if bonus_match:
                    result["bonus"] = bonus_match.group(1).replace(",", "")

                # Ratio / 分享率
                ratio_match = re.search(r'(?:分享率|Ratio)[：:\s]*([\d,.]+)', text_clean, re.I)
                if ratio_match:
                    result["ratio"] = ratio_match.group(1)

                # Upload / 上传量
                up_match = re.search(r'(?:上传量|Uploaded)[：:\s]*([\d,.]+\s*(?:[KMGTPE]?B|Bytes))', text_clean, re.I)
                if up_match:
                    result["uploaded"] = up_match.group(1).strip()

                # Download / 下载量
                down_match = re.search(r'(?:下载量|Downloaded)[：:\s]*([\d,.]+\s*(?:[KMGTPE]?B|Bytes))', text_clean, re.I)
                if down_match:
                    result["downloaded"] = down_match.group(1).strip()

            except Exception as e:
                logger.error(f"Error during sign-in for {site.name}: {e}")
                result["status"] = "error"
                result["message"] = str(e)

        return result

    async def signin_all(self) -> List[Dict[str, Any]]:
        results = []
        for site in self.sites:
            res = await self.signin_site(site)
            results.append(res)
        return results
