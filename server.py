import os
import logging
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_config, AppConfig
from core.qbittorrent import QBittorrentClient
from core.iyuu import IYUUClient
from core.indexer import PTIndexer
from core.signin import PTSignIn
from core.organizer import MediaOrganizer
from core.notify import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pt_agent.server")

# Load configuration
config: AppConfig = load_config()

# Initialize core services
qb_client = QBittorrentClient(
    host=config.qbittorrent.host,
    username=config.qbittorrent.username,
    password=config.qbittorrent.password
)
iyuu_client = IYUUClient(
    token=config.iyuu.token,
    qb_client=qb_client,
    sites_config=config.sites
)
indexer = PTIndexer(sites_config=config.sites)
signin_service = PTSignIn(sites_config=config.sites)
organizer = MediaOrganizer(media_root=config.media.media_dir)
notifier = Notifier(pushplus_token=config.pushplus.token if config.pushplus.enabled else None)

scheduler = AsyncIOScheduler()

async def scheduled_signin():
    logger.info("Running scheduled daily PT signin...")
    res = await signin_service.signin_all()
    await notifier.send("PT 每日签到汇报", f"<pre>{res}</pre>")

async def scheduled_reseed():
    if config.iyuu.enabled and config.iyuu.token:
        logger.info("Running scheduled IYUU auto-reseed...")
        res = await iyuu_client.run_reseed()
        await notifier.send("IYUU 自动辅种结果", f"<pre>{res}</pre>")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting pt-agent service...")
    await qb_client.login()
    
    # Schedule daily signin at 08:30
    scheduler.add_job(scheduled_signin, "cron", hour=8, minute=30)
    # Schedule daily reseed at 03:00 and periodic reseed every 30 minutes
    scheduler.add_job(scheduled_reseed, "cron", hour=3, minute=0)
    scheduler.add_job(scheduled_reseed, "interval", minutes=30)
    scheduler.start()
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    await qb_client.close()
    await iyuu_client.close()
    logger.info("pt-agent service shut down.")

app = FastAPI(title="pt-agent", description="AI-Native Lightweight PT & Media Automation Hub", version="1.0.0", lifespan=lifespan)

# Models
class SearchRequest(BaseModel):
    query: str
    free_only: bool = False
    site_filter: Optional[str] = None
    top_tier_only: bool = True

class DownloadRequest(BaseModel):
    download_url: str
    category: str = "Media"
    save_path: Optional[str] = None
    tags: str = "PT_AGENT"
    title: Optional[str] = None
    query: Optional[str] = None
    auto_cross_site: bool = True

class OrganizeRequest(BaseModel):
    source_path: str
    category: str = "外语电影"
    custom_title: Optional[str] = None

# REST API Endpoints
@app.get("/health")
async def health():
    return {"status": "ok", "service": "pt-agent", "version": "1.0.0"}

@app.get("/api/status")
async def get_status():
    """Get qBittorrent connection & transmission stats"""
    transfer = await qb_client.get_transfer_info()
    torrents = await qb_client.get_torrents()
    return {
        "qbittorrent_connected": qb_client._logged_in,
        "torrents_total": len(torrents),
        "dl_info_speed": transfer.get("dl_info_speed", 0),
        "up_info_speed": transfer.get("up_info_speed", 0),
        "dl_info_data": transfer.get("dl_info_data", 0),
        "up_info_data": transfer.get("up_info_data", 0),
        "sites_configured": len(config.sites),
        "iyuu_enabled": bool(config.iyuu.token)
    }

@app.post("/api/search")
async def search_torrents(req: SearchRequest):
    """Search for torrents across configured PT sites"""
    results = await indexer.search(keyword=req.query, free_only=req.free_only, site_filter=req.site_filter, top_tier_only=req.top_tier_only)
    return {"query": req.query, "count": len(results), "top_tier_only": req.top_tier_only, "results": results}

