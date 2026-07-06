#!/usr/bin/env python3
"""
ai-teacher — AI 教师工具箱 CLI
================================
整合 fix-env.ps1、mcp-hub、火山引擎 ARK API 等工具，
提供环境检测修复、MCP 插件管理、视频脚本生成、飞书部署等功能。

子命令:
  env check       — 运行 fix-env.ps1 检测模式
  env fix         — 运行 fix-env.ps1 -FixAll 自动修复
  mcp install     — 安装 MCP 插件 (mcp-hub)
  mcp list        — 列出已安装 MCP 插件
  mcp remove      — 卸载 MCP 插件
  video script    — 用 DeepSeek 生成物理教学视频多镜头脚本
  video storyboard — 根据脚本生成分镜描述
  deploy feishu   — 部署飞书 bot
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "ai-teacher"
CONFIG_DIR = Path.home() / ".ai-teacher"
CONFIG_FILE = CONFIG_DIR / "config.json"

FIX_ENV_PS1 = Path.home() / "ai-teacher-toolkit" / "one-click-env" / "fix-env.ps1"
# 也尝试直接在 home 找
FIX_ENV_PS1_ALT = Path.home() / "fix-env.ps1"

MCP_HUB_DIR = Path.home() / "mcp-hub"
MCP_HUB_ALT = Path.home() / "ai-teacher-toolkit" / "mcp-manager"

FEISHU_WORKER = Path.home() / ".openclaw" / "feishu_worker.py"
# 火山引擎 ARK 配置
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# 视觉 endpoint (doubao seedance)
DEFAULT_ARK_ENDPOINT = "ep-20260706101420-2w997"

# ── Rich 彩色输出（fallback 到 print） ──────────────
_rich_available = False
try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    _console = Console()
    _rich_available = True
except ImportError:
    _console = None  # type: ignore


def echo(msg: str = "", style: str = "info"):
    """统一输出（支持 rich fallback）。"""
    if _rich_available:
        styles = {
            "info": "cyan",
            "ok": "green",
            "warn": "yellow",
            "error": "red bold",
            "title": "magenta bold",
        }
        s = styles.get(style, "cyan")
        _console.print(msg, style=s)
    else:
        print(msg)


def progress_spinner(description: str):
    """进度上下文管理器（或 fallback）。"""
    if _rich_available:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        )
    return None


# ── 配置 ──────────────────────────────────────────────


def _load_config() -> Dict:
    """加载 ~/.ai-teacher/config.json。"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(cfg: Dict):
    """保存 ~/.ai-teacher/config.json。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_ark_api_key():
    """获取火山引擎 ARK API Key。"""
    cfg = _load_config()
    key = cfg.get("ark", {}).get("api_key") or os.environ.get("ARK_API_KEY")
    if not key:
        print("  ⚠ 未配置火山引擎 ARK API Key")
        print("   请设置环境变量 ARK_API_KEY")
        return None
    return key


def _get_ark_endpoint():
    """获取火山引擎 endpoint ID（用作 model 参数）。"""
    cfg = _load_config()
    ep = cfg.get("ark", {}).get("endpoint") or os.environ.get("ARK_ENDPOINT")
    if not ep:
        ep = DEFAULT_ARK_ENDPOINT
    return ep


def _check_tool(name: str, cmd: list) -> bool:
    """检查工具是否可用。"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            shell=platform.system() == "Windows",
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _env_check_all() -> Dict[str, bool]:
    """检测所有需要的工具是否可用。"""
    tools = {
        "PowerShell": ["powershell", "-Command", "$PSVersionTable.PSVersion"],
        "Python": [sys.executable, "--version"],
        "Git": ["git", "--version"],
        "Node": ["node", "--version"],
        "npm": ["npm", "--version"],
    }
    results = {}
    echo("\n🔍 环境检测", "title")
    echo("─" * 40, "info")
    for name, cmd in tools.items():
        ok = _check_tool(name, cmd)
        results[name] = ok
        style = "ok" if ok else "warn"
        echo(f"  {name:12s} {'✅ 可用' if ok else '⚠️ 未找到'}", style)
    echo("─" * 40 + "\n", "info")
    return results


