import os
import yaml
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class QBittorrentConfig(BaseModel):
    host: str = "http://192.168.100.3:8085"
    username: str = "admin"
    password: str = ""

class IYUUConfig(BaseModel):
    token: str = ""
    enabled: bool = True
    cron: str = "0 3 * * *"  # Daily at 3 AM

class SiteConfig(BaseModel):
    id: Optional[int] = None
    name: str
    domain: str
    base_url: str
    cookie: str = ""
    passkey: str = ""
    site_type: str = "nexusphp"  # nexusphp, mteam, nyaa
    enabled: bool = True

class MediaConfig(BaseModel):
    download_dir: str = "/vol1/1000/Media"
    media_dir: str = "/vol1/1000/Media"

class CookieCloudConfig(BaseModel):
    enabled: bool = False
    server: str = ""
    key: str = ""
    password: str = ""

class AppConfig(BaseModel):
    qbittorrent: QBittorrentConfig = Field(default_factory=QBittorrentConfig)
    iyuu: IYUUConfig = Field(default_factory=IYUUConfig)
    sites: List[SiteConfig] = Field(default_factory=list)
    media: MediaConfig = Field(default_factory=MediaConfig)
    cookiecloud: CookieCloudConfig = Field(default_factory=CookieCloudConfig)
    api_key: str = "pt-agent-secret"

def load_config(config_path: str = "/app/config/config.yaml") -> AppConfig:
    if not os.path.exists(config_path):
        # fallback to local path if running outside docker
        local_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
        if os.path.exists(local_path):
            config_path = local_path
        else:
            return AppConfig()
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig(**data)