@app.post("/api/download")
async def download_torrent(req: DownloadRequest):
    """Push torrent to qBittorrent with automatic multi-site linkage synergy"""
    if req.save_path:
        save_path = req.save_path
    elif req.category:
        save_path = os.path.join(config.media.download_dir, req.category)
    else:
        save_path = config.media.download_dir

    # 1. Add primary torrent
    success = await qb_client.add_torrent(
        urls=req.download_url,
        save_path=save_path,
        category=req.category,
        tags=req.tags
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add torrent to qBittorrent")

    # 2. Multi-site synergy linkage: automatically search & add matching releases from other sites
    synergy_added = []
    if req.auto_cross_site:
        target_title = req.title
        # If title wasn't passed, try to infer from download url or query
        if not target_title and req.query:
            target_title = req.query

        if target_title:
            try:
                matches = await indexer.find_synergy_torrents(
                    target_title=target_title,
                    query=req.query,
                    exclude_url=req.download_url
                )
                for m in matches:
                    m_url = m.get("download_url")
                    m_site = m.get("site")
                    m_title = m.get("title")
                    logger.info(f"Adding multi-site synergy torrent from {m_site}: {m_title}")
                    added = await qb_client.add_torrent(
                        urls=m_url,
                        save_path=save_path,
                        category=req.category,
                        tags=f"{req.tags},MULTI_SITE,{m_site.upper()}"
                    )
                    if added:
                        synergy_added.append({"site": m_site, "title": m_title})
            except Exception as e:
                logger.warning(f"Error executing auto cross-site synergy: {e}")

    return {
        "status": "success",
        "message": "Torrent added with multi-site linkage",
        "save_path": save_path,
        "synergy_count": len(synergy_added),
        "synergy_torrents": synergy_added
    }

@app.post("/api/reseed")
async def run_reseed():
    """Trigger IYUU auto-reseed immediately"""
    res = await iyuu_client.run_reseed()
    return res

@app.post("/api/signin")
async def run_signin():
    """Trigger PT sites signin immediately"""
    res = await signin_service.signin_all()
    return {"status": "success", "results": res}

@app.post("/api/organize")
async def organize_media(req: OrganizeRequest):
    """Hardlink and organize media files for fnOS Media Center"""
    res = organizer.organize_path(source_path=req.source_path, category=req.category, custom_title=req.custom_title)
    return {"status": "success", "count": len(res), "organized_files": res}

# --- MCP (Model Context Protocol) JSON-RPC Standard Endpoint ---
# Allows any AI Agent to directly list and invoke tools

MCP_TOOLS = [
    {
        "name": "pt_search",
        "description": "Search for movies, TV series or torrents across PT sites with Free/2xFree filter",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword, e.g. movie name or actor"},
                "free_only": {"type": "boolean", "description": "Only return Free or 2xFree torrents (default true)", "default": True},
                "site_filter": {"type": "string", "description": "Optional site name to search specific site"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "pt_download",
        "description": "Download a torrent into qBittorrent by URL or torrent file link",
        "inputSchema": {
            "type": "object",
            "properties": {
                "download_url": {"type": "string", "description": "Torrent download link"},
                "category": {"type": "string", "description": "Category tag (e.g. Media, 电影, 电视剧)", "default": "Media"}
            },
            "required": ["download_url"]
        }
    },
    {
        "name": "pt_reseed",
        "description": "Trigger IYUU automatic cross-site reseed (辅种) for all active torrents",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "pt_signin",
        "description": "Perform automatic check-in (签到) for all configured PT sites and report magic points",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "pt_status",
        "description": "Get current download/upload speeds, active torrent count, and system status",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "pt_organize",
        "description": "Hardlink completed download to fnOS Media library directory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Path of downloaded file or directory"},
                "category": {"type": "string", "description": "Target folder, e.g. 外语电影, 华语电影, 国产剧, 欧美剧", "default": "外语电影"},
                "custom_title": {"type": "string", "description": "Optional standardized title e.g. 奥本海默 (2023)"}
            },
            "required": ["source_path"]
        }
    }
]

@app.post("/mcp")
async def mcp_endpoint(payload: Dict[str, Any]):
    """Standard Model Context Protocol JSON-RPC handler for AI agents"""
    method = payload.get("method")
    req_id = payload.get("id", 1)
    
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}
        
    elif method == "tools/call":
        params = payload.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        
        try:
            if name == "pt_search":
                res = await indexer.search(
                    keyword=args.get("query"),
                    free_only=args.get("free_only", False),
                    site_filter=args.get("site_filter"),
                    top_tier_only=args.get("top_tier_only", True)
                )
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            elif name == "pt_download":
                d_req = DownloadRequest(
                    download_url=args.get("download_url"),
                    category=args.get("category", "外语电影"),
                    title=args.get("title"),
                    query=args.get("query"),
                    auto_cross_site=args.get("auto_cross_site", True)
                )
                res = await download_torrent(d_req)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            elif name == "pt_reseed":
                res = await iyuu_client.run_reseed()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            elif name == "pt_signin":
                res = await signin_service.signin_all()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            elif name == "pt_status":
                res = await get_status()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            elif name == "pt_organize":
                res = organizer.organize_path(source_path=args.get("source_path"), category=args.get("category", "外语电影"), custom_title=args.get("custom_title"))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}
            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{name}' not found"}}
        except Exception as e:
            logger.error(f"Error handling tool call {name}: {e}")
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}
            
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not supported"}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8989, reload=False)
