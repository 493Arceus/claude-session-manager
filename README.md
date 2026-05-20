# Claude Session Manager

Claude Code CLI 的图形化会话管理工具。

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 功能

- **会话浏览** - 自动扫描 `~/.claude/projects/` 下的所有会话，按项目分组展示
- **会话搜索** - 支持按标题、项目路径、内容关键词过滤
- **恢复会话** - 一键在新终端窗口中恢复历史会话 (`claude --resume`)
- **分叉会话** - 从现有会话创建分叉 (`claude --resume --fork-session`)
- **删除会话** - 删除会话及相关数据（带确认对话框）
- **详情预览** - 右侧面板显示消息数、文件大小、最近消息预览
- **主题切换** - 支持亮/暗主题
- **排序** - 按最近活动时间、消息数、名称排序

## 界面

```
┌─────────────────────────────────────────────────────────────┐
│ Claude 会话管理器    [搜索...]  [刷新] [继续最近]     [🌙]  │
├──────────┬─────────────────────────────┬──────────────────┤
│ 项目     │  会话列表                    │  详情            │
│          │                              │                  │
│ 📁 全部  │  ● Session Title             │  项目路径        │
│          │    D:\project\path            │  消息数          │
│ cc-tools │    15 条消息  ·  2 小时前    │  文件大小        │
│ hermes   │                              │  状态            │
│ ...      │  Session Title               │                  │
│          │    ...                       │  最后输入        │
│          │                              │                  │
│          │                              │  最近消息        │
│          │                              │                  │
│          │                              │  [▶ 恢复会话]    │
│          │                              │  [⎇ 分叉会话]    │
│          │                              │  [📂 打开文件夹]  │
│          │                              │  [🗑 删除会话]    │
└──────────┴─────────────────────────────┴──────────────────┘
```

## 安装

### 直接运行（推荐）

从 [Releases](https://github.com/493Arceus/claude-session-manager/releases) 下载对应系统的可执行文件，双击运行。

### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/493Arceus/claude-session-manager.git
cd claude-session-manager

# 安装依赖
pip install -r requirements.txt

# 运行
python session_manager.py
```

## 构建

### 打包为可执行文件

```bash
pip install -r requirements.txt
python build.py
```

构建完成后，可执行文件位于 `dist/ClaudeSessionManager(.exe)`。

## 项目结构

```
claude-session-manager/
├── session_manager.py      # 主程序入口 + UI
├── scanner.py              # 会话扫描/解析逻辑
├── models.py               # 数据模型 (Session, Project)
├── utils.py                # 工具函数
├── build.py                # PyInstaller 打包脚本
├── requirements.txt        # Python 依赖
├── .gitignore              # Git 忽略规则
└── README.md               # 本文件
```

## 工作原理

Claude Code CLI 的会话存储在 `~/.claude/projects/` 目录下：

- 每个项目是一个子目录（目录名由工作路径编码而成）
- 每个会话是一个 `.jsonl` 文件，文件名是会话 UUID
- 活跃会话在 `~/.claude/sessions/<pid>.json` 中跟踪

本工具读取这些文件，提取会话元数据（标题、消息数、时间戳等），并通过 `claude --resume <session_id>` 命令恢复会话。

## 系统要求

- **Windows**: Windows 10+
- **macOS**: macOS 12+
- **Linux**: 带有 GTK 的桌面环境
- **Python**: 3.10+（仅源码运行需要）

## 许可证

[MIT](LICENSE)
