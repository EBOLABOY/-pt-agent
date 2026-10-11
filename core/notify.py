import logging
import httpx
from typing import Optional, List, Dict, Any

logger = logging.getLogger("pt_agent.notify")

def _fmt_bonus(val: Any) -> str:
    if not val:
        return "--"
    try:
        num = float(str(val).replace(",", "").strip())
        return f"{num:,.0f}" if num.is_integer() else f"{num:,.2f}"
    except Exception:
        return str(val)

def format_signin_html(results: List[Dict[str, Any]]) -> str:
    """Format daily PT check-in results into a clean, modern Chinese mobile card"""
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    all_success = (success_count == total and total > 0)
    
    summary_bg = "#ecfdf5" if all_success else "#fef2f2"
    summary_color = "#047857" if all_success else "#b91c1c"
    summary_text = f"全部成功 ({success_count}/{total})" if all_success else f"部分站点异常 ({success_count}/{total} 成功)"

    site_cards = []
    for r in results:
        site_name = r.get("site") or r.get("domain") or "未知站点"
        status = r.get("status", "unknown")
        msg = r.get("message", "")
        bonus = _fmt_bonus(r.get("bonus"))
        ratio = r.get("ratio") or "--"
        uploaded = r.get("uploaded") or "--"
        downloaded = r.get("downloaded") or "--"

        is_ok = (status == "success")
        badge_bg = "#ecfdf5" if is_ok else "#fef2f2"
        badge_color = "#059669" if is_ok else "#dc2626"
        badge_text = msg if msg else ("签到成功" if is_ok else "签到失败")

        card = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 10px;">
            <tr>
              <td align="left" style="font-size: 15px; font-weight: 700; color: #0f172a;">{site_name}</td>
              <td align="right">
                <span style="font-size: 12px; padding: 3px 9px; border-radius: 6px; background: {badge_bg}; color: {badge_color}; font-weight: 600;">{badge_text}</span>
              </td>
            </tr>
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size: 13px; color: #475569; line-height: 1.8;">
            <tr>
              <td width="50%">💎 魔力值：<b style="color: #0f172a;">{bonus}</b></td>
              <td width="50%">📈 分享率：<b style="color: #0f172a;">{ratio}</b></td>
            </tr>
            <tr>
              <td width="50%">⬆ 上传量：<b style="color: #0f172a;">{uploaded}</b></td>
              <td width="50%">⬇ 下载量：<b style="color: #0f172a;">{downloaded}</b></td>
            </tr>
          </table>
        </div>
        """
        site_cards.append(card)

    cards_html = "\n".join(site_cards)

    return f"""
    <div style="max-width: 500px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
      <div style="background: linear-gradient(135deg, #1e40af, #3b82f6); padding: 20px; color: #ffffff;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td>
              <h2 style="margin: 0; font-size: 18px; font-weight: 700; letter-spacing: 0.3px;">📅 PT 站点每日签到汇报</h2>
              <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">监控站点自动巡检与数据统计</p>
            </td>
            <td align="right" valign="top">
              <span style="font-size: 12px; padding: 4px 10px; border-radius: 20px; background: {summary_bg}; color: {summary_color}; font-weight: 700; white-space: nowrap;">{summary_text}</span>
            </td>
          </tr>
        </table>
      </div>
      <div style="padding: 16px;">
        {cards_html}
      </div>
      <div style="padding: 12px 16px; background: #f1f5f9; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
        飞牛 fnOS 影视中枢 · pt-agent 智能推送
      </div>
    </div>
    """

def format_reseed_html(summary: Dict[str, Any]) -> str:
    """Format IYUU auto-reseed results into a clean Chinese mobile card"""
    total_local = summary.get("total_local_torrents", 0)
    matched = summary.get("total_matched", 0)
    added = summary.get("total_added", 0)
    skipped = summary.get("total_skipped", 0)

    return f"""
    <div style="max-width: 500px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
      <div style="background: linear-gradient(135deg, #065f46, #10b981); padding: 20px; color: #ffffff;">
        <h2 style="margin: 0; font-size: 18px; font-weight: 700;">🔄 IYUU 跨站自动辅种报告</h2>
        <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">零磁盘占用 · 自动注入与多站辅种</p>
      </div>
      <div style="padding: 16px;">
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-bottom: 12px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="text-align: center;">
            <tr>
              <td width="50%" style="padding: 10px 0; border-bottom: 1px solid #f1f5f9; border-right: 1px solid #f1f5f9;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">本地种子总数</div>
                <div style="font-size: 22px; font-weight: 700; color: #0f172a;">{total_local}</div>
              </td>
              <td width="50%" style="padding: 10px 0; border-bottom: 1px solid #f1f5f9;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">跨站匹配候选</div>
                <div style="font-size: 22px; font-weight: 700; color: #0f172a;">{matched}</div>
              </td>
            </tr>
            <tr>
              <td width="50%" style="padding: 10px 0; border-right: 1px solid #f1f5f9;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">本次新增辅种</div>
                <div style="font-size: 22px; font-weight: 700; color: #059669;">+{added}</div>
              </td>
              <td width="50%" style="padding: 10px 0;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">已存在/已忽略</div>
                <div style="font-size: 22px; font-weight: 700; color: #64748b;">{skipped}</div>
              </td>
            </tr>
          </table>
        </div>
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #166534; line-height: 1.5;">
          💡 <b>状态说明</b>：新增辅种任务已自动设置跳过校验，与原资源共享同一份媒体文件，安全赚取各站上传量与魔力。
        </div>
      </div>
      <div style="padding: 12px 16px; background: #f1f5f9; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
        飞牛 fnOS 影视中枢 · pt-agent 智能推送
      </div>
    </div>
    """

def format_download_html(title: str, category: str, save_path: str, synergy_sites: Optional[List[Dict[str, str]]] = None) -> str:
    """Format movie download dispatch card with synergy details"""
    synergy_count = len(synergy_sites) if synergy_sites else 0
    synergy_text = f"已开启 (共联动 {synergy_count} 个镜像站点)" if synergy_count > 0 else "未启用 (单站下载)"
    synergy_badge = "#059669" if synergy_count > 0 else "#64748b"

    synergy_list_html = ""
    if synergy_sites:
        items = "".join([f"<li><b>{s.get('site', '').upper()}</b>: {s.get('title', '')[:35]}...</li>" for s in synergy_sites])
        synergy_list_html = f"""
        <div style="margin-top: 10px; padding: 10px 12px; background: #faf5ff; border: 1px solid #f3e8ff; border-radius: 8px; font-size: 12px; color: #6b21a8;">
          <div style="font-weight: 700; margin-bottom: 4px;">⚡ 协同下载站点清单：</div>
          <ul style="margin: 0; padding-left: 18px; line-height: 1.6;">{items}</ul>
        </div>
        """

    return f"""
    <div style="max-width: 500px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
      <div style="background: linear-gradient(135deg, #6b21a8, #9333ea); padding: 20px; color: #ffffff;">
        <h2 style="margin: 0; font-size: 18px; font-weight: 700;">🎬 新增影视下载任务</h2>
        <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">任务已推送至 qBittorrent 调度执行</p>
      </div>
      <div style="padding: 16px;">
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size: 13px; color: #475569; line-height: 2.0;">
            <tr>
              <td width="28%" style="color: #64748b;">影片名称：</td>
              <td width="72%" style="font-weight: 700; color: #0f172a; word-break: break-all;">{title}</td>
            </tr>
            <tr>
              <td style="color: #64748b;">分类归档：</td>
              <td style="font-weight: 600; color: #0f172a;">{category}</td>
            </tr>
            <tr>
              <td style="color: #64748b;">多站协同：</td>
              <td style="font-weight: 600; color: {synergy_badge};">{synergy_text}</td>
            </tr>
            <tr>
              <td style="color: #64748b;">存储路径：</td>
              <td style="color: #64748b; font-size: 12px; word-break: break-all;">{save_path}</td>
            </tr>
            <tr>
              <td style="color: #64748b;">上行防护：</td>
              <td style="color: #059669; font-weight: 600;">已锁定全局 1.0 MB/s (防 PCDN 判定)</td>
            </tr>
          </table>
          {synergy_list_html}
        </div>
      </div>
      <div style="padding: 12px 16px; background: #f1f5f9; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
        飞牛 fnOS 影视中枢 · pt-agent 智能推送
      </div>
    </div>
    """

def format_organize_html(category: str, files: List[Dict[str, str]]) -> str:
    """Format movie library entry card for fnOS Media Center"""
    count = len(files)
    file_items = []
    for f in files[:5]:
        dest_name = f.get("destination", "").split("/")[-1]
        file_items.append(f"<li style='margin-bottom: 4px; word-break: break-all;'>{dest_name}</li>")
    
    if len(files) > 5:
        file_items.append(f"<li style='color: #64748b;'>...等共 {count} 个文件</li>")

    items_html = "".join(file_items)

    return f"""
    <div style="max-width: 500px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
      <div style="background: linear-gradient(135deg, #c2410c, #f97316); padding: 20px; color: #ffffff;">
        <h2 style="margin: 0; font-size: 18px; font-weight: 700;">🍿 飞牛影视已入库就绪</h2>
        <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">硬链接整理完成 · 零占用新磁盘空间</p>
      </div>
      <div style="padding: 16px;">
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size: 13px; color: #475569; line-height: 2.0; margin-bottom: 8px;">
            <tr>
              <td width="28%" style="color: #64748b;">入库分类：</td>
              <td width="72%" style="font-weight: 700; color: #0f172a;">{category}</td>
            </tr>
            <tr>
              <td style="color: #64748b;">整理数量：</td>
              <td style="font-weight: 700; color: #059669;">{count} 个视频文件</td>
            </tr>
          </table>
          <div style="font-size: 12px; color: #334155; background: #fff7ed; border: 1px solid #ffedd5; border-radius: 8px; padding: 10px 12px;">
            <div style="font-weight: 700; margin-bottom: 4px; color: #c2410c;">📁 入库文件列表：</div>
            <ul style="margin: 0; padding-left: 18px; line-height: 1.6;">{items_html}</ul>
          </div>
        </div>
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #166534; line-height: 1.5;">
          🎬 <b>观看提示</b>：飞牛影视客户端已自动刮削海报墙与元数据，您可在手机、TV 或网页端直接播放。
        </div>
      </div>
      <div style="padding: 12px 16px; background: #f1f5f9; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
        飞牛 fnOS 影视中枢 · pt-agent 智能推送
      </div>
    </div>
    """

class Notifier:
    """PushPlus WeChat notification client with clean Chinese card formatting"""
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

    async def send_signin(self, results: List[Dict[str, Any]]) -> bool:
        """Send formatted Chinese sign-in card"""
        html = format_signin_html(results)
        return await self.send("PT 每日签到汇报", html)

    async def send_reseed(self, summary: Dict[str, Any]) -> bool:
        """Send formatted Chinese reseed card"""
        html = format_reseed_html(summary)
        return await self.send("IYUU 跨站自动辅种报告", html)

    async def send_download(self, title: str, category: str, save_path: str, synergy_sites: Optional[List[Dict[str, str]]] = None) -> bool:
        """Send formatted Chinese download task card"""
        html = format_download_html(title, category, save_path, synergy_sites)
        return await self.send(f"影视下载启动: {title[:20]}", html)

    async def send_organize(self, category: str, files: List[Dict[str, str]]) -> bool:
        """Send formatted Chinese media library entry card"""
        html = format_organize_html(category, files)
        return await self.send("飞牛影视已入库就绪", html)
