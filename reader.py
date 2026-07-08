#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终端小说阅读器 (Stealth Edition)
配合 novel 下载器使用，在终端里低调读小说。

用法:
  python reader.py <小说文件.txt>
  python reader.py <小说文件.txt> --stealth   # 隐身模式：伪装系统日志

键盘控制:
  j / ↓        下滚动一行
  k / ↑        上滚动一行
  d / PageDn   下翻半页
  u / PageUp   上翻半页
  g            跳转到开头
  G            跳转到结尾
  n            下一章
  p            上一章
  c            显示章节目录（可跳转）
  b            添加书签（手动标记）
  '            跳转到书签
  s            切换隐身模式（假日志前缀）
  h            显示/隐藏帮助
  Esc / q      立即退出并清屏（Boss Key）

进度自动保存，下次打开自动恢复。
"""

import os
import sys
import re
import json
import curses
import argparse
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────
PROGRESS_FILE = os.path.expanduser('~/.novel_progress.json')
SCROLL_STEP = 1
PAGE_STEP_RATIO = 0.7  # 翻页比例

# 伪装用
FAKE_TITLE = 'sys-monitor'
FAKE_PREFIXES = [
    'systemd[1]:',
    'kernel:',
    'sshd[842]:',
    'CRON[1024]:',
    'dbus-daemon[501]:',
    'NetworkManager[423]:',
    'systemd-logind[512]:',
    'audit[1023]:',
]


# ─── 进度管理 ───────────────────────────────────────────

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_progress(data):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_book_key(filepath):
    """用文件名作为唯一键"""
    return os.path.basename(filepath)


# ─── 文件解析 ───────────────────────────────────────────

def parse_book(filepath):
    """
    解析下载好的小说 txt，返回:
      chapters: [(title, start_line, end_line), ...]
      lines: [所有行]
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    lines = text.split('\n')
    chapters = []

    # 找所有章节标题行
    chapter_pattern = re.compile(
        r'^(第[0-9零一二三四五六七八九十百千万]+章\s*.*|'
        r'第[0-9零一二三四五六七八九十百千万]+节\s*.*|'
        r'Chapter\s+\d+.*|'
        r'序章|楔子|前言|尾声|番外.*)'
    )

    prev_start = None
    prev_title = '开头'

    for i, line in enumerate(lines):
        stripped = line.strip()
        if chapter_pattern.match(stripped):
            if prev_start is not None and i > prev_start:
                chapters.append((prev_title, prev_start, i - 1))
            prev_title = stripped
            prev_start = i

    # 最后一章
    if prev_start is not None:
        chapters.append((prev_title, prev_start, len(lines) - 1))

    # 如果没解析到章节，整本书作为一个章节
    if not chapters:
        chapters.append(('全文', 0, len(lines) - 1))

    return chapters, lines


def find_current_chapter(chapters, line_idx):
    """根据行号找到当前所在章节索引"""
    for i, (title, start, end) in enumerate(chapters):
        if start <= line_idx <= end:
            return i
    return 0


# ─── Curses UI ──────────────────────────────────────────

def set_terminal_title(title):
    """设置终端窗口标题"""
    sys.stdout.write(f'\033]0;{title}\007')
    sys.stdout.flush()


