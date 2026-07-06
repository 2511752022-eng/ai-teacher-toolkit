# AI Teacher Toolkit

物理老师的 AI 工具箱。一条命令完成环境修复、MCP 管理、视频脚本生成。

## 安装

```bash
pip install -e ~/ai-teacher-toolkit
```

## 使用

```bash
# 环境检测修复
ai-teacher env check              # 检测中文 Windows 环境问题
ai-teacher env fix                # 一键修复

# MCP 插件管理
ai-teacher mcp install <repo-url> # 装 MCP 插件
ai-teacher mcp list               # 查看已装
ai-teacher mcp remove <name>      # 卸载

# 视频脚本生成（需配火山引擎 ARK）
ai-teacher video script "牛顿第三定律"    # → 7镜头完整教学脚本
ai-teacher video script "自由落体"       # 每个镜头含画面/旁白/时长/转场
ai-teacher video storyboard "光的折射"   # → 分镜描述

# 飞书 bot 部署
ai-teacher deploy feishu          # 部署教学助手到飞书
```

## 配置

```bash
# 火山引擎 ARK（视频脚本需要）
export ARK_API_KEY="your-api-key"
export ARK_ENDPOINT="ep-xxxxx"  # 可选，默认用视觉 endpoint
```

配置文件在 `~/.ai-teacher/config.json`。

## 包含的工具

| 工具 | 位置 | 功能 |
|------|------|------|
| `fix-env.ps1` | `one-click-env/` | 中文 Windows 开发环境一键修复 |
| `mcp_hub.py` | `mcp-manager/` | MCP 插件 git-based 包管理器 |
| `generate_3d_kg.py` | `video-pipeline/` | 3D 知识图谱生成器 |

## 实战来源

这套工具来自真实踩坑：

1. **codebase-memory-mcp (Go)** 在中文 Windows 下 `os.UserCacheDir()` 返回乱码路径
2. **Three.js 3D 可视化** 遇到的假 3D 问题（z=0.0）和 CDN 加载失败
3. **MCP 插件安装** 从手工6步压成1条命令
4. **飞书双 bot 系统** 教学助手 + 桌面控制，已投产使用

## 许可证

MIT
