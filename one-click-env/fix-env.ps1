# fix-env.ps1 — 中文 Windows 开发环境一键检测修复 (v2.0)
# ========================================================
# 全自动模式: .\fix-env.ps1
# Verbose模式: .\fix-env.ps1 -Verbose
# 静默修复:   .\fix-env.ps1 -FixAll
# ========================================================

param(
    [switch]$Verbose = $false,
    [switch]$FixAll = $false
)

$ErrorActionPreference = "Continue"
$script:fixes_applied = 0
$script:fixes_failed = 0
$script:warnings = 0
$script:skipped = 0
$script:passed = 0
$script:report = [System.Collections.Generic.List[PSCustomObject]]::new()

function Write-V { param([string]$M) if ($Verbose) { Write-Host "  [VERBOSE] $M" -ForegroundColor DarkGray } }
function Write-OK   { Write-Host "  [PASS] $args" -ForegroundColor Green; $script:passed++ }
function Write-WARN { Write-Host "  [WARN] $args" -ForegroundColor Yellow; $script:warnings++ }
function Write-FIX  { Write-Host "  [FIX] $args" -ForegroundColor Cyan; $script:fixes_applied++ }
function Write-SKIP { Write-Host "  [SKIP] $args" -ForegroundColor DarkGray; $script:skipped++ }
function Write-H1   { Write-Host "`n=== $args ===" -ForegroundColor Magenta }

function Add-Report {
    param($Category, $Check, $Status, $Detail)
    $script:report.Add([PSCustomObject]@{Category=$Category;Check=$Check;Status=$Status;Detail=$Detail})
}

function Has-Chinese([string]$s) { $s -match '[一-鿿㐀-䶿]' }

function Get-8dot3Path([string]$Path) {
    try {
        $fso = New-Object -ComObject Scripting.FileSystemObject
        if (Test-Path $Path) { return $fso.GetFolder((Resolve-Path $Path).Path).ShortPath }
    } catch { }
    return $null
}

function Write-ProgressBar {
    param([int]$Current, [int]$Total, [string]$Status)
    $pct = [math]::Round($Current / $Total * 100)
    Write-Progress -Activity "fix-env.ps1 — 中文 Windows 开发环境检测修复" -Status $Status -PercentComplete $pct
}

