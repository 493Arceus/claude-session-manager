"""Claude 会话管理器 - Claude Code CLI 会话的图形化管理工具."""
from __future__ import annotations

import os
import sys

# PyInstaller 打包后需要显式设置 Tcl/Tk 库路径
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # PyInstaller 标准路径
    _tcl = os.path.join(_meipass, "_tcl_data")
    _tk = os.path.join(_meipass, "_tk_data")
    # 备选路径（旧版或自定义打包）
    _tcl2 = os.path.join(_meipass, "tcl", "tcl8.6")
    _tk2 = os.path.join(_meipass, "tk", "tk8.6")
    if os.path.isdir(_tcl):
        os.environ["TCL_LIBRARY"] = _tcl
    elif os.path.isdir(_tcl2):
        os.environ["TCL_LIBRARY"] = _tcl2
    if os.path.isdir(_tk):
        os.environ["TK_LIBRARY"] = _tk
    elif os.path.isdir(_tk2):
        os.environ["TK_LIBRARY"] = _tk2

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# 检查 customtkinter 是否已安装
try:
    import customtkinter as ctk
except ImportError:
    print("错误: 未安装 customtkinter。")
    print("请安装: pip install customtkinter")
    print("或运行: pip install -r requirements.txt")
    sys.exit(1)

from models import Project, Session, format_relative_time, get_project_display_name
from scanner import delete_session, get_session_preview_messages, scan_all_projects
from utils import (
    format_file_size,
    launch_claude_resume,
    launch_claude_session,
    open_in_file_manager,
    truncate_text,
)

# 主题设置
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

COLOR_ACTIVE = "#2ecc71"
COLOR_CARD_BORDER = "#cccccc"
COLOR_CARD_HOVER = ("#e8e8e8", "#3b3b3b")
COLOR_CARD_NORMAL = ("#f5f5f5", "#2b2b2b")
COLOR_CARD_SELECTED = ("#dbeafe", "#1e3a5f")
COLOR_CARD_SELECTED_BORDER = ("#3b82f6", "#60a5fa")

FONT_TITLE = ("Microsoft YaHei", "PingFang SC", "Segoe UI", "Helvetica Neue", "Arial")
FONT_BODY = ("Microsoft YaHei", "PingFang SC", "Segoe UI", "Helvetica Neue", "Arial")


