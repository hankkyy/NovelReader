# NovelReader

笔趣阁小说下载器 + 终端阅读器。一站解决小说下载和终端摸鱼阅读。

## 项目结构

```
biquge/
├── novel              # 小说下载器（Playwright 版）
├── reader.py          # 终端阅读器（Stealth Edition）
├── requirements.txt   # Python 依赖
└── output/            # 下载的小说存放处（git 忽略）
```

## 安装

```bash
cd ~/Desktop/biquge

# 1. 创建虚拟环境
python3 -m venv venv

# 2. 安装 Python 依赖
venv/bin/pip install -r requirements.txt

# 3. 安装 Playwright 浏览器（二选一）
venv/bin/python3 -m playwright install chromium
# 或者直接用系统 Chrome（macOS 通常已安装）
```

> **前置条件：** 需要系统已安装 Google Chrome（macOS 通常在 `/Applications/Google Chrome.app`）。

---

## 一、下载小说 (`novel`)

### 基本原理

使用 Playwright 驱动系统 Chrome 浏览器，渲染目标网站的 JavaScript 后提取章节正文。笔趣阁镜像站使用 Cloudflare + AJAX 动态加载内容，传统 HTTP 请求无法获取正文，必须用真实浏览器渲染。

- 复用一个浏览器实例，避免每章启动
- 每 80 章自动重启浏览器，防止内存泄漏
- **断点续传**：中断后重新运行，自动跳过已下载章节
- 单章失败最多重试 2 次

### 用法

```bash
venv/bin/python3 novel 188981                    # 下载全部
venv/bin/python3 novel 188981 --start 419        # 从指定章节开始（续传）
venv/bin/python3 novel 188981 --start 419 --end 500  # 下载指定范围
venv/bin/python3 novel 188981 --start 419 -o ./output  # 指定输出目录
```

### 如何获取书 ID

1. 打开 https://m.snapd.net 搜索小说名
2. 进入小说详情页，URL 格式为 `m.snapd.net/read/{书ID}/`
3. 例如 `m.snapd.net/read/188981/` → 书 ID 是 `188981`

### 支持的站点

| 站点 | 章节数 | 需要 JS | 备注 |
|------|--------|---------|------|
| `m.snapd.net` | 最多（1000+） | 是 | **推荐**，更新最及时 |
| `www.biquge.tw` | 较少（<200） | 否 | 不需要 Playwright，但章节不全 |

> `biquge.tw` 可用 `biquge_spider.py`（独立脚本，不依赖 Playwright）。

---

## 二、终端阅读器 (`reader.py`)

### 基本原理

基于 `curses` 的终端小说阅读器。解析下载好的 txt 文件，自动识别章节标题（第X章），Vim 风格快捷键，阅读进度自动保存到 `~/.novel_progress.json`。

- 自动识别章节，支持 n/p 快速切换
- 进度持久化，断点续读
- 隐身模式：伪装成系统监控日志（`sys-monitor.service`）
- Boss Key：Esc 一键退出并清屏

### 用法

```bash
venv/bin/python3 reader.py output/书名.txt            # 正常模式
venv/bin/python3 reader.py output/书名.txt --stealth  # 隐身模式
venv/bin/python3 reader.py output/书名.txt --reset    # 重置进度
```

### 完整快捷键

#### 阅读模式

| 按键 | 功能 |
|------|------|
| `j` / `↓` | 下滚一行 |
| `k` / `↑` | 上滚一行 |
| `d` / `PageDn` | 下翻半页 |
| `u` / `PageUp` | 上翻半页 |
| `f` / `Space` | 下翻整页 |
| `b` | 上翻整页 |
| `g` | 跳到开头 |
| `G` | 跳到结尾 |
| `n` | 下一章 |
| `p` | 上一章 |
| `c` | 打开章节目录 |
| `c→输入数字→回车` | **直接跳转到指定章**（如 `419` 回车 → 第419章） |
| `B` | 添加/更新书签 |
| `'` | 跳转到书签 |
| `s` | 切换隐身模式 |
| `h` | 帮助 |
| `Esc` / `q` | **立即退出并清屏**（Boss Key） |

