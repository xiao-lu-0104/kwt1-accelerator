import pathlib
import subprocess
root = pathlib.Path(__file__).resolve().parents[1]
bin_dir = pathlib.Path('D:/Xilinx/Vivado/2022.2/bin')
source = (root/'rtl/kwt_foundry_sram16.v').read_text()
variants = {
    'coedge': (source.replace('wire write_clock = ~clk;', 'wire write_clock = clk;'), 'LOCAL_CONTRACT_COLLISION'),
    'unstaged': (source.replace('write_enable ?', 'we ?').replace('wire bank_we=write_enable', 'wire bank_we=we').replace('(write_address >> 10)', '(wa >> 10)').replace('.AB(write_address)', '.AB(wa)').replace('.AB(write_address[9:0])', '.AB(wa[9:0])').replace('.DB(write_data)', '.DB(wd)'), 'Phase depth='),
}
for name, (mutated, marker) in variants.items():
    work = root/'release'/('phase_negative_'+name)
    work.mkdir(exist_ok=True)
    (work/'mutated.v').write_text(mutated)
    commands = [
        ['xvlog', '--sv', '-d', 'KWT_ASIC_SRAM', '-d', 'KWT_LOCAL_SRAM_CONTRACT', '-i', str(root/'rtl'), str(root/'tb/models/kwt_ramtp_contract.v'), 'mutated.v', str(root/'rtl/kwt_mem16.v'), str(root/'tb/tb_kwt_sram_phase.v')],
        ['xelab', 'tb_kwt_sram_phase', '-s', 'negative', '-mt', '2'],
        ['xsim', 'negative', '-runall'],
    ]
    for command in commands:
        result = subprocess.run([str(bin_dir/(command[0]+'.bat'))]+command[1:], cwd=str(work), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (work/(command[0]+'.log')).write_text(result.stdout)
        if command[0] != 'xsim' and result.returncode:
            raise RuntimeError(result.stdout)
    if marker not in result.stdout or 'PASS: split-phase SRAM contract' in result.stdout:
        raise RuntimeError('negative test did not reject '+name+'\n'+result.stdout)
    print('PASS: negative control rejected '+name)
