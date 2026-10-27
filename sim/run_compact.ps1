# Focused compact-encoder regression; reuses the existing golden vectors.
# -Compare: frozen v1 and pipelined wide-K/V ablations before the default.
# -CompareSoftmax: same retimed datapath, serial versus four-lane Softmax.
# -IncludeTop: also run the three MFCC-to-classifier samples.
param([switch]$Compare, [switch]$CompareSoftmax, [switch]$IncludeTop, [switch]$OnlyLayer)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bin = 'D:\Xilinx\Vivado\2022.2\bin'
# Keep leaf-first order, matching the established Vivado regression flow.
$rtl = @('kwt_dot64', 'kwt_gemm4', 'kwt_gemm_engine', 'kwt_requant',
    'kwt_exp_lut', 'kwt_softmax', 'kwt_softmax4', 'kwt_rsqrt_lut', 'kwt_mul_pipe', 'kwt_layernorm',
    'kwt_gelu_lut', 'kwt_gelu', 'kwt_attn_qkv', 'kwt_attn_score',
    'kwt_attn_av', 'kwt_attention', 'kwt_align_add', 'kwt_align_add_pipe', 'kwt_encoder_layer',
    'kwt_encoder_12', 'kwt_top', 'kwt_axi_slave', 'kwt_axi_top',
    'kwt_sram_2p', 'kwt_mem16', 'kwt_mac16x4', 'kwt_mac16x4_pipe', 'kwt_requant_pipe', 'kwt_encoder_layer_compact') |
    ForEach-Object { "../rtl/$_.v" }
$layerTb = '../tb/tb_kwt_encoder_layer_compact.v'

function Invoke-Tool {
    param([string]$Name, [string[]]$Arguments)
    $result = & (Join-Path $bin "$Name.bat") @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $result | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "$Name failed, exit $exitCode" }
    return $result
}
function Run-Case {
    param([string]$Top, [string]$Snapshot)
    $null = Invoke-Tool 'xelab' @($Top, '-s', $Snapshot, '--debug', 'typical')
    $result = Invoke-Tool 'xsim' @($Snapshot, '-R', '-log', "$Snapshot.log")
    if (($result -match 'FAIL:|ERROR:|MISMATCH|FATAL:') -or -not ($result -match 'PASS:')) {
        throw "$Top failed"
    }
}
Push-Location $PSScriptRoot
try {
    if ($Compare) {
        $baseline = '../rtl/reference/kwt_encoder_layer_compact_v1.v'
        $null = Invoke-Tool 'xvlog' (@('-sv', '-d', 'KWT_COMPACT_BASELINE') + $rtl + @($baseline, $layerTb))
        Run-Case 'tb_kwt_encoder_layer_compact' 'compact_v1_profile_snap'
    }
    $tb = @($layerTb, '../tb/tb_kwt_encoder_layer_compact_wide.v', '../tb/tb_kwt_encoder_layer_compact_sm1.v',
                     '../tb/tb_kwt_encoder_12.v', '../tb/tb_kwt_top.v')
    $null = Invoke-Tool 'xvlog' (@('-sv') + $rtl + $tb)
    if ($Compare) { Run-Case 'tb_kwt_encoder_layer_compact_wide' 'compact_v2_wide_layer_snap' }
    if ($CompareSoftmax) { Run-Case 'tb_kwt_encoder_layer_compact_sm1' 'compact_sm1_layer_snap' }
    Run-Case 'tb_kwt_encoder_layer_compact' 'compact_v2_layer_snap'
    if (-not $OnlyLayer) { Run-Case 'tb_kwt_encoder_12' 'compact_v2_enc12_snap' }
    if ($IncludeTop) { Run-Case 'tb_kwt_top' 'compact_v2_top_snap' }
    Write-Host 'All compact checks passed.'
} finally {
    Pop-Location
}
