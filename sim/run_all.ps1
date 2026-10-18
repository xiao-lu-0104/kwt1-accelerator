# 一键回归：生成向量 → 编译 → 逐级仿真
# 用法：在 e:\chipdesign\sim 下执行  .\run_all.ps1
#     或  .\run_all.ps1 -SkipVectors   (复用已有向量)

param(
    [switch]$SkipVectors,
    [switch]$OnlyTop
)

$ErrorActionPreference = "Stop"
$XVLOG = "D:\Xilinx\Vivado\2022.2\bin\xvlog.bat"
$XELAB = "D:\Xilinx\Vivado\2022.2\bin\xelab.bat"
$XSIM  = "D:\Xilinx\Vivado\2022.2\bin\xsim.bat"
$PY    = "..\.venv\Scripts\python.exe"

$RTL = @(
    "..\rtl\kwt_dot64.v",
    "..\rtl\kwt_gemm4.v",
    "..\rtl\kwt_gemm_engine.v",
    "..\rtl\kwt_requant.v",
    "..\rtl\kwt_exp_lut.v",
    "..\rtl\kwt_softmax.v",
    "..\rtl\kwt_rsqrt_lut.v",
    "..\rtl\kwt_layernorm.v",
    "..\rtl\kwt_gelu_lut.v",
    "..\rtl\kwt_gelu.v",
    "..\rtl\kwt_attn_qkv.v",
    "..\rtl\kwt_attn_score.v",
    "..\rtl\kwt_attn_av.v",
    "..\rtl\kwt_attention.v",
    "..\rtl\kwt_align_add.v",
    "..\rtl\kwt_encoder_layer.v",
    "..\rtl\kwt_encoder_12.v",
    "..\rtl\kwt_top.v",
    "..\rtl\kwt_axi_slave.v"
)

function Clear-XsimLock {
    Get-Process | Where-Object { $_.ProcessName -like '*xsim*' } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
}

function Run-Test {
    param([string]$Tb, [string]$Snap, [string]$Pattern = "PASS:|FAIL:")
    Clear-XsimLock
    Remove-Item -Recurse -Force "xsim.dir\$Snap" -ErrorAction SilentlyContinue
    Write-Host "`n=== $Tb ===" -ForegroundColor Cyan
    & $XELAB $Tb -s $Snap --debug typical 2>&1 | Select-String "ERROR" | Select-Object -First 3
    & $XSIM $Snap -R 2>&1 | Select-String -Pattern $Pattern
}

# ---------------------------------------------------------------- vectors
if (-not $SkipVectors) {
    Write-Host "Generating vectors..." -ForegroundColor Cyan
    Push-Location ..
    & $PY tools\calibrate.py            | Select-Object -Last 1
    & $PY tools\gen_attention_vectors.py
    & $PY tools\gen_encoder_vectors.py
    & $PY tools\gen_encoder12_vectors.py
    & $PY tools\gen_top_vectors.py
    Pop-Location
}

# ---------------------------------------------------------------- compile
Write-Host "`nCompiling RTL..." -ForegroundColor Cyan
$tb = if ($OnlyTop) { @("..\tb\tb_kwt_top.v") }
      else { @("..\tb\tb_kwt_attention.v", "..\tb\tb_kwt_encoder_layer.v",
               "..\tb\tb_kwt_encoder_12.v", "..\tb\tb_kwt_top.v",
               "..\tb\tb_kwt_axi_slave.v") }
& $XVLOG -sv @RTL @tb 2>&1 | Select-String "ERROR" | Select-Object -First 5

# ---------------------------------------------------------------- simulate
if (-not $OnlyTop) {
    Run-Test "tb_kwt_attention"     "attn_snap"  "PASS:|FAIL:|cycles="
    Run-Test "tb_kwt_encoder_layer" "enc_snap"   "PASS:|FAIL:|cycles="
    Run-Test "tb_kwt_encoder_12"    "enc12_snap" "PASS:|FAIL:|cycles="
    Run-Test "tb_kwt_axi_slave"     "axi_snap"   "PASS:|FAIL:"
}
Run-Test "tb_kwt_top" "top_snap" "PASS:|FAIL:|sample |cycles="

Write-Host "`nAll simulations finished." -ForegroundColor Green