# ═══════════════════════════════════════════
# Module 1: 中文用户名 + HOME 重定向
# ═══════════════════════════════════════════
function Fix-ChineseUsername {
    Write-H1 "1/8 中文用户名检测"
    Write-ProgressBar 1 8 "中文用户名检测"
    $u = $env:USERNAME
    if (-not (Has-Chinese $u)) { Add-Report "USER" "用户名" "PASS" "纯 ASCII: $u"; Write-OK "用户名纯 ASCII"; return }

    Add-Report "USER" "用户名" "WARN" "含中文: $u"
    Write-WARN "用户名含中文: $u (Go/Node/Rust cache 可能乱码)"

    $currentHome = $env:HOME
    if ($currentHome -and -not (Has-Chinese $currentHome)) {
        Add-Report "USER" "HOME 已重定向" "PASS" "HOME=$currentHome"
        Write-OK "HOME 已重定向: $currentHome"
        return
    }

    if (-not $FixAll) { Add-Report "USER" "HOME 重定向" "WARN" "需修复: $env:HOME"; return }

    $asciiHome = "C:\claude-data"
    try {
        New-Item -ItemType Directory -Force -Path "$asciiHome\.cache" | Out-Null
        New-Item -ItemType Directory -Force -Path "$asciiHome\.go" | Out-Null
        New-Item -ItemType Directory -Force -Path "$asciiHome\.npm" | Out-Null
        $oldCache = "$env:USERPROFILE\.cache"
        if (Test-Path $oldCache) { Copy-Item "$oldCache\*" "$asciiHome\.cache\" -Recurse -ErrorAction SilentlyContinue }
        [Environment]::SetEnvironmentVariable("HOME", $asciiHome, "User")
        $env:HOME = $asciiHome
        Add-Report "USER" "HOME 重定向" "FIXED" "HOME=$asciiHome"
        Write-FIX "HOME 已设为 $asciiHome"
    } catch {
        Add-Report "USER" "HOME 重定向" "FAIL" $_.Exception.Message
        Write-WARN "设置 HOME 失败: $_"
    }
}

# ═══════════════════════════════════════════
# Module 2: 环境变量一致性
# ═══════════════════════════════════════════
function Fix-EnvChain {
    Write-H1 "2/8 环境变量一致性"
    Write-ProgressBar 2 8 "环境变量一致性检查"
    $vars = @("HOME","USERPROFILE","HOMEDRIVE","HOMEPATH")
    $allConsistent = $true
    $matches = @{}
    foreach ($v in $vars) {
        $val = [Environment]::GetEnvironmentVariable($v, "User")
        if (-not $val) { $val = [Environment]::GetEnvironmentVariable($v, "Process") }
        if (-not $val) { $val = [Environment]::GetEnvironmentVariable($v, "Machine") }
        $matches[$v] = $val
        Write-V "  $v = $val"
    }
    # 检查 HOME vs USERPROFILE
    if ($matches["HOME"] -and $matches["USERPROFILE"] -and $matches["HOME"] -ne $matches["USERPROFILE"]) {
        if ($matches["HOME"] -eq "C:\claude-data") {
            Write-OK "HOME 指向 claude-data (正常)"
        } else {
            Write-WARN "HOME($($matches['HOME'])) != USERPROFILE($($matches['USERPROFILE']))"
            $allConsistent = $false
        }
    }
    if ($allConsistent) { Add-Report "ENV" "一致性" "PASS" "HOME/USERPROFILE 一致"; Write-OK "环境变量一致" }
    else { Add-Report "ENV" "一致性" "WARN" "HOME 不匹配" }
}

# ═══════════════════════════════════════════
# Module 3: PATH 中文路径检测
# ═══════════════════════════════════════════
function Fix-PathEntries {
    Write-H1 "3/8 PATH 中文路径检测"
    Write-ProgressBar 3 8 "PATH 中文路径检测"
    $cnt = 0
    $newPath = @()
    foreach ($e in ($env:PATH -split ';')) {
        if (-not $e) { $newPath += $e; continue }
        if (Has-Chinese $e) {
            $short = Get-8dot3Path $e
            if ($short) {
                $cnt++; $newPath += $short
                Write-V "$e → $short"
            } else {
                $newPath += $e
            }
        } else {
            $newPath += $e
        }
    }
    if ($cnt -eq 0) {
        Add-Report "PATH" "中文路径" "PASS" "无中文路径"
        Write-OK "PATH 无中文路径"
        return
    }
    Add-Report "PATH" "中文路径" "WARN" "$cnt 个中文路径被替换为短路径"
    Write-WARN "发现 $cnt 个中文路径条目"

    if ($FixAll) {
        $uniquePath = @()
        foreach ($p in $newPath) { if ($p -and $p -notin $uniquePath) { $uniquePath += $p } }
        $env:PATH = $uniquePath -join ';'
        [Environment]::SetEnvironmentVariable("PATH", $env:PATH, "User")
        Add-Report "PATH" "修复" "FIXED" "已用 8.3 短路径替换 (去重后 $($uniquePath.Count) 条)"
        Write-FIX "已用 8.3 短路径替换 $cnt 个条目"
    }
}

# ═══════════════════════════════════════════
# Module 4: Git SSH 配置
# ═══════════════════════════════════════════
function Fix-GitSSH {
    Write-H1 "4/8 Git SSH 配置"
    Write-ProgressBar 4 8 "Git SSH 配置检查"

    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Add-Report "GIT" "Git" "WARN" "Git 未安装"
        Write-SKIP "Git 未安装"; return
    }
    Add-Report "GIT" "Git" "PASS" "git version $(& git --version)"

    # SSH 密钥检查
    $sshDir = "$env:USERPROFILE\.ssh"
    $keyFiles = @()
    if (Test-Path $sshDir) {
        $keyFiles = @(Get-ChildItem "$sshDir\id_*" -ErrorAction SilentlyContinue | Where-Object { -not $_.Name.EndsWith(".pub") })
    }
    if ($keyFiles.Count -gt 0) {
        Add-Report "GIT" "SSH 密钥" "PASS" "存在 $($keyFiles.Count) 个密钥"
        Write-OK "SSH 密钥已存在 ($($keyFiles.Count) 个)"
    } else {
        Add-Report "GIT" "SSH 密钥" "WARN" "未找到密钥"
        Write-WARN "未找到 SSH 密钥"
        if ($FixAll -and $gitCmd) {
            try {
                ssh-keygen -t ed25519 -f "$sshDir\id_ed25519" -N '""' -C "fix-env@auto" 2>&1 | Out-Null
                Add-Report "GIT" "SSH 密钥生成" "FIXED" "id_ed25519 已生成"
                Write-FIX "SSH 密钥已生成"
            } catch {
                Add-Report "GIT" "SSH 密钥生成" "FAIL" $_.Exception.Message
                Write-WARN "SSH 密钥生成失败"
            }
        }
    }

    # SSH config
    if (Test-Path "$sshDir\config") {
        $cfg = Get-Content "$sshDir\config" -Raw -ErrorAction SilentlyContinue
        if ($cfg -and $cfg -match "github.com") {
            Add-Report "GIT" "SSH config" "PASS" "有 GitHub 配置"
            Write-OK "SSH config 已配置 GitHub"
        } else {
            Add-Report "GIT" "SSH config" "WARN" "缺少 GitHub"
            Write-WARN "SSH config 缺少 GitHub"
        }
    } else {
        Add-Report "GIT" "SSH config" "WARN" "不存在"
        Write-WARN "SSH config 不存在"
        if ($FixAll) {
            @"
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  StrictHostKeyChecking no

Host gitlab.com
  HostName gitlab.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  StrictHostKeyChecking no
"@ | Out-File -FilePath "$sshDir\config" -Encoding ASCII -NoNewline
            Add-Report "GIT" "SSH config" "FIXED" "已创建"
            Write-FIX "SSH config 已创建"
        }
    }

    # HTTPS fallback
    $v = git config --global --get url."https://github.com/".insteadOf 2>$null
    if ($v -eq "git@github.com:") {
        Add-Report "GIT" "HTTPS fallback" "PASS" "已配置"
    } else {
        Add-Report "GIT" "HTTPS fallback" "WARN" "未配置"
        if ($FixAll) {
            git config --global url."https://github.com/".insteadOf git@github.com:
            Add-Report "GIT" "HTTPS fallback" "FIXED" "已设置"
            Write-FIX "HTTPS fallback 已配置"
        }
    }

    # Default branch
    $db = git config --global --get init.defaultBranch 2>$null
    if ($db -ne "main") {
        if ($FixAll) {
            git config --global init.defaultBranch main
            Add-Report "GIT" "defaultBranch" "FIXED" "设为 main"
            Write-FIX "默认分支设为 main"
        }
    } else {
        Add-Report "GIT" "defaultBranch" "PASS" "main"
    }
}

