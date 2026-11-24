set Sources {}
foreach Name {TpuPkg.sv TpuLut.sv TpuDot.sv TpuDivide.sv TpuSqrt.sv TpuSram.sv TpuRowBuffer.sv TpuMatmul.sv TpuGelu.sv TpuVector.sv TpuDma.sv TpuTop.sv TpuNice.sv TpuIcb.sv e203_subsys_nice_core.sv SpFoundry.sv} {lappend Sources [file join $::env(TPU_SHARED_SOURCE) $Name]}
