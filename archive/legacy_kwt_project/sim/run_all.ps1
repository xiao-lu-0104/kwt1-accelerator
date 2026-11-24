# 一键回归：生成向量 → 编译 → 逐级仿真
# 用法：在 e:\chipdesign\sim 下执行  .\run_all.ps1
#     或  .\run_all.ps1 -SkipVectors   (复用已有向量)

param(
    [switch]$SkipVectors,
    [switch]$OnlyTop,
    [switch]$CompareLegacy
)

$ErrorActionPreference = "Stop"
$XVLOG = "D:\Xilinx\Vivado\2022.2\bin\xvlog.bat"
$XELAB = "D:\Xilinx\Vivado\2022.2\bin\xelab.bat"
$XSIM  = "D:\Xilinx\Vivado\2022.2\bin\xsim.bat"
$PY    = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"

$RTL = @(
    "..\rtl\kwt_dot64.v",
    "..\rtl\kwt_gemm4.v",
    "..\rtl\kwt_gemm_engine.v",
    "..\rtl\kwt_requant.v",
    "..\rtl\kwt_exp_lut.v",
    "..\rtl\kwt_softmax.v",
    "..\rtl\kwt_softmax4.v",
    "..\rtl\kwt_rsqrt_lut.v",
    "..\rtl\kwt_mul_pipe.v",
    "..\rtl\kwt_layernorm.v",
    "..\rtl\kwt_gelu_lut.v",
    "..\rtl\kwt_gelu.v",
    "..\rtl\kwt_attn_qkv.v",
    "..\rtl\kwt_attn_score.v",
    "..\rtl\kwt_attn_av.v",
    "..\rtl\kwt_attention.v",
    "..\rtl\kwt_align_add.v",
    "..\rtl\kwt_align_add_pipe.v",
    "..\rtl\kwt_encoder_layer.v",
    "..\rtl\kwt_encoder_12.v",
    "..\rtl\kwt_top.v",
    "..\rtl\kwt_axi_slave.v",
    "..\rtl\kwt_axi_top.v",
    "..\rtl\kwt_sram_2p.v",
    "..\rtl\kwt_mem16.v",
    "..\rtl\kwt_mac16x4.v",
    "..\rtl\kwt_mac16x4_pipe.v",
    "..\rtl\kwt_requant_pipe.v",
    "..\rtl\kwt_encoder_layer_compact.v"
)

Set-Location $PSScriptRoot
function Invoke-Checked {
    param([string]$Tool, [string[]]$ToolArgs)
    $output = & $Tool @ToolArgs 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) { throw "$Tool failed (exit $code)" }
    return $output
}

function Run-Test {
    param([string]$Tb, [string]$Snap, [string]$Pattern = "PASS:|FAIL:")
    Write-Host "`n=== $Tb ===" -ForegroundColor Cyan
    $null = Invoke-Checked $XELAB @($Tb, "-s", $Snap, "--debug", "typical")
    $output = Invoke-Checked $XSIM @($Snap, "-R")
    if (($output -match 'FAIL:|ERROR:|MISMATCH|FATAL:') -or -not ($output -match 'PASS:')) {
        throw "$Tb did not pass"
    }
}

# ---------------------------------------------------------------- vectors
if (-not $SkipVectors) {
    Write-Host "Generating vectors..." -ForegroundColor Cyan
    Push-Location ..
    foreach ($generator in @("calibrate.py", "gen_softmax_vectors.py", "gen_attention_vectors.py",
                              "gen_encoder_vectors.py", "gen_encoder12_vectors.py",
                              "gen_top_vectors.py")) {
        $null = Invoke-Checked $PY @("tools\$generator")
    }
    Pop-Location
}

# ---------------------------------------------------------------- compile
Write-Host "`nCompiling RTL..." -ForegroundColor Cyan
$tb = if ($OnlyTop) { @("..\tb\tb_kwt_top.v") }
      else { @("..\tb\tb_kwt_attention.v", "..\tb\tb_kwt_encoder_layer.v",
               "..\tb\tb_kwt_encoder_layer_compact.v", "..\tb\tb_kwt_encoder_12.v", "..\tb\tb_kwt_top.v",
               "..\tb\tb_kwt_encoder_12_legacy.v",
               "..\tb\tb_kwt_axi_slave.v", "..\tb\tb_kwt_dot64_tree.v",
               "..\tb\tb_kwt_mac16x4.v", "..\tb\tb_kwt_packed_sram.v", "..\tb\tb_kwt_softmax_serial.v",
               "..\tb\tb_kwt_mfcc_map.v", "..\tb\tb_kwt_axi_top_load.v") }
$null = Invoke-Checked $XVLOG (@("-sv") + $RTL + $tb)

# ---------------------------------------------------------------- simulate
if (-not $OnlyTop) {
    Run-Test "tb_kwt_packed_sram" "compact_mem_snap"
    Run-Test "tb_kwt_mac16x4" "compact_mac_snap"
    Run-Test "tb_kwt_softmax_serial" "serial_sm_snap"
    Run-Test "tb_kwt_dot64_tree" "dot_tree_snap"
    Run-Test "tb_kwt_mfcc_map" "mfcc_map_snap"
    Run-Test "tb_kwt_axi_top_load" "axi_top_load_snap"
    Run-Test "tb_kwt_attention"     "attn_snap"  "PASS:|FAIL:|cycles="
    Run-Test "tb_kwt_encoder_layer" "enc_snap"   "PASS:|FAIL:|cycles="
    Run-Test "tb_kwt_encoder_layer_compact" "compact_layer_snap"
    Run-Test "tb_kwt_encoder_12"    "enc12_snap" "PASS:|FAIL:|cycles="
    if ($CompareLegacy) { Run-Test "tb_kwt_encoder_12_legacy" "enc12_legacy_snap" }
    Run-Test "tb_kwt_axi_slave"     "axi_snap"   "PASS:|FAIL:"
}
Run-Test "tb_kwt_top" "top_snap" "PASS:|FAIL:|sample |cycles="

Write-Host "`nAll simulations finished." -ForegroundColor Green