def run_reader(stdscr, filepath, stealth=False):
    """curses 主循环"""
    # ── 初始化 ──
    curses.curs_set(0)  # 隐藏光标
    stdscr.timeout(-1)  # 阻塞等待输入
    curses.use_default_colors()

    # 加载书籍
    chapters, lines = parse_book(filepath)
    book_key = get_book_key(filepath)
    progress = load_progress()

    # 恢复进度
    saved = progress.get(book_key, {})
    top_line = saved.get('top_line', 0)
    bookmark_line = saved.get('bookmark', None)
    show_help = False
    use_stealth = stealth
    show_chapter_list = False
    chapter_list_offset = 0
    chap_input = ''   # 章节跳转数字输入缓冲
    msg = ''
    msg_timer = 0

    # 确保 top_line 合法
    max_top = max(0, len(lines) - 1)
    top_line = max(0, min(top_line, max_top))

    # 读取章节标题快捷显示
    chapter_index = find_current_chapter(chapters, top_line)

    # 伪终端标题
    set_terminal_title(FAKE_TITLE)

    # ── 主循环 ──
    while True:
        try:
            height, width = stdscr.getmaxyx()
        except Exception:
            break

        if height < 3 or width < 20:
            continue  # 窗口太小

        # 计算阅读区域
        content_width = min(width - 4, 76)  # 窄列阅读
        left_margin = max(0, (width - content_width) // 2)

        stdscr.erase()

        # ── 渲染顶部状态栏 ──
        book_name = os.path.basename(filepath).replace('.txt', '')
        if len(book_name) > content_width - 15:
            book_name = book_name[:content_width - 18] + '...'

        if use_stealth:
            # 伪装模式：顶部显示假日志信息
            header = f' ● {FAKE_TITLE}.service - System Monitoring Daemon'
            try:
                stdscr.addstr(0, max(0, left_margin), header[:content_width], curses.A_DIM)
            except Exception:
                pass
            status = f'   Loaded: loaded (/lib/systemd/system/{FAKE_TITLE}.service; enabled)'
            try:
                stdscr.addstr(1, max(0, left_margin), status[:content_width], curses.A_DIM)
            except Exception:
                pass
        else:
            # 正常模式：显示书名和进度
            total = len(chapters)
            ch_title = chapters[chapter_index][0] if chapter_index < len(chapters) else ''
            if len(ch_title) > 40:
                ch_title = ch_title[:37] + '...'
            progress_text = f'《{book_name}》 {ch_title}  [{chapter_index+1}/{total}]'
            try:
                stdscr.addstr(0, max(0, left_margin), progress_text[:content_width])
            except Exception:
                pass

            # 第二行：进度条
            total_lines = len(lines)
            pct = min(100, int(top_line / max(1, total_lines) * 100))
            bar_width = min(content_width, 60)
            filled = int(bar_width * pct / 100)
            bar = '█' * filled + '░' * (bar_width - filled)
            try:
                stdscr.addstr(1, max(0, left_margin), f'{bar} {pct}%', curses.A_DIM)
            except Exception:
                pass

        # ── 章节目录弹窗 ──
        if show_chapter_list:
            _draw_chapter_list(stdscr, height, width, chapters,
                               chapter_index, chapter_list_offset, chap_input)
        else:
            # ── 渲染正文 ──
            text_start_row = 2 if not use_stealth else 2
            text_end_row = height - 1  # 最后一行留给状态

            row = text_start_row
            for i in range(top_line, len(lines)):
                if row >= text_end_row:
                    break
                line = lines[i]

                if use_stealth:
                    # 隐身模式：加假日志前缀
                    prefix = FAKE_PREFIXES[i % len(FAKE_PREFIXES)]
                    ts_hour = 9 + (i // 60) % 14
                    ts_min = (i * 7) % 60
                    ts_sec = (i * 13) % 60
                    fake_line = f'{prefix} [{ts_hour:02d}:{ts_min:02d}:{ts_sec:02d}] {line}'
                else:
                    fake_line = line

                # 截断以适应宽度
                display = _fit_line(fake_line, content_width)

                try:
                    attr = 0
                    # 章节标题高亮（用下划线代替颜色）
                    if i == chapters[chapter_index][1] if chapter_index < len(chapters) else False:
                        attr |= curses.A_UNDERLINE
                    stdscr.addstr(row, left_margin, display[:width - left_margin], attr)
                except Exception:
                    pass

                row += 1

        # ── 底部状态栏 ──
        try:
            if use_stealth:
                bottom_text = f' PID: {os.getpid()}  Uptime: {top_line//60}h  Tasks: {len(chapters)}  '
            else:
                ch = chapters[chapter_index][0] if chapter_index < len(chapters) else ''
                bottom_text = f' {top_line}/{len(lines)} | {ch} | jk滚动 nd翻页 np换章 q退出 h帮助'
                if bookmark_line is not None:
                    bottom_text += f' 🔖{bookmark_line}'

            if len(bottom_text) > width:
                bottom_text = bottom_text[:width - 1]
            stdscr.addstr(height - 1, 0, bottom_text.ljust(width)[:width], curses.A_REVERSE)
        except Exception:
            pass

        # ── 消息提示 ──
        if msg and msg_timer > 0:
            try:
                msg_attr = curses.A_BOLD
                msg_x = max(0, (width - len(msg)) // 2)
                stdscr.addstr(height - 2, msg_x, msg[:width - msg_x], msg_attr)
            except Exception:
                pass
            msg_timer -= 1
            if msg_timer <= 0:
                msg = ''

        stdscr.refresh()

        # ── 处理输入 ──
        try:
            key = stdscr.getch()
        except Exception:
            continue

        if key == -1:
            continue

        # Boss Key: Esc 立即退出
        if key == 27:  # Esc
            break

        # 帮助面板切换
        if key == ord('h') or key == ord('H'):
            show_help = not show_help
            show_chapter_list = False
            if show_help:
                _draw_help(stdscr, height, width)
                stdscr.refresh()
                stdscr.getch()
                show_help = False
            continue

        if show_chapter_list:
            # 章节目录模式下的按键
            if key == ord('q') or key == 27:
                show_chapter_list = False
                chap_input = ''
            elif key == ord('j') or key == curses.KEY_DOWN:
                chapter_list_offset = min(chapter_list_offset + 1,
                                          max(0, len(chapters) - (height - 4)))
            elif key == ord('k') or key == curses.KEY_UP:
                chapter_list_offset = max(0, chapter_list_offset - 1)
            elif key == ord('d') or key == curses.KEY_NPAGE:  # 章节目录翻页
                step = max(1, (height - 5))
                chapter_list_offset = min(chapter_list_offset + step,
                                          max(0, len(chapters) - (height - 4)))
            elif key == ord('u') or key == curses.KEY_PPAGE:
                step = max(1, (height - 5))
                chapter_list_offset = max(0, chapter_list_offset - step)
            elif key == ord('g'):
                chapter_list_offset = 0
                chap_input = ''
            elif key == ord('G'):
                chapter_list_offset = max(0, len(chapters) - (height - 4))
                chap_input = ''
            # 数字输入：输入数字后回车直接跳到该章节
            elif ord('0') <= key <= ord('9'):
                chap_input += chr(key)
                msg = f'跳转到第 {chap_input} 章...'
                msg_timer = 3
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                chap_input = chap_input[:-1]
                msg = f'跳转到第 {chap_input} 章...' if chap_input else ''
                msg_timer = 2 if chap_input else 0
            elif key in (curses.KEY_ENTER, 10, 13):
                if chap_input:
                    # 按输入的数字跳转
                    target_ch = int(chap_input)
                    if 1 <= target_ch <= len(chapters):
                        chapter_list_offset = target_ch - 1
                        chapter_index = target_ch - 1
                        top_line = chapters[chapter_index][1]
                        show_chapter_list = False
                        msg = f'跳转: 第{target_ch}章'
                    else:
                        msg = f'章节不存在: {target_ch}'
                    msg_timer = 2
                    chap_input = ''
                else:
                    # 回车跳转到当前选中章节
                    selected = chapter_list_offset
                    if 0 <= selected < len(chapters):
                        top_line = chapters[selected][1]
                        chapter_index = selected
                        show_chapter_list = False
                        msg = f'跳转: {chapters[selected][0]}'
                        msg_timer = 2
            elif key == ord('c'):
                show_chapter_list = False
                chap_input = ''
            continue

        # ── 正常阅读模式按键 ──
        visible_lines = max(1, height - 2 - 1)  # 减去顶部和底部

        if key == ord('q'):  # 退出
            break

        elif key == ord('j') or key == curses.KEY_DOWN:
            top_line = min(top_line + SCROLL_STEP, max(0, len(lines) - visible_lines))

        elif key == ord('k') or key == curses.KEY_UP:
            top_line = max(0, top_line - SCROLL_STEP)

        elif key == ord('d') or key == curses.KEY_NPAGE:  # 下翻半页
            step = max(1, int(visible_lines * PAGE_STEP_RATIO))
            top_line = min(top_line + step, max(0, len(lines) - visible_lines))

        elif key == ord('u') or key == curses.KEY_PPAGE:  # 上翻半页
            step = max(1, int(visible_lines * PAGE_STEP_RATIO))
            top_line = max(0, top_line - step)

        elif key == ord('f') or key == ord(' '):  # 下翻整页
            top_line = min(top_line + visible_lines, max(0, len(lines) - visible_lines))

        elif key == ord('b'):  # 上翻整页
            top_line = max(0, top_line - visible_lines)

        elif key == ord('g'):  # 跳转到开头
            top_line = 0

        elif key == ord('G'):  # 跳转到结尾
            top_line = max(0, len(lines) - visible_lines)

        elif key == ord('n'):  # 下一章
            if chapter_index < len(chapters) - 1:
                chapter_index += 1
                top_line = chapters[chapter_index][1]
                msg = f'→ {chapters[chapter_index][0]}'
                msg_timer = 2

        elif key == ord('p'):  # 上一章
            if chapter_index > 0:
                chapter_index -= 1
                top_line = chapters[chapter_index][1]
                msg = f'← {chapters[chapter_index][0]}'
                msg_timer = 2

        elif key == ord('c'):  # 章节目录
            show_chapter_list = True
            chapter_list_offset = chapter_index

        elif key == ord('s'):  # 切换隐身模式
            use_stealth = not use_stealth
            title = FAKE_TITLE if use_stealth else 'novel-reader'
            set_terminal_title(title)
            msg = '隐身模式 ON' if use_stealth else '隐身模式 OFF'
            msg_timer = 2

        elif key == ord('B'):  # 添加/更新书签
            bookmark_line = top_line
            msg = f'书签已保存 (行 {bookmark_line})'
            msg_timer = 2

        elif key == ord('\''):  # 跳转到书签
            if bookmark_line is not None:
                top_line = bookmark_line
                chapter_index = find_current_chapter(chapters, top_line)
                msg = '跳转到书签'
                msg_timer = 2

        elif key == ord('r'):  # 重置进度
            top_line = 0
            chapter_index = 0
            msg = '进度已重置'
            msg_timer = 2

        # 更新当前章节
        chapter_index = find_current_chapter(chapters, top_line)

        # 保存进度
        progress[book_key] = {
            'top_line': top_line,
            'bookmark': bookmark_line,
            'filepath': str(filepath),
        }
        save_progress(progress)

    # ── 退出清理 ──
    set_terminal_title('')
    # 确保清屏（Boss Key 效果）
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


def _fit_line(line, max_width):
    """处理中文宽度，截断到合适长度"""
    if not line:
        return ''
    width = 0
    result = []
    for ch in line:
        w = 2 if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯' else 1
        if width + w > max_width:
            break
        result.append(ch)
        width += w
    # 填充到等宽
    pad = max_width - width
    if pad > 0:
        result.append(' ' * pad)
    return ''.join(result)


def _draw_help(stdscr, height, width):
    """帮助面板"""
    lines = [
        '════════════ 按键帮助 ════════════',
        '',
        '  j / ↓        下滚一行',
        '  k / ↑        上滚一行',
        '  d / PageDn   下翻半页',
        '  u / PageUp   上翻半页',
        '  f / Space    下翻整页',
        '  b            上翻整页',
        '  g            跳到开头',
        '  G            跳到结尾',
        '  n            下一章',
        '  p            上一章',
        '  c            章节目录',
        '  c→输入数字   跳转到指定章',
        '  B            添加书签',
        "  '            跳转书签",
        '  s            切换隐身模式',
        '  h            帮助',
        '  Esc / q      立即退出+清屏',
        '',
        '════════════════════════════════',
        '',
        '  按任意键返回...',
    ]
    panel_h = len(lines) + 2
    panel_w = 42
    start_y = max(0, (height - panel_h) // 2)
    start_x = max(0, (width - panel_w) // 2)

    try:
        for i, line in enumerate(lines):
            y = start_y + i
            if 0 <= y < height:
                stdscr.addstr(y, start_x, line[:width - start_x])
    except Exception:
        pass


def _draw_chapter_list(stdscr, height, width, chapters, current_idx, offset, chap_input=''):
    """章节目录面板"""
    panel_w = min(width - 4, 60)
    panel_h = min(height - 4, len(chapters) + 2)
    start_y = max(0, (height - panel_h) // 2)
    start_x = max(0, (width - panel_w) // 2)

    # 标题
    title = ' 章节目录 (jk移动 du翻页 输数字回车跳转 c返回) '
    try:
        stdscr.addstr(start_y, start_x, title.center(panel_w)[:panel_w], curses.A_REVERSE)
    except Exception:
        pass

    visible = panel_h - 2
    end_offset = min(offset + visible, len(chapters))

    for i, idx in enumerate(range(offset, end_offset)):
        if idx >= len(chapters):
            break
        ch_title, ch_start, _ = chapters[idx]
        if len(ch_title) > panel_w - 6:
            ch_title = ch_title[:panel_w - 9] + '...'

        prefix = ' → ' if idx == current_idx else '   '
        line = f'{prefix}[{idx+1:3d}] {ch_title}'
        try:
            attr = curses.A_REVERSE if idx == current_idx else 0
            stdscr.addstr(start_y + 1 + i, start_x,
                          line.ljust(panel_w)[:panel_w], attr)
        except Exception:
            pass

    # 底部信息
    if chap_input:
        info = f' 跳转到第 {chap_input} 章... | {offset+1}-{end_offset} / {len(chapters)} '
    else:
        info = f' {offset+1}-{end_offset} / {len(chapters)} 章 | 输入数字快速跳转 '
    try:
        stdscr.addstr(start_y + panel_h - 1, start_x,
                      info.center(panel_w)[:panel_w], curses.A_REVERSE)
    except Exception:
        pass


# ─── 入口 ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='终端小说阅读器 (Stealth Edition)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python reader.py 三体.txt
  python reader.py 三体.txt --stealth   # 隐身模式

隐身模式:
  - 窗口标题伪装为 sys-monitor
  - 每行添加假系统日志前缀
  - 看起来像在看服务器日志
  - Esc 一键退出+清屏

配合 snapd_spider.py 使用流程:
  1. python snapd_spider.py <book_id>     # 下载小说
  2. python reader.py <书名>.txt          # 终端阅读
        """
    )
    parser.add_argument('file', help='小说 txt 文件路径')
    parser.add_argument('--stealth', action='store_true',
                        help='隐身模式（伪装成系统日志）')
    parser.add_argument('--reset', action='store_true',
                        help='重置阅读进度')
    args = parser.parse_args()

    filepath = os.path.abspath(args.file)
    if not os.path.exists(filepath):
        print(f'❌ 文件不存在: {filepath}')
        sys.exit(1)

    # 重置进度
    if args.reset:
        progress = load_progress()
        book_key = get_book_key(filepath)
        if book_key in progress:
            del progress[book_key]
            save_progress(progress)
            print(f'✅ 已重置《{os.path.basename(filepath)}》的阅读进度')
        else:
            print(f'📭 没有《{os.path.basename(filepath)}》的进度记录')

    # 启动 curses
    try:
        curses.wrapper(run_reader, filepath, args.stealth)
    except KeyboardInterrupt:
        # Ctrl-C 也清屏
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write('\033[2J\033[H')
        print(f'Error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
