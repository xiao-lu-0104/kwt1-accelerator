# ---------------------------------------------------------------------------
# 打包初赛提交材料
#
#   .\tools\make_release.ps1                # 生成 release\KWT1_<日期>\
#   .\tools\make_release.ps1 -Zip           # 同时压缩成 zip
#
# 只打包"可复现"的必要内容：已验证的 RTL/TB 快照、数值模型、向量、脚本、文档。
# 不包含 external/（官方代码）与 data/（数据集），避免体积过大。
# ---------------------------------------------------------------------------

param(
    [switch]$Zip,
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stamp = Get-Date -Format "yyyyMMdd"
if ($Tag -eq "") { $Tag = "KWT1_$stamp" }
$dest = Join-Path $root "release\$Tag"

Write-Host "==> packaging to $dest" -ForegroundColor Cyan
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Path $dest | Out-Null

# ------------------------------------------------------------------ content
$items = @(
    @{ Src = "rtl_verified"; Dst = "rtl" },
    @{ Src = "tb_verified";  Dst = "tb"  },
    @{ Src = "tools";        Dst = "tools" },
    @{ Src = "doc";          Dst = "doc" },
    @{ Src = "syn";          Dst = "syn" },
    @{ Src = "sim\run_all.ps1"; Dst = "sim\run_all.ps1" },
    @{ Src = "README.md";    Dst = "README.md" }
)

foreach ($it in $items) {
    $src = Join-Path $root $it.Src
    $dst = Join-Path $dest $it.Dst
    if (-not (Test-Path $src)) {
        Write-Host "    skip (missing): $($it.Src)" -ForegroundColor Yellow
        continue
    }
    if ((Get-Item $src).PSIsContainer) {
        Copy-Item $src $dst -Recurse -Force
        # drop bulky/generated content that is not needed to reproduce
        Remove-Item (Join-Path $dst "out") -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $dst "__pycache__") -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        $dir = Split-Path -Parent $dst
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        Copy-Item $src $dst -Force
    }
    Write-Host "    + $($it.Src)"
}

# scales.json is required to regenerate vectors
$scales = Join-Path $root "models\quant\scales.json"
if (Test-Path $scales) {
    New-Item -ItemType Directory -Path (Join-Path $dest "models\quant") -Force | Out-Null
    Copy-Item $scales (Join-Path $dest "models\quant\scales.json") -Force
    Write-Host "    + models/quant/scales.json"
}

# ------------------------------------------------------------------ manifest
$lines = @()
$lines += "# 提交清单 $Tag"
$lines += ""
$lines += "生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += ""
$lines += "## 已验证指标"
$lines += ""
$lines += "| 项 | 值 |"
$lines += "|---|---|"
$lines += "| 整机周期 | 1,477,755（9.85 ms @150 MHz） |"
$lines += "| 定点精度 | 96.17 %（浮点 97.33 %，-1.17 pp） |"
$lines += "| 量化 | 权重 int4 per-output-channel，激活 int8 |"
$lines += "| 功能验证 | 全部 15 个 TB bit-exact，整机 3/3 样本 |"
$lines += ""
$lines += "## 目录"
$lines += ""
$lines += "- ``rtl/`` 19 个可综合模块"
$lines += "- ``tb/`` 15 个 testbench"
$lines += "- ``tools/`` 数值模型、标定、向量生成"
$lines += "- ``sim/run_all.ps1`` 一键回归"
$lines += "- ``syn/`` 综合脚本（Artix-7 估算，库到位后替换 target）"
$lines += "- ``doc/`` 00–09 设计文档"
$lines += ""
$lines += "## 复现步骤"
$lines += ""
$lines += '```powershell'
$lines += 'cd sim'
$lines += '.\run_all.ps1'
$lines += '```'
$lines += ""
$lines += "## 文件校验（MD5）"
$lines += ""
$lines += "| 文件 | MD5 |"
$lines += "|---|---|"
Get-ChildItem $dest -Recurse -File | Where-Object { $_.Name -ne "MANIFEST.md" } |
    Sort-Object FullName | ForEach-Object {
        $rel = $_.FullName.Substring($dest.Length + 1).Replace("\", "/")
        $h = (Get-FileHash $_.FullName -Algorithm MD5).Hash
        $lines += "| $rel | $h |"
    }

$lines | Set-Content -Path (Join-Path $dest "MANIFEST.md") -Encoding utf8
Write-Host "    + MANIFEST.md"

$count = (Get-ChildItem $dest -Recurse -File).Count
$size  = [math]::Round(((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2)
Write-Host "==> $count files, $size MB" -ForegroundColor Green

# ------------------------------------------------------------------ zip
if ($Zip) {
    $zipPath = Join-Path $root "release\$Tag.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path $dest -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host "==> $zipPath" -ForegroundColor Green
}
