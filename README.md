# pt-agent

🤖 **AI 原生极简 PT & 影音自动化中枢** (AI-Native Lightweight PT & Media Automation Hub)

专为飞牛 NAS (fnOS) 及各类私有云环境打造。旨在彻底摆脱传统工具（MoviePilot、IYUUPlus）臃肿庞大的 Web 界面、无头浏览器、MySQL 数据库等沉重依赖，以 **< 90MB 镜像、< 30MB 运行内存** 的超轻量形态，提供纯粹的 PT 自动化能力，并通过 **标准 MCP (Model Context Protocol)** 与 **REST API** 专供 AI Agent 调用。

---

## 🌟 核心特性

- 🚀 **极致轻量**：镜像体积不到 90MB，内存占用仅约 20~30MB（相比 MoviePilot 1.5GB + IYUUPlus 300MB 节约 95% 以上系统资源）。
- 🎯 **AI 原生集成**：内置符合 Anthropic 标准的 **Model Context Protocol (MCP)** 协议，支持各大 AI Agent（Antigravity、Claude Desktop、Chatbox、Dify 等）直接作为本地工具调用。
- 🔍 **PT 智能搜索与优选**：支持 NexusPHP 架构站点与公共站点检索，自动解析优惠标签（`Free`、`2xFree`）、做种人数与体积，自动过滤并优先呈现优质免费种。
- ⚡ **无数据库 IYUU 自动辅种**：直接对接 qBittorrent WebAPI 读取做种信息，调用 IYUU 官方接口秒级完成跨站辅种匹配，推回下载器并开启“跳过哈希校验”，彻底淘汰本地 MySQL 数据库。
- 📅 **全站自动签到**：支持定时全站签到与活跃度保活，自动采集魔力值（积分）、做种量与上传下载统计。
- 🎬 **飞牛影视零拷贝入库**：下载完成后支持通过 Linux 原生 `os.link` 硬链接到分类媒体库（`/vol1/1000/Media/`），秒级触发飞牛影视海报墙刮削，不占用任何额外硬盘空间。

---

## 📊 资源占用对比

| 指标 | MoviePilot v2 + IYUUPlus | **pt-agent** |
| :--- | :--- | :--- |
| **Docker 镜像总大小** | ~ 1.85 GB | **< 90 MB** |
| **常驻运行内存** | ~ 500MB - 1.2 GB | **~ 25 MB** |
| **数据库依赖** | SQLite + MariaDB/MySQL | **无（完全无状态轻量设计）** |
| **浏览器依赖** | Playwright / Chromium (1GB) | **无** |
| **交互方式** | 复杂的网页配置与多级表单 | **自然语言直接告诉 AI 执行** |

---

## 🛠️ 快速部署

### 1. 配置文件
创建并编辑 `config/config.yaml`（可参考 `config.example.yaml`）：

```yaml
qbittorrent:
  host: "http://192.168.100.3:8085"
  username: "admin"
  password: "your_password"

iyuu:
  token: "your_iyuu_token"
  enabled: true
  cron: "0 3 * * *"

media:
  download_dir: "/vol1/1000/Media"
  media_dir: "/vol1/1000/Media"

sites:
  - name: "红豆饭"
    domain: "hdfans.org"
    base_url: "https://hdfans.org"
    cookie: "your_cookie"
    passkey: ""
    enabled: true

  - name: "PT时间"
    domain: "pttime.org"
    base_url: "https://www.pttime.org"
    cookie: "your_cookie"
    passkey: ""
    enabled: true
```

### 2. 使用 Docker Compose 启动

```bash
docker compose up -d
```

---

## 🤖 AI Agent 接入与调用 (MCP 规范)

`pt-agent` 在 `http://<NAS_IP>:8989/mcp` 提供了标准 Model Context Protocol 工具定义：

| MCP 工具名称 | 描述 | 参数 |
| :--- | :--- | :--- |
| `pt_search` | 在各大 PT 站搜索资源并筛选 Free/2xFree | `query` (关键词), `free_only` (默认 true) |
| `pt_download` | 推送种子链接到 qBittorrent 开始下载 | `download_url`, `category` |
| `pt_reseed` | 触发 IYUU 跨站全量自动辅种 | 无 |
| `pt_signin` | 执行所有已配置站点的每日签到 | 无 |
| `pt_status` | 查看当前上传下载速度、做种总数及系统状态 | 无 |
| `pt_organize` | 将下载目录硬链接并规范化命名入库飞牛影视 | `source_path`, `category`, `custom_title` |

### 双模运行机制 (Dual Modes)：

1. **模式 A：订阅后台自动化模式 (Subscription Auto Mode)**
   * 后台定时监听，严格只下音画质全网综合评分第 1 名的母盘（4K UHD REMUX / 原盘，DoVi + TrueHD Atmos 7.1 优先），全自动推送到 qB 并硬链接入库，无需人工干预。

2. **模式 B：用户主动点播模式 (Interactive Manual Mode)**
   * 当用户主动发起：“*帮我搜/下某部电影*” 时；
   * AI 不直接私自下载，而是调用检索返回 **Top 10 最顶母盘资源候选清单**（标明格式、画质、无损音轨、体积与促销标签）；
   * 等待用户回复序号确认后，再触发精准下载。

---

## 🚀 GitHub Actions 自动化 CI

本项目已内置 `.github/workflows/docker-build.yml`：
1. 在 GitHub 上创建新仓库 `pt-agent`。
2. 将本地代码推送到 GitHub：
   ```bash
   git remote add origin https://github.com/<你的用户名>/pt-agent.git
   git branch -M main
   git push -u origin main
   ```
3. GitHub Actions 会自动触发构建，并将最新的多架构 Docker 镜像发布至 GitHub Packages (`ghcr.io/<你的用户名>/pt-agent:latest`)。
