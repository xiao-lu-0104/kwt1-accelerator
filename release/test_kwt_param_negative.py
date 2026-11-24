from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
bin_dir=Path('D:/Xilinx/Vivado/2022.2/bin')
source=(root/'rtl/kwt_encoder_12.v').read_text()
variants={
    'length_truncation':source.replace('function [15:0] wlen','function [13:0] wlen').replace('NW4[15:0] : NWF[15:0]','NW4[13:0] : NWF[13:0]'),
    'ignored_valid':source.replace('wire load_accept = (PARAM_HANDSHAKE == 0) || param_valid;','wire load_accept = 1\'b1;'),
}
for name,text in variants.items():
    work=root/'release'/('param_negative_'+name);work.mkdir(exist_ok=True)
    (work/'mutated.v').write_text(text)
    sources=[str(p) for p in (root/'rtl').glob('*.v') if p.name!='kwt_encoder_12.v']
    commands=[['xvlog','--sv','-d','KWT_ASIC_SRAM','-d','KWT_LOCAL_SRAM_CONTRACT','-i',str(root/'rtl')]+sources+['mutated.v',str(root/'tb/models/kwt_ramtp_contract.v'),str(root/'tb/tb_kwt_encoder_param_load.v')],
              ['xelab','tb_kwt_encoder_param_load','-s','negative','-mt','2'],['xsim','negative','-runall']]
    for command in commands:
        result=subprocess.run([str(bin_dir/(command[0]+'.bat'))]+command[1:],cwd=work,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (work/(command[0]+'.log')).write_text(result.stdout)
        if command[0]!='xsim' and result.returncode:raise RuntimeError(result.stdout)
    assert 'Fatal:' in result.stdout and 'PASS: encoder parameter loading contract' not in result.stdout,result.stdout
    print('PASS: negative control rejected '+name)