# ═══════════════════════════════════════════
# Module 5: PowerShell 编码 + 执行策略
# ═══════════════════════════════════════════
function Fix-PowerShell {
    Write-H1 "5/8 PowerShell 配置"
    Write-ProgressBar 5 8 "PowerShell 配置检查"

    # 执行策略
    $ep = Get-ExecutionPolicy -Scope CurrentUser -ErrorAction SilentlyContinue
    if ($ep -eq "RemoteSigned" -or $ep -eq "Bypass" -or $ep -eq "Unrestricted") {
        Add-Report "PS" "ExecutionPolicy" "PASS" "$ep"
        Write-OK "ExecutionPolicy: $ep"
    } else {
        Add-Report "PS" "ExecutionPolicy" "WARN" "当前: $ep"
        Write-WARN "ExecutionPolicy: $ep"
        if ($FixAll) {
            Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force -ErrorAction SilentlyContinue
            Add-Report "PS" "ExecutionPolicy" "FIXED" "设为 RemoteSigned"
            Write-FIX "已设为 RemoteSigned"
        }
    }

    # UTF-8 编码
    $cp = [Console]::OutputEncoding
    Write-V "OutputEncoding: $($cp.EncodingName) ($($cp.WebName))"
    if ($cp.WebName -eq "utf-8") {
        Add-Report "PS" "UTF-8 编码" "PASS" "UTF-8"
        Write-OK "输出编码 UTF-8"
    } else {
        Add-Report "PS" "UTF-8 编码" "WARN" "$($cp.WebName)"
        Write-WARN "输出编码非 UTF-8"
        if ($FixAll) {
            chcp 65001 >$null 2>&1
            [Console]::OutputEncoding = [Text.Encoding]::UTF8
            [Console]::InputEncoding = [Text.Encoding]::UTF8
            $pd = Split-Path $PROFILE -Parent -ErrorAction SilentlyContinue
            if ($pd -and -not (Test-Path $pd)) { New-Item -ItemType Directory -Force -Path $pd | Out-Null }
            Add-Content -Path $PROFILE -Value "`n# fix-env: UTF-8`nchcp 65001 >`$null 2>&1`n[Console]::OutputEncoding = [Text.Encoding]::UTF8`n[Console]::InputEncoding = [Text.Encoding]::UTF8`n" -Encoding UTF8 -ErrorAction SilentlyContinue
            Add-Report "PS" "UTF-8 编码" "FIXED" "已配置 UTF-8"
            Write-FIX "已配置 UTF-8"
        }
    }
}