# ── 子命令：env ───────────────────────────────────────


def cmd_env_check():
    """运行 fix-env.ps1 检测模式。"""
    ps1 = FIX_ENV_PS1 if FIX_ENV_PS1.exists() else FIX_ENV_PS1_ALT
    if not ps1.exists():
        echo("❌ 找不到 fix-env.ps1", "error")
        sys.exit(1)

    echo("🔍 运行 fix-env.ps1（检测模式）...\n", "title")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ps1)],
        timeout=120,
    )
    sys.exit(r.returncode)


def cmd_env_fix():
    """运行 fix-env.ps1 -FixAll 自动修复。"""
    ps1 = FIX_ENV_PS1 if FIX_ENV_PS1.exists() else FIX_ENV_PS1_ALT
    if not ps1.exists():
        echo("❌ 找不到 fix-env.ps1", "error")
        sys.exit(1)

    echo("🔧 运行 fix-env.ps1（全自动修复模式）...\n", "title")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ps1), "-FixAll"],
        timeout=300,
    )
    sys.exit(r.returncode)


# ── 子命令：mcp ────────────────────────────────────────


def _import_mcp_hub():
    """动态导入 mcp_hub 模块。"""
    # 先尝试 mcp-hub 目录
    for d in [MCP_HUB_DIR, MCP_HUB_ALT]:
        if d.exists() and (d / "mcp_hub.py").exists():
            sys.path.insert(0, str(d))
            break
    try:
        import mcp_hub  # type: ignore
        return mcp_hub
    except ImportError:
        echo("❌ 无法导入 mcp_hub 模块", "error")
        echo(f"   请确认 mcp-hub 安装在 {MCP_HUB_DIR} 或 {MCP_HUB_ALT}", "warn")
        sys.exit(1)


def cmd_mcp_install(repo: str):
    """安装 MCP 插件。"""
    echo(f"📦 安装 MCP 插件: {repo}\n", "title")
    mcp = _import_mcp_hub()
    mcp.cmd_install(repo)


def cmd_mcp_list():
    """列出已安装的 MCP 插件。"""
    echo("📋 列出已安装的 MCP 插件\n", "title")
    mcp = _import_mcp_hub()
    mcp.cmd_list()


def cmd_mcp_remove(name: str):
    """卸载 MCP 插件。"""
    echo(f"🗑  卸载 MCP 插件: {name}\n", "title")
    mcp = _import_mcp_hub()
    mcp.cmd_remove(name)


# ── 子命令：video ─────────────────────────────────────


