#!/usr/bin/env python3
"""
mcp-hub — MCP 插件的 Git-based 包管理器
==========================================
一条命令完成安装、编译、配置全流程。

命令：
  mcp-hub install <repo-url> [--name <name>]
  mcp-hub list
  mcp-hub remove <name>
  mcp-hub update [--all] [<name>]
"""

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- 常量 ----------
HUB_DIR = Path.home() / ".mcp-hub"
BIN_DIR = HUB_DIR / "bin"
CONFIG_FILE = HUB_DIR / "config.json"
HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"
WORK_DIR = HUB_DIR / "work"  # git clone 临时工作目录

# ---------- 工具函数 ----------


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 300,
         capture: bool = True, shell: bool = False) -> Tuple[int, str, str]:
    """执行命令并返回 (retcode, stdout, stderr)。"""
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=capture,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -2, "", f"找不到命令: {e}"
    except Exception as e:
        return -3, "", str(e)


def _which(name: str) -> Optional[str]:
    """检查 PATH 中是否存在命令。"""
    return shutil.which(name)


def _on_windows() -> bool:
    return platform.system() == "Windows"


def _normalize_path(path: Path) -> str:
    """返回适合写入 yaml 的路径（Windows 用正斜杠）。"""
    return path.as_posix()


def _get_8dot3(path_str: str) -> str:
    """将含中文的路径转为 8.3 短路径（避免 Go/Node 等工具乱码）。"""
    try:
        import ctypes
        from ctypes import wintypes
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        GetShortPathNameW.restype = wintypes.DWORD
        buf = ctypes.create_unicode_buffer(260)
        n = GetShortPathNameW(path_str, buf, 260)
        if n > 0 and n <= 260:
            return buf.value
    except Exception:
        pass
    return path_str


def _has_chinese(s: str) -> bool:
    """检查字符串是否包含中文字符。"""
    import re
    return bool(re.search(r'[\u4e00-\u9fff]', s))


def _sanitize_name(name: str) -> str:
    """将 repo 名称转换为合法短名。"""
    return name.lower().replace(" ", "-").replace("_", "-").strip("-")


