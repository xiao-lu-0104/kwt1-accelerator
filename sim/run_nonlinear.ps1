# Focused regression for retimed LayerNorm and four-lane Softmax.
$ErrorActionPreference = 'Stop'
$bin = 'D:\Xilinx\Vivado\2022.2\bin'
function Invoke-Checked([string]$tool, [string[]]$toolArgs) {
    $result = & (Join-Path $bin "$tool.bat") @toolArgs 2>&1
    $code = $LASTEXITCODE
    $result | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) { throw "$tool failed ($code)" }
    return $result
}
Push-Location $PSScriptRoot
try {
    $null = Invoke-Checked 'xvlog' @('-sv', '../rtl/kwt_mul_pipe.v', '../rtl/kwt_exp_lut.v',
        '../rtl/kwt_softmax4.v', '../rtl/kwt_rsqrt_lut.v', '../rtl/kwt_layernorm.v',
        '../rtl/reference/kwt_layernorm_pre_output_pipe.v', '../tb/tb_kwt_mul_pipe.v',
        '../rtl/kwt_gelu_lut.v', '../rtl/kwt_requant_pipe.v', '../tb/tb_kwt_requant_pipe.v',
        '../rtl/kwt_mac16x4_pipe.v', '../tb/tb_kwt_mac16x4_pipe.v',
        '../rtl/kwt_align_add.v', '../rtl/kwt_align_add_pipe.v', '../tb/tb_kwt_align_add_pipe.v',
        '../tb/tb_kwt_softmax4.v', '../tb/tb_kwt_layernorm.v', '../tb/tb_kwt_layernorm_pipe.v')
    foreach ($test in @('kwt_mul_pipe', 'kwt_mac16x4_pipe', 'kwt_requant_pipe', 'kwt_align_add_pipe', 'kwt_softmax4', 'kwt_layernorm', 'kwt_layernorm_pipe')) {
        $snap = "${test}_check_snap"
        $null = Invoke-Checked 'xelab' @("tb_$test", '-s', $snap)
        $result = Invoke-Checked 'xsim' @($snap, '-R', '-log', "$snap.log")
        if (($result -match 'FAIL:|ERROR:|MISMATCH|FATAL:') -or -not ($result -match 'PASS:')) {
            throw "$test failed"
        }
    }
    Write-Host 'All nonlinear checks passed.'
} finally { Pop-Location }