#### 章节目录模式

| 按键 | 功能 |
|------|------|
| `j` / `k` / `↑` / `↓` | 移动 |
| `d` / `u` | 翻页 |
| `g` / `G` | 第一/最后一章 |
| `数字` + `回车` | **跳到指定章** |
| `回车` | 跳当前高亮章 |
| `c` / `Esc` | 返回阅读 |

---

## 三、隐身模式

按 `s` 切换后：

- 窗口标题 → `sys-monitor`
- 顶部 → 假 systemd 服务信息
- 每行前 → 假系统日志前缀
- 底部 → 假 PID 和 Uptime
- `Esc` → 一键退出+清屏

```
 ● sys-monitor.service - System Monitoring Daemon
   Loaded: loaded (/lib/systemd/system/sys-monitor.service; enabled)
kernel: [09:32:13] 这届的武林大会让众人非常尽兴。
sshd[842]: [09:32:20] 因为有许多的场面，都是他们在以往不曾看到过的。
```

---

## 四、完整工作流

```bash
cd ~/Desktop/biquge

# Step 1: 下载
venv/bin/python3 novel 188981 --start 419

# Step 2: 阅读
venv/bin/python3 reader.py output/太后娘娘请开门，奴才来请安了.txt
```

---

## 五、技术架构

### novel 下载器

```
用户输入 book_id + 参数
  → sync_playwright().start()
  → browser = chromium.launch(channel='chrome', headless=True)
  → 获取书籍信息页 → 解析书名/作者/总章节数
  → 循环逐章:
       page.goto(url) → JS 渲染
       page.content() → 获取 HTML
       BeautifulSoup 解析 div#chaptercontent
       <br> 分段 → 过滤广告 → 写入 txt
  → 每 80 章重启浏览器防内存泄漏
```

### reader.py 阅读器

```
打开 txt 文件
  → 正则解析章节标题（第X章）
  → 构建章节索引 [(title, start_line, end_line), ...]
  → curses 主循环:
       渲染顶部（书名+进度条）
       渲染正文（从 top_line 开始）
       渲染底部（快捷键提示）
       监听键盘 → 更新位置 → 保存进度
```

### 进度文件格式 (`~/.novel_progress.json`)

```json
{
  "太后娘娘请开门，奴才来请安了.txt": {
    "top_line": 12345,
    "bookmark": 10000,
    "filepath": "/Users/xxx/biquge/output/太后娘娘请开门，奴才来请安了.txt"
  }
}
```

---

## 六、Agent 接手指南

如果需要 AI Agent 接手维护或二次开发：

### 关键文件
- `novel` — 下载器主逻辑。核心函数：`download_novel(book_id, start, end, output_dir)`
- `reader.py` — 阅读器主逻辑。核心函数：`run_reader(stdscr, filepath, stealth)`
- `~/.novel_progress.json` — 阅读进度持久化文件

### 添加新的小说源
在 `novel` 中增加站点判断逻辑，修改 `parse_chapter_html()` 适配新站点的 HTML 结构。

### 添加新功能
- 阅读器支持搜索：在 `run_reader()` 中添加 `/` 键触发的搜索模式
- 并发下载：开多个 tab 同时下载不同章节
- EPUB 导出：添加 `ebooklib` 依赖，将 txt 转为 epub

---

## 七、常见问题

**Q: 下载很慢？**
A: Playwright 启动浏览器 + JS 渲染每章约 3-8 秒。718 章约 30-60 分钟。支持断点续传，随时中断。

**Q: 中断会丢进度吗？**
A: 不会。重跑相同命令自动跳过已下载章节。

**Q: 进度存在哪？**
A: `~/.novel_progress.json`，按文件名关联。
