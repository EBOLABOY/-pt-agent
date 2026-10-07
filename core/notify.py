import logging
import httpx
from typing import Optional

logger = logging.getLogger("pt_agent.notify")

class Notifier:
    """PushPlus WeChat notification client"""
    def __init__(self, pushplus_token: Optional[str] = None):
        self.token = pushplus_token

    async def send(self, title: str, content: str) -> bool:
        if not self.token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "http://www.pushplus.plus/send",
                    json={
                        "token": self.token,
                        "title": title,
                        "content": content,
                        "template": "html"
                    }
                )
                if resp.status_code == 200 and resp.json().get("code") == 200:
                    logger.info(f"PushPlus notification sent: {title}")
                    return True
                logger.warning(f"PushPlus failed: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"PushPlus error: {e}")
            return False