def _call_ark_api(prompt: str, system_prompt: str = "") -> Optional[str]:
    """调用火山引擎 ARK API（DeepSeek 模型）。"""
    api_key = _get_ark_api_key()
    if not api_key:
        echo("❌ 未配置火山引擎 ARK API key", "error")
        return None

    cfg = _load_config()
    ark_cfg = cfg.get("ark", {})
    base_url = ark_cfg.get("base_url", ARK_BASE_URL)
    endpoint = _get_ark_endpoint()
    model = endpoint  # 火山引擎用 endpoint ID 作为 model 参数

    # 构建请求
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    try:
        import requests
    except ImportError:
        echo("❌ 需要 requests 库：pip install requests", "error")
        return None

    try:
        echo("  🤖 正在调用 DeepSeek（火山引擎 ARK）...", "info")
        resp = requests.post(url, json=body, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content
    except requests.exceptions.Timeout:
        echo("❌ API 请求超时（120s）", "error")
    except requests.exceptions.HTTPError as e:
        echo(f"❌ API 请求失败: {e}", "error")
        if e.response is not None:
            echo(f"   {e.response.text[:500]}", "error")
    except Exception as e:
        echo(f"❌ 请求异常: {e}", "error")
    return None


def cmd_video_script(topic: str):
    """用 DeepSeek 生成物理教学视频多镜头脚本。"""
    echo(f"🎬 生成物理教学视频脚本\n", "title")
    echo(f"   主题: {topic}\n", "info")

    system_prompt = """你是一个专业的物理教学视频脚本作者。你的任务是生成高质量、逻辑清晰的物理教学视频脚本。

输出格式：严格按以下 JSON 格式输出（不要包含 markdown 代码块标记，直接输出 JSON）：
{
  "title": "视频标题",
  "topic": "主题",
  "total_duration": 总时长（秒）,
  "scenes": [
    {
      "scene_number": 1,
      "type": "中景|特写|动画示意|实拍|图文说明|实验演示",
      "description": "画面描述，详细说明镜头中的视觉元素",
      "narration": "旁白文案，面向高中生的讲解语言",
      "duration_seconds": 时长（秒）,
      "transition": "切|淡入|淡出|滑动|缩放|溶解"
    }
  ]
}

要求：
- 生成 6-8 个镜头
- 画面描述说明景别（中景/特写/全景/近景）和视觉元素
- 旁白用中文，通俗易懂，适合高中生
- 每个镜头 10-30 秒
- 转场效果多样化"""

    result = _call_ark_api(
        prompt=f"请为一个高中物理教学视频生成多镜头脚本，主题为：{topic}\n\n"
               f"输出 JSON 格式，包含 6-8 个镜头，每个镜头含：镜头编号、画面描述（含景别）、"
               f"旁白文案、时长（秒）、转场效果。",
        system_prompt=system_prompt,
    )

    if result is None:
        sys.exit(1)

    # 尝试提取 JSON
    content = result.strip()
    # 去掉可能的 ```json ... ``` 包裹
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 不是 JSON，直接输出
        echo("\n📝 脚本生成结果：\n", "title")
        print(content)
        return

    # 格式化输出
    echo(f"\n📺 {data.get('title', '物理教学视频')}", "title")
    echo(f"   主题: {data.get('topic', topic)}", "info")
    echo(f"   总时长: {data.get('total_duration', '?')} 秒\n", "info")

    scenes = data.get("scenes", [])
    for i, sc in enumerate(scenes):
        sn = sc.get("scene_number", i + 1)
        stype = sc.get("type", "")
        dur = sc.get("duration_seconds", "?")
        trans = sc.get("transition", "切")
        desc = sc.get("description", "")
        narration = sc.get("narration", "")

        echo(f"  ─── 镜头 {sn} ───", "title")
        echo(f"  类型: {stype}  |  时长: {dur}s  |  转场: {trans}")
        echo(f"  📹 画面: {desc}")
        echo(f"  🎙️ 旁白: {narration}\n")

    # 同时保存到文件
    output_dir = Path.cwd() / "ai-teacher-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_topic = topic.replace(" ", "_").replace("/", "_")[:30]
    output_file = output_dir / f"script_{safe_topic}.json"
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    echo(f"💾 脚本已保存到: {output_file}", "ok")


def cmd_video_storyboard(topic: str):
    """生成分镜描述（每镜头的画面描述、旁白、时长建议）。"""
    echo(f"🎨 生成物理教学视频分镜\n", "title")
    echo(f"   主题: {topic}\n", "info")

    system_prompt = """你是一个专业的视频分镜设计师，专注于物理教学视频。你需要为每个镜头提供详细的视觉设计。

输出格式：严格按以下 JSON 格式输出（直接输出 JSON，不要 markdown 代码块）：
{
  "title": "视频标题",
  "topic": "主题",
  "scenes": [
    {
      "scene_number": 1,
      "visual_description": "详细的画面描述：构图、景别、色彩、人物位置、道具、动画类型等",
      "narration": "旁白文案",
      "duration_seconds": 建议时长,
      "transition": "切|淡入|淡出|滑动|缩放|溶解",
      "camera_movement": "固定|推|拉|摇|移|跟",
      "visual_effects": ["效果1", "效果2"],
      "notes": "制作注意事项"
    }
  ]
}

要求：
- 生成 6-8 个镜头
- 视觉描述要足够详细，能让美术/动画师直接理解
- 说明动画类型（如果涉及）：3D 模拟、粒子动画、图表动画等
- 旁白适合高中生理解
- 每个镜头 10-30 秒"""

    result = _call_ark_api(
        prompt=f"请为高中物理教学视频生成详细分镜描述，主题为：{topic}\n\n"
               f"输出 JSON 格式，包含 6-8 个镜头。",
        system_prompt=system_prompt,
    )

    if result is None:
        sys.exit(1)

    content = result.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        echo("\n📝 分镜生成结果：\n", "title")
        print(content)
        return

    echo(f"\n🎨 {data.get('title', '物理教学视频分镜')}", "title")
    echo(f"   主题: {data.get('topic', topic)}\n", "info")

    scenes = data.get("scenes", [])
    for i, sc in enumerate(scenes):
        sn = sc.get("scene_number", i + 1)
        dur = sc.get("duration_seconds", "?")
        trans = sc.get("transition", "切")
        cam = sc.get("camera_movement", "固定")
        vfx = ", ".join(sc.get("visual_effects", []))
        vis = sc.get("visual_description", "")
        narration = sc.get("narration", "")
        notes = sc.get("notes", "")

        if _rich_available:
            from rich.panel import Panel
            from rich.text import Text
            t = Text()
            t.append(f"镜头 {sn}", style="bold magenta")
            t.append(f"  |  时长: {dur}s  |  转场: {trans}  |  运镜: {cam}", style="cyan")
            _console.print(Panel(t, border_style="blue"))
            _console.print(f"  📹 画面: {vis}", style="white")
            _console.print(f"  🎙️ 旁白: {narration}", style="green")
            if vfx:
                _console.print(f"  ✨ 特效: {vfx}", style="yellow")
            if notes:
                _console.print(f"  📌 备注: {notes}", style="dim")
            print()
        else:
            print(f"  ─── 镜头 {sn} ───")
            print(f"  时长: {dur}s  |  转场: {trans}  |  运镜: {cam}")
            print(f"  📹 画面: {vis}")
            print(f"  🎙️ 旁白: {narration}")
            if vfx:
                print(f"  ✨ 特效: {vfx}")
            if notes:
                print(f"  📌 备注: {notes}")
            print()

    output_dir = Path.cwd() / "ai-teacher-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_topic = topic.replace(" ", "_").replace("/", "_")[:30]
    output_file = output_dir / f"storyboard_{safe_topic}.json"
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    echo(f"💾 分镜已保存到: {output_file}", "ok")


# ── 子命令：deploy feishu ────────────────────────────


def cmd_deploy_feishu():
    """部署飞书 bot（从 ~/.openclaw/feishu_worker.py）。"""
    if not FEISHU_WORKER.exists():
        echo("❌ 找不到飞书 worker 文件", "error")
        echo(f"   预期路径: {FEISHU_WORKER}", "warn")
        sys.exit(1)

    echo("🚀 部署飞书 Bot\n", "title")

    # 1. 检查配置
    echo("  检查飞书配置...", "info")
    content = FEISHU_WORKER.read_text(encoding="utf-8")
    if "APP_ID" in content and "APP_SECRET" in content:
        echo("  ✅ APP_ID / APP_SECRET 已配置", "ok")
    else:
        echo("  ⚠️ 未找到 APP_ID / APP_SECRET 配置", "warn")

    # 2. 启动 worker（后台进程）
    python_exe = sys.executable
    cmd = [python_exe, str(FEISHU_WORKER)]
    
    echo(f"  启动命令: {' '.join(cmd)}\n", "info")
    echo("  🔄 正在启动飞书 worker（后台运行）...", "info")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        echo(f"  ✅ 飞书 worker 已启动 (PID: {proc.pid})", "ok")
        echo("  💡 查看日志: type ~/.openclaw\\logs\\worker.log", "info")
    except Exception as e:
        echo(f"  ❌ 启动失败: {e}", "error")
        sys.exit(1)


# ── CLI 入口 ──────────────────────────────────────────


def main():
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        prog="ai-teacher",
        description="AI 教师工具箱 — 环境检测修复 · MCP 管理 · 视频脚本 · 飞书部署",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              ai-teacher env check
              ai-teacher env fix
              ai-teacher mcp install https://github.com/user/mcp-server.git
              ai-teacher mcp list
              ai-teacher mcp remove my-server
              ai-teacher video script "牛顿第三定律"
              ai-teacher video storyboard "光的折射"
              ai-teacher deploy feishu
        """),
    )
    parser.add_argument(
        "--version", action="version",
        version=f"ai-teacher 0.1.0 (MVP)",
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── env ──
    p_env = subparsers.add_parser("env", help="环境检测与修复")
    env_sub = p_env.add_subparsers(dest="env_cmd", help="env 子命令")
    env_sub.add_parser("check", help="运行 fix-env.ps1 检测模式")
    env_sub.add_parser("fix", help="运行 fix-env.ps1 -FixAll 自动修复")

    # ── mcp ──
    p_mcp = subparsers.add_parser("mcp", help="MCP 插件管理（通过 mcp-hub）")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_cmd", help="mcp 子命令")
    p_mcp_install = mcp_sub.add_parser("install", help="安装 MCP 插件")
    p_mcp_install.add_argument("repo", help="Git 仓库 URL")
    mcp_sub.add_parser("list", help="列出已安装的 MCP 插件")
    p_mcp_remove = mcp_sub.add_parser("remove", help="卸载 MCP 插件")
    p_mcp_remove.add_argument("name", help="插件名称")

    # ── video ──
    p_video = subparsers.add_parser("video", help="视频脚本与分镜生成（火山引擎 ARK + DeepSeek）")
    video_sub = p_video.add_subparsers(dest="video_cmd", help="video 子命令")
    p_script = video_sub.add_parser("script", help="生成物理教学视频多镜头脚本")
    p_script.add_argument("topic", help='教学主题（如 "牛顿第三定律"）')
    p_storyboard = video_sub.add_parser("storyboard", help="生成分镜描述")
    p_storyboard.add_argument("topic", help="教学主题")

    # ── deploy ──
    p_deploy = subparsers.add_parser("deploy", help="部署飞书 bot 等服务")
    deploy_sub = p_deploy.add_subparsers(dest="deploy_cmd", help="deploy 子命令")
    deploy_sub.add_parser("feishu", help="部署飞书 bot（从 ~/.openclaw/feishu_worker.py）")

    args = parser.parse_args()

    # 没有子命令
    if args.command is None:
        parser.print_help()
        return

    # ── env ──
    if args.command == "env":
        if args.env_cmd == "check":
            _env_check_all()
            cmd_env_check()
        elif args.env_cmd == "fix":
            _env_check_all()
            cmd_env_fix()
        else:
            p_env.print_help()

    # ── mcp ──
    elif args.command == "mcp":
        if args.mcp_cmd == "install":
            cmd_mcp_install(args.repo)
        elif args.mcp_cmd == "list":
            cmd_mcp_list()
        elif args.mcp_cmd == "remove":
            cmd_mcp_remove(args.name)
        else:
            p_mcp.print_help()

    # ── video ──
    elif args.command == "video":
        if args.video_cmd == "script":
            cmd_video_script(args.topic)
        elif args.video_cmd == "storyboard":
            cmd_video_storyboard(args.topic)
        else:
            p_video.print_help()

    # ── deploy ──
    elif args.command == "deploy":
        if args.deploy_cmd == "feishu":
            cmd_deploy_feishu()
        else:
            p_deploy.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