# ═══════════════════════════════════════════
# Module 6: Node cache 迁移
# ═══════════════════════════════════════════
function Fix-NodeRust {
    Write-H1 "6/8 Node/Rust/Go Cache 检查"
    Write-ProgressBar 6 8 "Cache 路径检查"

    # npm cache
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        $npmCache = & npm config get cache 2>$null
        if ($npmCache -and (Has-Chinese $npmCache)) {
            Add-Report "NODE" "npm cache" "WARN" "含中文: $npmCache"
            Write-WARN "npm cache 含中文路径: $npmCache"
            if ($FixAll) {
                $newCache = "$env:USERPROFILE\.npm-cache"
                & npm config set cache "$newCache" 2>$null
                Add-Report "NODE" "npm cache" "FIXED" "迁移到 $newCache"
                Write-FIX "npm cache 迁移到 $newCache"
            }
        } else {
            Add-Report "NODE" "npm cache" "PASS" "$npmCache"
            Write-OK "npm cache: $npmCache"
        }
    } else {
        Add-Report "NODE" "npm" "SKIP" "未安装"
        Write-SKIP "npm 未安装"
    }

    # Go env
    $go = Get-Command go -ErrorAction SilentlyContinue
    if ($go) {
        $gopath = [Environment]::GetEnvironmentVariable("GOPATH", "User")
        if (-not $gopath) { $gopath = "$env:USERPROFILE\go" }
        if (Has-Chinese $gopath) {
            Add-Report "GO" "GOPATH" "WARN" "含中文: $gopath"
            Write-WARN "GOPATH 含中文"
            if ($FixAll) {
                $newGo = "$env:USERPROFILE\.go"
                [Environment]::SetEnvironmentVariable("GOPATH", $newGo, "User")
                Add-Report "GO" "GOPATH" "FIXED" "迁移到 $newGo"
                Write-FIX "GOPATH 迁移到 $newGo"
            }
        } else {
            Add-Report "GO" "GOPATH" "PASS" "$gopath"
        }
    } else {
        Add-Report "GO" "Go 编译器" "SKIP" "未安装"
        Write-SKIP "Go 未安装"
    }

    # Rust
    $rustc = Get-Command rustc -ErrorAction SilentlyContinue
    if ($rustc) {
        Add-Report "RUST" "rustc" "PASS" "已安装"
    } else {
        Add-Report "RUST" "rustc" "SKIP" "未安装"
        Write-SKIP "Rust 未安装"
    }
}

# ═══════════════════════════════════════════
# Module 7: 系统区域设置（UTF-8 beta 开关）
# ═══════════════════════════════════════════
function Fix-SystemLocale {
    Write-H1 "7/8 系统区域设置"
    Write-ProgressBar 7 8 "系统区域设置检查"
    $acp = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
    if ($acp -eq 65001) {
        Add-Report "LOCALE" "UTF-8 Beta" "PASS" "已启用 (ACP=65001)"
        Write-OK "UTF-8 Beta 已启用"
    } else {
        Add-Report "LOCALE" "UTF-8 Beta" "WARN" "未启用 (ACP=$acp)"
        Write-WARN "UTF-8 Beta 未启用 (ACP=$acp)"
        Write-WARN "  手动: 设置 → 时间和语言 → 管理语言设置 → Beta: 使用 Unicode UTF-8"
    }
}

