"""Build a local interface-lint file list; not the authoritative competition source."""
from pathlib import Path
import re
import shutil
import sys

repo=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1])
platform=out/'local_platform'
shutil.copytree(repo/'workspace/Backend/Local20261102Soc30Tpu150/Sources/e203_hbirdv2/rtl/e203',platform)
config=platform/'core/config.v'; text=config.read_text()
for kind in ('ITCM','DTCM'):
    text,count=re.subn(r'(?m)^(`define\s+E203_CFG_'+kind+r'_ADDR_WIDTH\s+)16\b',r'\g<1>18',text)
    if count!=1: raise ValueError('Expected local comparison 64KiB width')
config.write_text(text)
names='TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice TpuIcb'.split()
files=[repo/'rtl'/(name+'.sv') for name in names]+[repo/'Backend/e203_subsys_nice_core.sv',
    repo/'Server/Backend/SpFoundry.sv',repo/'Server/SystemBackend/TcmMacro.sv']
files += [p for p in sorted(platform.rglob('*.v')) if p.name not in ('sirv_gnrl_ram.v','e203_subsys_nice_core.v')]
(out/'CpuLint.f').write_text('+define+SYNTHESIS+FPGA+FPGA_SOURCE+TPU_SRAM_MODEL\n'+
    '\n'.join('+incdir+'+str(p) for p in sorted({p.parent for p in platform.rglob('*.v')}))+'\n'+
    '\n'.join(str(p) for p in files)+'\n')
# Private macro shape fixture for source-interface lint only.
(out/'PrivateMacroFixture.sv').write_text('''module RAMSP1024X16(output [15:0] Q,input CLK,CEN,GWEN,input [15:0] WEN,D,
input [9:0] A,input [2:0] EMA,input [1:0] EMAW,input RET1N);
assign Q=16'h0;
endmodule
''')