class SessionCard(ctk.CTkFrame):
    """可点击的会话卡片."""

    # 需要跳过绑定的控件类型（避免干扰交互控件）
    _SKIP_BIND_TYPES = (ctk.CTkButton, ctk.CTkEntry, ctk.CTkTextbox, ctk.CTkOptionMenu, ctk.CTkComboBox)

    def __init__(self, master, session: Session, on_click, **kwargs):
        super().__init__(master, **kwargs)
        self.session = session
        self.on_click = on_click
        self.is_selected = False
        self._click_debounce = False

        self.configure(
            corner_radius=10,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
            fg_color=COLOR_CARD_NORMAL,
        )

        # 标题行
        self.title_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.title_frame.pack(fill="x", padx=12, pady=(10, 2))

        # 活跃状态指示点
        self.dot_label = ctk.CTkLabel(
            self.title_frame,
            text="●" if session.is_active else "",
            font=(FONT_BODY, 12),
            text_color=COLOR_ACTIVE,
            width=20,
        )
        self.dot_label.pack(side="left")

        # 会话标题
        self.title_label = ctk.CTkLabel(
            self.title_frame,
            text=session.display_title(),
            font=(FONT_TITLE, 14, "bold"),
            anchor="w",
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        # 项目路径
        self.path_label = ctk.CTkLabel(
            self,
            text=session.project_path,
            font=(FONT_BODY, 11),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.path_label.pack(fill="x", padx=32, pady=(0, 2))

        # 信息行 (消息数 + 时间)
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.pack(fill="x", padx=32, pady=(0, 10))

        if session.message_count:
            msg_text = f"{session.message_count} 条消息"
        else:
            msg_text = "无消息"

        self.msg_label = ctk.CTkLabel(
            self.info_frame,
            text=msg_text,
            font=(FONT_BODY, 11),
            text_color=("gray50", "gray70"),
        )
        self.msg_label.pack(side="left")

        self.sep_label = ctk.CTkLabel(
            self.info_frame,
            text="  ·  ",
            font=(FONT_BODY, 11),
            text_color=("gray50", "gray70"),
        )
        self.sep_label.pack(side="left")

        self.time_label = ctk.CTkLabel(
            self.info_frame,
            text=session.display_time(),
            font=(FONT_BODY, 11),
            text_color=("gray50", "gray70"),
        )
        self.time_label.pack(side="left")

        if session.is_active:
            self.active_label = ctk.CTkLabel(
                self.info_frame,
                text="  (运行中)",
                font=(FONT_BODY, 11, "bold"),
                text_color=COLOR_ACTIVE,
            )
            self.active_label.pack(side="left")

        # 悬停效果（tkinter 默认会冒泡到父级）
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        # 点击事件递归绑定到所有子控件（CustomTkinter 内部 Canvas 可能不冒泡）
        self._bind_recursive(self, "<Button-1>", self._handle_click)

    def _bind_recursive(self, widget, event, handler):
        """为 widget 及其所有后代递归绑定事件，跳过交互控件."""
        if not isinstance(widget, self._SKIP_BIND_TYPES):
            widget.bind(event, handler)
        for child in widget.winfo_children():
            self._bind_recursive(child, event, handler)

    def _handle_click(self, event=None):
        """处理点击事件，防抖避免重复触发."""
        if self._click_debounce:
            return "break"
        self._click_debounce = True
        self.after(100, self._reset_debounce)
        self.on_click(self.session)
        return "break"

    def _reset_debounce(self):
        self._click_debounce = False

    def _on_enter(self, event=None):
        if not self.is_selected:
            self.configure(fg_color=COLOR_CARD_HOVER)

    def _on_leave(self, event=None):
        if not self.is_selected:
            self.configure(fg_color=COLOR_CARD_NORMAL)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(
                fg_color=COLOR_CARD_SELECTED,
                border_color=COLOR_CARD_SELECTED_BORDER,
            )
        else:
            self.configure(
                fg_color=COLOR_CARD_NORMAL,
                border_color=COLOR_CARD_BORDER,
            )


class ProjectSidebarItem(ctk.CTkFrame):
    """侧边栏中的项目条目."""

    def __init__(self, master, project: Project, on_click, **kwargs):
        super().__init__(master, **kwargs)
        self.project = project
        self.on_click = on_click
        self.is_selected = False

        self.configure(fg_color="transparent", corner_radius=6, height=36)
        self.pack_propagate(False)

        display_name = get_project_display_name(project.decoded_path)
        count_text = f" ({project.session_count()})"

        self.name_label = ctk.CTkLabel(
            self,
            text=display_name + count_text,
            font=(FONT_BODY, 12),
            anchor="w",
        )
        self.name_label.pack(side="left", padx=10, fill="y")

        self.bind("<Button-1>", self._handle_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _handle_click(self, event=None):
        self.on_click(self.project)
        return "break"

    def _on_enter(self, event=None):
        if not self.is_selected:
            self.configure(fg_color=("#e8e8e8", "#3b3b3b"))

    def _on_leave(self, event=None):
        if not self.is_selected:
            self.configure(fg_color="transparent")

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.configure(fg_color=COLOR_CARD_SELECTED)
            self.name_label.configure(font=(FONT_BODY, 12, "bold"))
        else:
            self.configure(fg_color="transparent")
            self.name_label.configure(font=(FONT_BODY, 12))


class SessionManagerApp(ctk.CTk):
    """主应用程序窗口."""

    def __init__(self):
        super().__init__()

        self.title("Claude 会话管理器")
        self.geometry("1200x700")
        self.minsize(900, 500)

        # 数据
        self.projects: list[Project] = []
        self.filtered_sessions: list[Session] = []
        self.selected_project: Project | None = None
        self.selected_session: Session | None = None
        self.session_cards: list[SessionCard] = []
        self.project_items: list[ProjectSidebarItem] = []

        # 构建 UI
        self._build_header()
        self._build_main_layout()

        # 初始加载
        self.after(100, self._load_data)

    def _build_header(self):
        """构建顶部标题栏."""
        self.header = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.title_label = ctk.CTkLabel(
            self.header,
            text="Claude 会话管理器",
            font=(FONT_TITLE, 18, "bold"),
        )
        self.title_label.pack(side="left", padx=20, pady=10)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.search_entry = ctk.CTkEntry(
            self.header,
            placeholder_text="搜索会话...",
            width=300,
            height=32,
            textvariable=self.search_var,
        )
        self.search_entry.pack(side="left", padx=10, pady=9)

        self.refresh_btn = ctk.CTkButton(
            self.header,
            text="🔄 刷新",
            width=80,
            height=32,
            command=self._load_data,
        )
        self.refresh_btn.pack(side="left", padx=5, pady=9)

        self.resume_btn = ctk.CTkButton(
            self.header,
            text="▶ 继续最近",
            width=100,
            height=32,
            command=self._resume_latest,
        )
        self.resume_btn.pack(side="left", padx=5, pady=9)

        self.theme_btn = ctk.CTkButton(
            self.header,
            text="🌙",
            width=40,
            height=32,
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="right", padx=20, pady=9)

    def _build_main_layout(self):
        """构建三栏主布局."""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        # 左侧边栏
        self.sidebar = ctk.CTkFrame(self.main_frame, width=220, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.sidebar_title = ctk.CTkLabel(
            self.sidebar,
            text="项目",
            font=(FONT_TITLE, 13, "bold"),
        )
        self.sidebar_title.pack(anchor="w", padx=15, pady=(15, 5))

        self.all_projects_btn = ctk.CTkButton(
            self.sidebar,
            text="📁 全部会话",
            height=30,
            anchor="w",
            command=self._show_all_sessions,
        )
        self.all_projects_btn.pack(fill="x", padx=10, pady=2)

        self.projects_container = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            scrollbar_button_color=("gray60", "gray40"),
        )
        self.projects_container.pack(fill="both", expand=True, padx=5, pady=5)

        # 中间 - 会话列表
        self.center_frame = ctk.CTkFrame(self.main_frame, corner_radius=0)
        self.center_frame.pack(side="left", fill="both", expand=True)

        self.center_header = ctk.CTkFrame(self.center_frame, height=40, corner_radius=0, fg_color="transparent")
        self.center_header.pack(fill="x", side="top")
        self.center_header.pack_propagate(False)

        self.center_title = ctk.CTkLabel(
            self.center_header,
            text="会话列表",
            font=(FONT_TITLE, 15, "bold"),
        )
        self.center_title.pack(side="left", padx=15, pady=8)

        self.center_count = ctk.CTkLabel(
            self.center_header,
            text="",
            font=(FONT_BODY, 12),
            text_color=("gray50", "gray70"),
        )
        self.center_count.pack(side="left", padx=5, pady=8)

        self.sort_menu = ctk.CTkOptionMenu(
            self.center_header,
            values=["最近", "消息数", "名称"],
            width=100,
            height=28,
            command=self._on_sort_change,
        )
        self.sort_menu.pack(side="right", padx=15, pady=6)
        self.sort_menu.set("最近")

        self.sessions_scroll = ctk.CTkScrollableFrame(
            self.center_frame,
            fg_color="transparent",
            scrollbar_button_color=("gray60", "gray40"),
        )
        self.sessions_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        # 右侧面板 - 详情
        self.details_panel = ctk.CTkFrame(self.main_frame, width=300, corner_radius=0)
        self.details_panel.pack(side="right", fill="y")
        self.details_panel.pack_propagate(False)

        self._build_details_panel()

    def _build_details_panel(self):
        """构建右侧详情面板 (未选择会话时显示)."""
        self.details_empty = ctk.CTkLabel(
            self.details_panel,
            text="选择一个会话\n查看详情",
            font=(FONT_BODY, 14),
            text_color=("gray50", "gray70"),
            justify="center",
        )
        self.details_empty.pack(expand=True)

    def _clear_details_panel(self):
        """安全清除详情面板所有子控件."""
        for widget in self.details_panel.winfo_children():
            widget.pack_forget()
            widget.destroy()
        self.details_panel.update_idletasks()

    def _clear_session_cards(self):
        """安全清除所有会话卡片."""
        for card in self.session_cards:
            card.pack_forget()
            card.destroy()
        self.session_cards.clear()
        self.sessions_scroll.update_idletasks()

    def _show_session_details(self, session: Session):
        """在详情面板中显示会话信息."""
        self._clear_details_panel()

        scroll = ctk.CTkScrollableFrame(
            self.details_panel,
            fg_color="transparent",
            scrollbar_button_color=("gray60", "gray40"),
        )
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # 标题
        ctk.CTkLabel(
            scroll,
            text=session.display_title(),
            font=(FONT_TITLE, 16, "bold"),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(0, 5))

        # 会话 ID
        ctk.CTkLabel(
            scroll,
            text=f"ID: {session.short_id()}",
            font=(FONT_BODY, 10),
            text_color=("gray50", "gray70"),
        ).pack(anchor="w", pady=(0, 10))

        # 信息网格
        info_items = [
            ("项目路径", session.project_path),
            ("消息数", str(session.message_count)),
            ("文件大小", format_file_size(session.file_size)),
            ("状态", "运行中" if session.is_active else "未运行"),
        ]

        for label, value in info_items:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{label}:", font=(FONT_BODY, 11, "bold"), width=60, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value, font=(FONT_BODY, 11), wraplength=210, justify="left").pack(side="left", fill="x", expand=True)

        if session.first_timestamp:
            ctk.CTkLabel(
                scroll,
                text=f"创建于: {session.first_timestamp.strftime('%Y-%m-%d %H:%M')}",
                font=(FONT_BODY, 11),
                text_color=("gray50", "gray70"),
            ).pack(anchor="w", pady=(10, 0))

        if session.last_timestamp:
            ctk.CTkLabel(
                scroll,
                text=f"最后活跃: {session.last_timestamp.strftime('%Y-%m-%d %H:%M')}",
                font=(FONT_BODY, 11),
                text_color=("gray50", "gray70"),
            ).pack(anchor="w", pady=(2, 10))

        # 最后提示预览
        if session.last_prompt:
            ctk.CTkLabel(
                scroll,
                text="最后输入:",
                font=(FONT_BODY, 11, "bold"),
            ).pack(anchor="w", pady=(10, 2))

            prompt_text = ctk.CTkTextbox(scroll, height=60, wrap="word", font=(FONT_BODY, 11))
            prompt_text.pack(fill="x", pady=(0, 10))
            prompt_text.insert("1.0", truncate_text(session.last_prompt, 300))
            prompt_text.configure(state="disabled")

        # 最近消息预览
        ctk.CTkLabel(
            scroll,
            text="最近消息:",
            font=(FONT_BODY, 11, "bold"),
        ).pack(anchor="w", pady=(10, 2))

        preview_messages = get_session_preview_messages(Path(session.file_path), count=3)
        if preview_messages:
            for msg in preview_messages:
                msg_frame = ctk.CTkFrame(scroll, fg_color=("#f0f0f0", "#333333"), corner_radius=6)
                msg_frame.pack(fill="x", pady=2)

                if msg["type"] == "user":
                    type_label = "用户"
                    color = "#3b82f6"
                elif msg["type"] == "assistant":
                    type_label = "助手"
                    color = "#10b981"
                else:
                    type_label = msg["type"]
                    color = "#f59e0b"

                ctk.CTkLabel(
                    msg_frame,
                    text=type_label,
                    font=(FONT_BODY, 10, "bold"),
                    text_color=color,
                ).pack(anchor="w", padx=8, pady=(4, 0))

                ctk.CTkLabel(
                    msg_frame,
                    text=truncate_text(msg["preview"], 200),
                    font=(FONT_BODY, 10),
                    wraplength=250,
                    justify="left",
                ).pack(anchor="w", padx=8, pady=(0, 4))
        else:
            ctk.CTkLabel(
                scroll,
                text="无预览可用",
                font=(FONT_BODY, 11),
                text_color=("gray50", "gray70"),
            ).pack(anchor="w")

        # 操作按钮
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 5))

        ctk.CTkButton(
            btn_frame,
            text="▶ 恢复会话",
            command=lambda: self._resume_session(session),
        ).pack(fill="x", pady=2)

        ctk.CTkButton(
            btn_frame,
            text="⎇ 分叉会话",
            command=lambda: self._fork_session(session),
        ).pack(fill="x", pady=2)

        ctk.CTkButton(
            btn_frame,
            text="📂 打开所在文件夹",
            command=lambda: open_in_file_manager(os.path.dirname(session.file_path)),
        ).pack(fill="x", pady=2)

        ctk.CTkButton(
            btn_frame,
            text="🗑 删除会话",
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            command=lambda: self._delete_session(session),
        ).pack(fill="x", pady=2)

    def _load_data(self):
        """在后台线程中加载会话."""
        self.refresh_btn.configure(state="disabled", text="⏳ 加载中...")

        def load():
            try:
                projects = scan_all_projects()
                self.after(0, lambda: self._on_data_loaded(projects))
            except Exception as e:
                self.after(0, lambda: self._on_load_error(str(e)))

        threading.Thread(target=load, daemon=True).start()

    def _on_data_loaded(self, projects: list[Project]):
        """处理加载完成的数据."""
        self.projects = projects
        self.refresh_btn.configure(state="normal", text="🔄 刷新")

        # 更新侧边栏
        for item in self.project_items:
            item.pack_forget()
            item.destroy()
        self.project_items = []

        for project in projects:
            item = ProjectSidebarItem(
                self.projects_container,
                project,
                on_click=self._on_project_select,
            )
            item.pack(fill="x", pady=1)
            self.project_items.append(item)

        self._show_all_sessions()

    def _on_load_error(self, error: str):
        """处理加载错误."""
        self.refresh_btn.configure(state="normal", text="🔄 刷新")
        messagebox.showerror("错误", f"加载会话失败:\n{error}")

    def _show_all_sessions(self):
        """显示所有项目中的全部会话."""
        self.selected_project = None
        self._update_project_selection()

        all_sessions: list[Session] = []
        for project in self.projects:
            all_sessions.extend(project.sessions)

        self._display_sessions(all_sessions, "全部会话")

    def _on_project_select(self, project: Project):
        """处理项目选择."""
        self.selected_project = project
        self._update_project_selection()
        display_name = get_project_display_name(project.decoded_path)
        self._display_sessions(project.sessions, display_name)

    def _update_project_selection(self):
        """更新侧边栏选中状态."""
        for item in self.project_items:
            item.set_selected(item.project == self.selected_project)

    def _display_sessions(self, sessions: list[Session], title: str):
        """在中间面板显示会话列表（含排序）."""
        sort_mode = self.sort_menu.get()
        sessions = list(sessions)

        if sort_mode == "最近":
            from datetime import datetime
            sessions.sort(key=lambda s: s.last_timestamp or datetime.min, reverse=True)
        elif sort_mode == "消息数":
            sessions.sort(key=lambda s: s.message_count, reverse=True)
        elif sort_mode == "名称":
            sessions.sort(key=lambda s: s.display_title().lower())

        # 更新标题和计数
        self.center_title.configure(text=title)
        self.center_count.configure(text=f"({len(sessions)})")

        # 安全清除旧卡片
        self._clear_session_cards()

        # 清除选择状态
        self.selected_session = None
        self._clear_details_panel()
        self._build_details_panel()

        # 批量创建新卡片
        self.filtered_sessions = sessions
        for session in sessions:
            card = SessionCard(
                self.sessions_scroll,
                session,
                on_click=self._on_session_select,
            )
            card.pack(fill="x", pady=4)
            self.session_cards.append(card)

    def _on_session_select(self, session: Session):
        """处理会话卡片点击."""
        if self.selected_session == session:
            return  # 避免重复点击同一会话时的闪烁

        self.selected_session = session
        for card in self.session_cards:
            card.set_selected(card.session == session)
        self._show_session_details(session)

    def _on_search(self, *args):
        """按搜索文本过滤会话."""
        query = self.search_var.get().lower().strip()

        if not query:
            if self.selected_project:
                display_name = get_project_display_name(self.selected_project.decoded_path)
                self._display_sessions(self.selected_project.sessions, display_name)
            else:
                self._show_all_sessions()
            return

        all_sessions: list[Session] = []
        for project in self.projects:
            all_sessions.extend(project.sessions)

        filtered = [
            s for s in all_sessions
            if query in s.display_title().lower()
            or query in s.project_path.lower()
            or (s.last_prompt and query in s.last_prompt.lower())
        ]

        self._display_sessions(filtered, f"搜索: '{query}'")

    def _on_sort_change(self, value):
        """处理排序模式变化."""
        if self.selected_project:
            self._display_sessions(self.selected_project.sessions, get_project_display_name(self.selected_project.decoded_path))
        else:
            all_sessions = []
            for p in self.projects:
                all_sessions.extend(p.sessions)
            self._display_sessions(all_sessions, "全部会话")

    def _resume_latest(self):
        """继续最近活跃的会话."""
        if not self.projects:
            messagebox.showinfo("无会话", "未找到任何会话。")
            return

        latest: Session | None = None
        for project in self.projects:
            for session in project.sessions:
                if not latest or (session.last_timestamp and latest.last_timestamp and session.last_timestamp > latest.last_timestamp):
                    latest = session

        if latest:
            self._resume_session(latest)

    def _resume_session(self, session: Session):
        """恢复特定会话."""
        try:
            launch_claude_session(session.session_id, session.project_path, mode="resume")
        except Exception as e:
            messagebox.showerror("错误", f"启动会话失败:\n{e}")

    def _fork_session(self, session: Session):
        """分叉会话."""
        if messagebox.askyesno("分叉会话", f"从 '{session.display_title()}' 创建一个新的分叉会话?"):
            try:
                launch_claude_session(session.session_id, session.project_path, mode="fork")
            except Exception as e:
                messagebox.showerror("错误", f"分叉会话失败:\n{e}")

    def _delete_session(self, session: Session):
        """删除会话 (需确认)."""
        if messagebox.askyesno(
            "删除会话",
            f"确定要删除 '{session.display_title()}' 吗?\n\n此操作无法撤销。",
        ):
            if delete_session(session):
                for project in self.projects:
                    if session in project.sessions:
                        project.sessions.remove(session)
                        break
                self._on_search()
                messagebox.showinfo("已删除", "会话已成功删除。")
            else:
                messagebox.showerror("错误", "删除会话失败。")

    def _toggle_theme(self):
        """切换亮/暗主题."""
        current = ctk.get_appearance_mode()
        new_mode = "Dark" if current == "Light" else "Light"
        ctk.set_appearance_mode(new_mode)
        self.theme_btn.configure(text="☀️" if new_mode == "Light" else "🌙")


def main():
    app = SessionManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