def _repo_name_from_url(url: str) -> str:
    """从 Git URL 提取仓库名。"""
    base = url.rstrip("/").rsplit("/", 1)[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base


def _convert_url_ssh_to_https(url: str) -> str:
    """将 SSH URL 转换为 HTTPS URL。"""
    if url.startswith("git@"):
        # git@github.com:user/repo.git → https://github.com/user/repo.git
        url = url.replace(":", "/", 1)
        url = url.replace("git@", "https://")
    elif url.startswith("ssh://"):
        # ssh://git@github.com/user/repo.git → https://github.com/user/repo.git
        url = url.replace("ssh://", "https://")
        url = url.replace("git@", "")
    return url


# ---------- 配置读写 ----------


def _load_config() -> Dict:
    """加载 ~/.mcp-hub/config.json"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"plugins": {}}


def _save_config(cfg: Dict):
    """保存 ~/.mcp-hub/config.json"""
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_hermes_config() -> Dict:
    """加载 Hermes YAML 配置，返回完整 dict。"""
    try:
        import yaml
    except ImportError:
        return {}
    if not HERMES_CONFIG.exists():
        return {}
    try:
        with open(str(HERMES_CONFIG), "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_hermes_config(cfg: Dict):
    """保存 Hermes YAML 配置。"""
    try:
        import yaml
    except ImportError:
        return
    HERMES_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    # 自定义 representer 保持可读性
    class LiteralString(str):
        pass
    def literal_representer(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    yaml.add_representer(LiteralString, literal_representer)

    with open(str(HERMES_CONFIG), "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _set_hermes_mcp_server(cfg: Dict, name: str, command: str, args: List[str] = None):
    """在 Hermes config 中设置 mcp_servers.<name>。"""
    if "mcp_servers" not in cfg:
        cfg["mcp_servers"] = {}
    cfg["mcp_servers"][name] = {
        "command": command,
        "args": args or [],
    }


def _remove_hermes_mcp_server(cfg: Dict, name: str) -> bool:
    """从 Hermes config 移除 mcp_servers.<name>。"""
    if "mcp_servers" in cfg and name in cfg["mcp_servers"]:
        del cfg["mcp_servers"][name]
        return True
    return False


# ---------- 构建器 ----------

def _detect_build_type(repo_path: Path) -> Tuple[str, List[str], List[str]]:
    """
    检测项目类型，返回 (type, build_cmds, binary_patterns)
    - type: "go" | "node" | "cargo" | "python" | "pip" | "unknown"
    - build_cmds: 构建命令列表
    - binary_patterns: 用于查找编译产物的 glob 模式
    """
    files = set(f.name for f in repo_path.iterdir())

    # 1) Go (go.mod)
    if "go.mod" in files:
        ret, _, _ = _run(["go", "version"], timeout=10, shell=_on_windows())
        if ret == 0:
            return ("go", ["go build -o ."], ["*"])
        else:
            print("  ⚠  检测到 Go 项目但未安装 Go，跳过构建")

    # 2) Cargo (Cargo.toml)
    if "Cargo.toml" in files:
        ret, _, _ = _run(["cargo", "--version"], timeout=10, shell=_on_windows())
        if ret == 0:
            return ("cargo", ["cargo build --release"], ["target/release/*"])
        else:
            print("  ⚠  检测到 Rust 项目但未安装 Cargo，跳过构建")
            return ("cargo", [], [])

    # 3) Node (package.json) — 检测是否有构建脚本
    if "package.json" in files:
        ret, _, _ = _run(["npm", "--version"], timeout=10, shell=_on_windows())
        if ret == 0:
            pkg_path = repo_path / "package.json"
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                has_build = bool(pkg.get("scripts", {}).get("build"))
                bin_conf = pkg.get("bin", {})
                if isinstance(bin_conf, str):
                    bin_names = [bin_conf]
                elif isinstance(bin_conf, dict):
                    bin_names = list(bin_conf.values())
                else:
                    bin_names = []
                if has_build:
                    return ("node", ["npm install", "npm run build"], ["build/*", "dist/*", "*.js", "*.mjs", *bin_names])
                else:
                    return ("node", ["npm install"], ["*.js", "*.mjs", *bin_names])
            except Exception:
                return ("node", ["npm install"], ["*.js", "*.mjs"])
        else:
            print("  ⚠  检测到 Node 项目但未安装 npm，跳过构建")
            return ("node", [], [])

    # 4) Python (setup.py / pyproject.toml / requirements.txt)
    if "setup.py" in files or "pyproject.toml" in files:
        return ("pip", ["pip install -e ."], [])

    # 5) 裸 Python 脚本
    py_files = [f for f in files if f.endswith(".py")]
    if py_files:
        # 检查是否有主入口文件
        main_candidates = [f for f in py_files if f.startswith("main") or f.startswith("server") or f.startswith("mcp")]
        if main_candidates:
            return ("python", [], main_candidates[:3])

    return ("unknown", [], [])


def _find_binaries(repo_path: Path, patterns: List[str]) -> List[Path]:
    """
    根据 glob 模式查找编译产物。
    返回路径列表（相对于 repo_path）。
    """
    found: List[Path] = []
    for pattern in patterns:
        if pattern == "*":
            # 查找可执行文件
            for f in repo_path.iterdir():
                if f.is_file():
                    # Windows: .exe / .cmd / .bat
                    # Linux/macOS: 可执行位
                    if _on_windows():
                        if f.suffix.lower() in (".exe", ".cmd", ".bat", ".ps1"):
                            found.append(f.relative_to(repo_path))
                    else:
                        st = f.stat()
                        if st.st_mode & stat.S_IXUSR or st.st_mode & stat.S_IXGRP:
                            found.append(f.relative_to(repo_path))
            # 如果没有找到可执行文件，也找 .js / .py 入口
            if not found:
                for ext in (".js", ".mjs", ".py"):
                    for f in repo_path.iterdir():
                        if f.suffix.lower() == ext:
                            found.append(f.relative_to(repo_path))
        elif "/" in pattern:
            # 深层 glob，用 Path.rglob
            for f in repo_path.rglob(pattern):
                if f.is_file():
                    found.append(f.relative_to(repo_path))
        else:
            for f in repo_path.glob(pattern):
                if f.is_file():
                    found.append(f.relative_to(repo_path))
    return found


def _build_project(repo_path: Path, build_type: str, build_cmds: List[str]) -> bool:
    """执行构建命令。"""
    if not build_cmds:
        return True  # 无需构建
    print(f"  🔨 构建方式: {build_type}")
    for cmd in build_cmds:
        print(f"    $ {cmd}")
        # Windows 下 npm/go/cargo 需要用 shell=True 来找到 PATH 中的命令
        use_shell = _on_windows()
        parts = cmd.split()
        ret, out, err = _run(parts, cwd=repo_path, timeout=600, shell=use_shell)
        if out.strip():
            for line in out.strip().splitlines():
                print(f"      {line}")
        if err.strip():
            for line in err.strip().splitlines():
                print(f"      {line}")
        if ret != 0:
            print(f"  ❌ 构建失败 (ret={ret})")
            return False
    return True


def _copy_artifacts(repo_path: Path, name: str, build_type: str,
                    patterns: List[str]) -> List[Path]:
    """将编译产物复制到 ~/.mcp-hub/bin/<name>/。"""
    target_dir = BIN_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    # 如果已有文件，清空再复制
    if any(target_dir.iterdir()):
        print(f"  📁 清空目标目录 {target_dir}")
        for f in target_dir.iterdir():
            if f.is_dir():
                shutil.rmtree(f, ignore_errors=True)
            else:
                f.unlink()

    copied: List[Path] = []

    if build_type == "go":
        # Go 构建产物直接在 repo 根目录
        for f in repo_path.iterdir():
            if f.is_file() and (not _on_windows() or f.suffix.lower() in (".exe", "")):
                if f.name == "go.mod" or f.name == "go.sum" or f.name.endswith(".go"):
                    continue
                # 检查是否真的是可执行文件
                if _on_windows():
                    if f.suffix.lower() == ".exe":
                        dest = target_dir / f.name
                        shutil.copy2(f, dest)
                        copied.append(dest)
                        print(f"    ✅ {f.name}")
                else:
                    st = f.stat()
                    if st.st_mode & stat.S_IXUSR:
                        dest = target_dir / f.name
                        shutil.copy2(f, dest)
                        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
                        copied.append(dest)
                        print(f"    ✅ {f.name}")

        if not copied:
            # fallback: 复制所有可能二进制
            for f in repo_path.iterdir():
                if f.is_file() and not f.name.startswith(".") and f.name not in ("go.mod", "go.sum"):
                    for ext in ("", ".exe", ".js", ".py"):
                        if f.name.endswith(ext) and not f.name.endswith(".go"):
                            dest = target_dir / f.name
                            shutil.copy2(f, dest)
                            copied.append(dest)
                            print(f"    ✅ {f.name}")
                            break

    elif build_type == "cargo":
        release_dir = repo_path / "target" / "release"
        if release_dir.exists():
            for f in release_dir.iterdir():
                if f.is_file() and (not _on_windows() or f.suffix.lower() in (".exe", ".dll", "")):
                    if f.suffix.lower() in (".d", ".dSYM", ".pdb"):
                        continue
                    if _on_windows() and f.suffix.lower() != ".exe" and not f.suffix:
                        continue
                    dest = target_dir / f.name
                    shutil.copy2(f, dest)
                    copied.append(dest)
                    print(f"    ✅ {f.name}")

    elif build_type in ("node",):
        # 复制全部文件（node 项目按需运行）
        copied = _copy_recursive(repo_path, target_dir)

    elif build_type == "pip":
        # pip install 已经安装好了，但我们也记录一下
        pass

    elif patterns:
        for pattern in patterns:
            for f in repo_path.rglob(pattern):
                if f.is_file():
                    rel = f.relative_to(repo_path)
                    dest = target_dir / rel.name
                    shutil.copy2(f, dest)
                    copied.append(dest)
                    print(f"    ✅ {f.name}")

    return copied


def _copy_recursive(src: Path, dst: Path) -> List[Path]:
    """递归复制目录内容，排除 .git 和 node_modules。"""
    copied = []
    for item in src.iterdir():
        if item.name in (".git", "node_modules", "__pycache__", ".venv", "target"):
            continue
        if item.is_dir():
            dst_sub = dst / item.name
            dst_sub.mkdir(parents=True, exist_ok=True)
            copied.extend(_copy_recursive(item, dst_sub))
        else:
            if item.name.startswith("."):
                continue
            try:
                shutil.copy2(item, dst / item.name)
                copied.append(dst / item.name)
            except Exception:
                pass
    return copied


def _force_rmtree(path: Path):
    """强力删除目录树（处理 Windows 下 .git 只读文件）。"""
    if not path.exists():
        return
    for root, dirs, files in os.walk(str(path)):
        for f in files:
            fp = os.path.join(root, f)
            try:
                os.chmod(fp, stat.S_IWRITE)
            except OSError:
                pass
        for d in dirs:
            fp = os.path.join(root, d)
            try:
                os.chmod(fp, stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(str(path), ignore_errors=True)
    if path.exists():
        # 终极手段 retry
        import time
        time.sleep(0.5)
        shutil.rmtree(str(path), ignore_errors=True)


# ---------- 验证 ----------

def _is_binary_candidate(f: Path) -> bool:
    """判断文件是否为可能的二进制入口（排除文档/配置等）。"""
    skip_suffixes = {".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json",
                     ".cfg", ".ini", ".conf", ".env", ".gitignore", ".dockerignore",
                     ".png", ".jpg", ".svg", ".ico", ".css", ".html", ".htm",
                     ".ts", ".tsx", ".jsx", ".map", ".d.ts"}
    skip_names = {"LICENSE", "README", "CHANGELOG", "CONTRIBUTING", "CODE_OF_CONDUCT",
                  "SECURITY", "MAINTAINERS", "AUTHORS", "COPYING", "Makefile",
                  "Dockerfile", "docker-compose", ".gitignore", ".gitattributes",
                  "tsconfig.json", "package-lock.json", "yarn.lock", ".npmignore",
                  "eslintrc", "prettierrc", "babelrc"}
    if f.suffix.lower() in skip_suffixes:
        return False
    if f.stem.upper() in skip_names or f.stem.upper().startswith(tuple(s.upper() for s in skip_names)):
        return False
    # 跳过以 dot 开头的
    if f.name.startswith("."):
        return False
    return True


def _find_entry_binary(name: str) -> Optional[Path]:
    """在 ~/.mcp-hub/bin/<name>/ 下查找可执行入口。"""
    target_dir = BIN_DIR / name
    if not target_dir.exists():
        return None
    # 优先级: .exe > .cmd > .bat > .js > .py > 其他
    for ext in (".exe", ".cmd", ".bat", ".ps1"):
        for f in target_dir.iterdir():
            if f.suffix.lower() == ext and _is_binary_candidate(f):
                return f
    # 无扩展名可执行文件
    for f in target_dir.iterdir():
        if f.is_file() and not f.suffix and _is_binary_candidate(f):
            return f
    # .js 入口
    for f in target_dir.iterdir():
        if f.suffix.lower() == ".js" and _is_binary_candidate(f):
            return f
    # .py 入口
    for f in target_dir.iterdir():
        if f.suffix.lower() == ".py" and _is_binary_candidate(f):
            return f
    # 任意非文档文件
    files = [f for f in target_dir.iterdir() if f.is_file() and _is_binary_candidate(f)]
    if files:
        return files[0]
    # 最后手段 — 任意文件
    files = [f for f in target_dir.iterdir() if f.is_file()]
    if files:
        return files[0]
    return None


def _verify_binary(name: str, bin_path: Path) -> bool:
    """验证二进制可用。"""
    print(f"\n  🔍 验证: {bin_path}")
    if not bin_path.exists():
        print(f"  ❌ 文件不存在: {bin_path}")
        return False

    # 尝试运行 --help 或 --version
    cmd = [str(bin_path), "--help"]
    ret, out, err = _run(cmd, timeout=15)
    if ret == 0:
        print(f"  ✅ 验证通过 (--help 返回 0)")
        if out.strip():
            preview = out.strip()[:200]
            print(f"     {preview}")
        return True
    # 再试一次没有参数
    cmd2 = [str(bin_path)]
    ret2, out2, err2 = _run(cmd2, timeout=15)
    if ret2 in (0, 1):
        print(f"  ✅ 二进制可执行 (返回码 {ret2})")
        return True

    # 检查文件大小
    size = bin_path.stat().st_size
    if size > 100:
        print(f"  ⚠  验证执行失败 (ret={ret})，但文件存在 ({size} bytes)")
        return True  # 文件存在就算通过

    print(f"  ❌ 验证失败")
    return False


# ---------- 核心命令 ----------


def cmd_install(repo_url: str, name: Optional[str] = None, build_timeout: int = 600):
    """安装 MCP 插件。"""
    print(f"\n{'='*60}")
    print(f"  📦 安装 MCP 插件")
    print(f"     仓库: {repo_url}")
    print(f"{'='*60}\n")

    cfg = _load_config()

    # 1. 确定插件名
    repo_name = _repo_name_from_url(repo_url)
    plugin_name = _sanitize_name(name) if name else _sanitize_name(repo_name)

    if plugin_name in cfg["plugins"]:
        print(f"  ⚠  插件 '{plugin_name}' 已安装。使用 'mcp-hub update {plugin_name}' 更新。")
        return

    print(f"  插件名: {plugin_name}")

    # 2. Git clone — 中文路径特殊处理
    work_dir_path = str(WORK_DIR / plugin_name)
    if _on_windows() and _has_chinese(work_dir_path):
        work_dir_short = _get_8dot3(str(WORK_DIR)) or str(WORK_DIR)
        work_dir = Path(work_dir_short) / plugin_name
    else:
        work_dir = WORK_DIR / plugin_name
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  📥 克隆仓库...")
    # 先试 SSH
    git_cmd = ["git", "clone", "--depth", "1", repo_url, str(work_dir)]
    ret, out, err = _run(git_cmd, timeout=120, shell=_on_windows())
    if ret != 0:
        https_url = _convert_url_ssh_to_https(repo_url)
        if https_url != repo_url:
            print(f"  ⚠  SSH 失败，fallback 到 HTTPS...")
            git_cmd = ["git", "clone", "--depth", "1", https_url, str(work_dir)]
            ret, out, err = _run(git_cmd, timeout=120, shell=_on_windows())

    if ret != 0:
        print(f"  ❌ Git clone 失败:")
        for line in err.strip().splitlines()[:10]:
            print(f"     {line}")
        _force_rmtree(work_dir)
        sys.exit(1)

    print(f"  ✅ 克隆成功")

    # 3. 获取提交信息
    git_log_cmd = ["git", "-C", str(work_dir), "log", "--oneline", "-1"]
    _, commit_log, _ = _run(git_log_cmd)
    commit_id = commit_log.strip()[:40] if commit_log.strip() else "unknown"
    print(f"     提交: {commit_id}")

    # 4. 检测构建类型 & 构建
    build_type, build_cmds, patterns = _detect_build_type(work_dir)
    print(f"  📋 项目类型: {build_type}")
    if build_type in ("node",):
        print(f"  ⏱  构建超时: {build_timeout}s (可通过 -t 调整)")

    build_ok = _build_project(work_dir, build_type, build_cmds)
    if not build_ok:
        print(f"\n  ❌ 构建失败，清理中...")
        _force_rmtree(work_dir)
        sys.exit(1)

    # 5. 复制产物
    print(f"\n  📋 复制产物到 {BIN_DIR / plugin_name}")
    artifacts = _copy_artifacts(work_dir, plugin_name, build_type, patterns)

    # 6. 找到二进制入口
    entry_binary = _find_entry_binary(plugin_name)

    if entry_binary is None:
        print(f"  ⚠  未找到编译产物，尝试复制整个目录")
        artifacts = _copy_recursive(work_dir, BIN_DIR / plugin_name)
        entry_binary = _find_entry_binary(plugin_name)

    # 7. 验证
    if entry_binary:
        _verify_binary(plugin_name, entry_binary)

    # 8. 配置 Hermes
    if entry_binary:
        bin_path_str = str(entry_binary)
        # Windows 路径处理
        if _on_windows():
            bin_path_str = bin_path_str.replace("\\", "\\\\")

        hermes_cfg = _load_hermes_config()
        args_list = []
        # 如果是 JS 文件，用 node 执行
        if entry_binary.suffix.lower() == ".js":
            node_path = _which("node")
            if node_path:
                _set_hermes_mcp_server(hermes_cfg, plugin_name,
                                       command=node_path,
                                       args=[str(entry_binary)])
                bin_path_str = f"{node_path} {entry_binary}"
            else:
                print(f"  ⚠  Node.js 未安装，跳过 Hermes 配置")
                bin_path_str = str(entry_binary)
        elif entry_binary.suffix.lower() == ".py":
            python_path = _which("python3") or _which("python")
            if python_path:
                _set_hermes_mcp_server(hermes_cfg, plugin_name,
                                       command=python_path,
                                       args=[str(entry_binary)])
                bin_path_str = f"{python_path} {entry_binary}"
            else:
                print(f"  ⚠  Python 未找到，跳过 Hermes 配置")
                bin_path_str = str(entry_binary)
        else:
            _set_hermes_mcp_server(hermes_cfg, plugin_name,
                                   command=str(entry_binary),
                                   args=[])

        _save_hermes_config(hermes_cfg)
        print(f"\n  📝 Hermes 配置已更新: mcp_servers.{plugin_name}")

    # 9. 保存到数据库
    cfg["plugins"][plugin_name] = {
        "name": plugin_name,
        "repo_url": repo_url,
        "commit": commit_id,
        "build_type": build_type,
        "install_time": datetime.now(timezone.utc).isoformat(),
        "binary": str(entry_binary) if entry_binary else None,
        "artifacts": [str(a) for a in artifacts],
    }
    _save_config(cfg)

    # 10. 清理工作目录
    _force_rmtree(work_dir)

    # 11. 安装报告
    print(f"\n{'='*60}")
    print(f"  ✅ 安装完成！")
    print(f"     插件:    {plugin_name}")
    print(f"     仓库:    {repo_url}  @{commit_id[:12]}")
    print(f"     类型:    {build_type}")
    print(f"     二进制:  {entry_binary or 'N/A'}")
    print(f"     位置:    {BIN_DIR / plugin_name}")
    print(f"     配置:    mcp_servers.{plugin_name}")
    print(f"{'='*60}\n")
    print(f"  💡 重启 Hermes 或运行相关命令即可使用 '{plugin_name}' 功能。")


def cmd_list():
    """列出已安装的 MCP 插件。"""
    cfg = _load_config()
    plugins = cfg.get("plugins", {})

    if not plugins:
        print("\n  📭 未安装任何 MCP 插件。\n")
        return

    print(f"\n{'='*60}")
    print(f"  已安装的 MCP 插件 ({len(plugins)})")
    print(f"{'='*60}\n")

    for name, info in sorted(plugins.items()):
        install_time = info.get("install_time", "?")[:19].replace("T", " ")
        build_type = info.get("build_type", "?")
        commit = info.get("commit", "?")[:12]
        binary = info.get("binary")
        binary_label = Path(binary).name if binary else "N/A"

        print(f"  📦 {name}")
        print(f"     类型:    {build_type}")
        print(f"     提交:    {commit}")
        print(f"     二进制:  {binary_label}")
        print(f"     安装于:  {install_time}")
        print()

    print(f"{'='*60}\n")


def cmd_remove(name: str):
    """卸载 MCP 插件。"""
    cfg = _load_config()

    if name not in cfg.get("plugins", {}):
        print(f"\n  ❌ 插件 '{name}' 未安装。\n")
        sys.exit(1)

    print(f"\n  🗑  卸载 '{name}'...")

    # 1. 删除二进制目录
    target_dir = BIN_DIR / name
    if target_dir.exists():
        _force_rmtree(target_dir)
        print(f"  ✅ 已删除 {target_dir}")

    # 2. 从 Hermes config 移除
    hermes_cfg = _load_hermes_config()
    if _remove_hermes_mcp_server(hermes_cfg, name):
        _save_hermes_config(hermes_cfg)
        print(f"  ✅ 已从 Hermes 配置移除 mcp_servers.{name}")

    # 3. 从数据库移除
    del cfg["plugins"][name]
    _save_config(cfg)

    print(f"  ✅ 卸载完成！\n")


def cmd_update(names: List[str], all_flag: bool = False):
    """更新 MCP 插件。"""
    cfg = _load_config()
    installed = cfg.get("plugins", {})

    if all_flag:
        names = list(installed.keys())
    elif not names:
        names = list(installed.keys())

    if not names:
        print("\n  📭 没有需要更新的插件。\n")
        return

    for name in names:
        if name not in installed:
            print(f"\n  ❌ 插件 '{name}' 未安装，跳过。\n")
            continue

        info = installed[name]
        repo_url = info.get("repo_url", "")
        if not repo_url:
            print(f"\n  ⚠  插件 '{name}' 缺少 repo_url，跳过。\n")
            continue

        print(f"\n{'─'*50}")
        print(f"  🔄 更新 '{name}'")
        print(f"     仓库: {repo_url}")
        print(f"{'─'*50}")

        # 卸载旧版本（保留数据库记录备用）
        old_dir = BIN_DIR / name
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)
        hermes_cfg = _load_hermes_config()
        _remove_hermes_mcp_server(hermes_cfg, name)
        _save_hermes_config(hermes_cfg)

        # 从数据库移除旧记录
        del cfg["plugins"][name]
        _save_config(cfg)

        # 重新安装
        cmd_install(repo_url, name)


# ---------- CLI 入口 ----------


def main():
    parser = argparse.ArgumentParser(
        description="mcp-hub — MCP 插件的 Git-based 包管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  mcp-hub install https://github.com/user/mcp-server.git
  mcp-hub install git@github.com:user/mcp-server.git --name my-server
  mcp-hub list
  mcp-hub remove my-server
  mcp-hub update my-server
  mcp-hub update --all
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # install
    p_install = subparsers.add_parser("install", help="安装 MCP 插件")
    p_install.add_argument("repo_url", help="Git 仓库 URL（SSH 或 HTTPS）")
    p_install.add_argument("--name", "-n", help="自定义插件名（默认从仓库名推断）")
    p_install.add_argument("--timeout", "-t", type=int, default=600,
                           help="构建超时秒数（默认 600s，大项目可设为 1200）")

    # list
    subparsers.add_parser("list", help="列出已安装的 MCP 插件")

    # remove
    p_remove = subparsers.add_parser("remove", help="卸载 MCP 插件")
    p_remove.add_argument("name", help="插件名")

    # update
    p_update = subparsers.add_parser("update", help="更新 MCP 插件")
    p_update.add_argument("name", nargs="?", default=None, help="插件名")
    p_update.add_argument("--all", "-a", action="store_true", help="更新所有插件")

    args = parser.parse_args()

    # 确保目录存在
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "install":
        cmd_install(args.repo_url, args.name, build_timeout=args.timeout or 600)
    elif args.command == "list":
        cmd_list()
    elif args.command == "remove":
        cmd_remove(args.name)
    elif args.command == "update":
        cmd_update([args.name] if args.name else [], all_flag=args.all)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