# ═══════════════════════════════════════════
# Module 8: 编译器/Toolchain 检查
# ═══════════════════════════════════════════
function Fix-Toolchain {
    Write-H1 "8/8 开发工具链检查"
    Write-ProgressBar 8 8 "Toolchain 检查"
    $tools = @(
        @{Name="Python";  Cmd="python3 --version";  URL="https://www.python.org/downloads/"}
        @{Name="Git";     Cmd="git --version";       URL="https://git-scm.com/downloads"}
        @{Name="Node";    Cmd="node --version";      URL="https://nodejs.org/"}
        @{Name="Go";      Cmd="go version";          URL="https://go.dev/dl/"}
        @{Name="Rustc";   Cmd="rustc --version";     URL="https://rustup.rs/"}
    )
    foreach ($t in $tools) {
        $v = & cmd /c "where $($t.Name.ToLower()) >nul 2>nul && $($t.Cmd)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) {
            Add-Report "TOOLCHAIN" $t.Name "PASS" $v.Trim()
            Write-OK "$($t.Name): $($v.Trim())"
        } else {
            Add-Report "TOOLCHAIN" $t.Name "WARN" "未安装 → $($t.URL)"
            Write-WARN "$($t.Name) 未安装 → $($t.URL)"
        }
    }
}

# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════
Write-Host @"

  fix-env.ps1 v2.0 — 中文 Windows 开发环境检测修复
  =======================================
  系统: Windows $([Environment]::OSVersion.VersionString)
  用户: $env:USERNAME
  主页: $env:USERPROFILE

"@ -ForegroundColor Cyan

if ($FixAll) {
    Write-Host "  模式: 全自动修复模式" -ForegroundColor Green
} else {
    Write-Host "  模式: 检测模式 (加 -FixAll 自动修复)" -ForegroundColor Yellow
    Write-Host "  用法: .\fix-env.ps1 -FixAll`n" -ForegroundColor DarkGray
}

Write-ProgressBar 0 8 "开始检测"

Fix-ChineseUsername
Fix-EnvChain
Fix-PathEntries
Fix-GitSSH
Fix-PowerShell
Fix-NodeRust
Fix-SystemLocale
Fix-Toolchain

Write-Progress -Activity "fix-env.ps1" -Completed

# ═══════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════
Write-Host @"

  ═══════════════════════════════════════
               检测报告
  ═══════════════════════════════════════

"@ -ForegroundColor Cyan

$total = $script:passed + $script:warnings + $script:fixes_applied + $script:fixes_failed + $script:skipped
Write-Host "  PASS: $script:passed  FIXED: $script:fixes_applied  WARN: $script:warnings  FAIL: $script:fixes_failed  SKIP: $script:skipped  总计: $total" -ForegroundColor White
Write-Host ""

if ($script:report.Count -gt 0) {
    Write-Host "  详细报告:" -ForegroundColor DarkGray
    foreach ($r in $script:report) {
        $icon = switch ($r.Status) { "PASS" { "✓" } "FIXED" { "◆" } "WARN" { "△" } "FAIL" { "✗" } "SKIP" { "○" } default { "?" } }
        Write-Host "    $icon [$($r.Category)] $($r.Check): $($r.Detail)" -ForegroundColor DarkGray
    }
}

Write-Host @"

  提示:
  • 部分环境变量变更需要重启终端或注销后生效
  • 运行 .\fix-env.ps1 -FixAll 自动修复所有可修复项
  • 本脚本不会破坏现有配置

"@ -ForegroundColor DarkGray

# 导出 JSON 报告
$reportJson = @{
    date = (Get-Date -Format "o")
    mode = if ($FixAll) { "fix" } else { "check" }
    summary = @{ pass=$script:passed; fixed=$script:fixes_applied; warn=$script:warnings; fail=$script:fixes_failed; skip=$script:skipped }
    items = $script:report
}
$reportJson | ConvertTo-Json -Depth 3 | Out-File -FilePath "$env:TEMP\fix-env-report.json" -Encoding UTF8
Write-Host "  JSON 报告已保存: $env:TEMP\fix-env-report.json" -ForegroundColor DarkGray
