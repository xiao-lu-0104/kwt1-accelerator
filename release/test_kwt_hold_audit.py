from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tkinter

root = Path(__file__).resolve().parents[1]
base = root / 'release/kwt_hold_audit_fixture'
base.mkdir(exist_ok=True)
tcl_script = root / 'syn/audit_kwt_hold.tcl'
for name in ('std.db', 'RAMTP1024X16_tt_1p10v_1p10v_25c.db', 'baseline.ddc'):
    (base / name).write_text('fixture\n')

def check_tcl(mode):
    clock_mode = mode.startswith('clock_')
    interp = tkinter.Tcl()
    assert interp.call('info', 'complete', tcl_script.read_text()) == 1
    outputs, exits, commands = [], [], []
    state = {'zero': False, 'sdc_writes': 0}
    def seq(value):
        return list(value) if isinstance(value, tuple) else list(interp.splitlist(value))
    def get_attr(obj, attr):
        if attr == 'period': return '6.667'
        if attr == 'ref_name': return 'RAMTP1024X16' if obj.startswith('macro') else 'STD'
        if attr == 'slack':
            if obj == 'clock_min_path': return '-0.100'
            if obj == 'data_min_path': return '0.010'
            if obj == 'max_path': return '0.050' if mode == 'setup_drift' and state['zero'] else '0.049'
            return str(-1.04846 + int(state['zero']))
        raise AssertionError((obj, attr))
    def reports(*args):
        commands.append(args)
        assert '>' in args
        Path(args[-1]).write_text('fixture report\n')
        return ''
    def sdc(*args):
        state['sdc_writes'] += 1
        Path(args[-1]).write_text(f'# generated time {state["sdc_writes"]}\ncreate_clock -period 6.667 [get_ports clk]\n'
            'set_clock_uncertainty -setup 1.0 [get_clocks clk]\n'
            f'set_clock_uncertainty -hold {0 if state["zero"] else 1} [get_clocks clk]\n'
            + ('set_false_path -from input\n' if mode == 'clock_budget_drift' and state['sdc_writes'] > 1 else ''))
        return ''
    def uncertainty(*args):
        assert not clock_mode, 'clock audit must preserve every constraint'
        assert args == ('-hold', '0.0', 'clk')
        state['zero'] = True
        commands.append(('set_clock_uncertainty', *args))
        return ''
    def exit_cmd(code):
        exits.append(int(code))
        if int(code): raise tkinter.TclError('exit')
        return ''
    mappings = {
        'read_ddc': lambda *a: commands.append(('read_ddc', *a)) or '',
        'current_design': lambda *a: '',
        'link': lambda: '0' if mode == 'bad_link' else '1',
        'get_clocks': lambda *a: ('clk',),
        'get_object_name': lambda a: a,
        'sizeof_collection': lambda a: len(seq(a)),
        'get_attribute': get_attr,
        'get_cells': lambda *a: tuple(f'macro{i}' for i in range(39 if mode == 'bad_count' else 40))
            if a[-1] == 'ref_name == RAMTP1024X16' else ('macro0', 'std'),
        'get_lib_cells': lambda *a: () if mode == 'bad_lib' else ('lib/cell',),
        'get_pins': lambda *a: tuple('macro_clk%d' % i for i in range(79 if mode == 'clock_bad_count' else 80))
            if a[-1] == 'full_name =~ */CLKA || full_name =~ */CLKB' else ('macro_db',),
        'all_registers': lambda *a: ('macro_db', 'reg_d'),
        'all_outputs': lambda: ('top_output',),
        'add_to_collection': lambda a, b: tuple(dict.fromkeys(seq(a) + seq(b))),
        'remove_from_collection': lambda a, b: tuple(x for x in seq(a) if x not in seq(b)),
        'get_timing_paths': lambda *a: () if mode == 'no_paths' else
            ('max_path',) if a[a.index('-delay_type') + 1] == 'max' else
            ('clock_min_path',) if clock_mode and '-to' in a and 'macro_clk' in a[a.index('-to')+1] else
            ('data_min_path',) if clock_mode and ('-to' in a or '-through' in a) else ('min_path',),
        'write_sdc': sdc,
        'set_clock_uncertainty': uncertainty,
        'puts': lambda *a: outputs.append(' '.join(a)) or '',
        'exit': exit_cmd,
    }
    for cmd in ('report_area', 'report_qor', 'check_timing', 'report_timing'):
        mappings[cmd] = reports
    for cmd, fn in mappings.items(): interp.createcommand(cmd, fn)
    interp.eval('proc foreach_in_collection {v xs body} {upvar 1 $v x; foreach x $xs {uplevel 1 $body}}')
    env = {'KWT_DC_CHECKPOINT': base / 'baseline.ddc', 'KWT_STDCELL_DB': base / 'std.db',
           'KWT_SRAM_DB_DIR': base, 'KWT_DC_REPORT_DIR': base / mode}
    for key, value in env.items(): interp.setvar(f'env({key})', value.as_posix())
    interp.eval('unset -nocomplain env(KWT_DC_AUDIT_SRAM_CLOCKS)')
    if clock_mode: interp.setvar('env(KWT_DC_AUDIT_SRAM_CLOCKS)', '1')
    try: interp.eval(tcl_script.read_text())
    except tkinter.TclError:
        if not exits or exits[-1] != 1: raise
    if mode in ('good', 'clock_good'):
        assert exits == [0], outputs
        if clock_mode:
            assert 'KWT_SRAM_CLOCK_AUDIT_COMPLETE' in outputs
            assert any('CLOCK_AUDIT_DATA_ENDPOINT_HOLD_WNS: 0.010' in x for x in outputs)
            assert any('CLOCK_AUDIT_SRAM_CLOCK_PIN_HOLD_WNS: -0.100' in x for x in outputs)
            assert not any(x[0] == 'set_clock_uncertainty' for x in commands)
        else:
            assert 'KWT_HOLD_AUDIT_COMPLETE' in outputs
            assert any('AUDIT_ACCEPTANCE: NONE' in x for x in outputs)
            assert sum(x[0] == 'set_clock_uncertainty' for x in commands) == 1
    else:
        assert exits == [1], (mode, outputs, exits)
        assert 'KWT_HOLD_AUDIT_COMPLETE' not in outputs
        assert 'KWT_SRAM_CLOCK_AUDIT_COMPLETE' not in outputs

for mode in ('good', 'bad_link', 'bad_count', 'bad_lib', 'no_paths', 'setup_drift',
             'clock_good', 'clock_bad_count', 'clock_budget_drift'):
    check_tcl(mode)
print('PASS: audit Tcl, real-library/count/path guards, setup invariance, no closure claim')

package, run, binaries = base / 'package', base / 'run', base / 'bin'
for directory in (package / 'syn', package / 'tools', run / 'sram_db', run / 'dc_out_bound', binaries):
    directory.mkdir(parents=True, exist_ok=True)
for file in ('syn/audit_kwt_hold.tcl', 'tools/rerun_kwt_sram_synthesis.sh'):
    shutil.copyfile(root / file, package / file)
(run / 'results.tsv').write_text(''.join(name + '\tPASS\n' for name in (
    'tb_kwt_foundry_sram16', 'tb_kwt_packed_sram', 'tb_kwt_encoder_12', 'library_conversion')))
(run / 'input.txt').write_text('verified fixture\n')
digest = hashlib.sha256((run / 'input.txt').read_bytes()).hexdigest()
# Relative record is intentional: exercise original runner with its cwd set to run.
for record in ('source_sha256.txt', 'vector_sha256.txt', 'liberty_sha256.txt'):
    (run / record).write_text(digest + '  input.txt\n', newline='\n')
(run / 'sram_db/RAMTP1024X16_tt_1p10v_1p10v_25c.db').write_text('fixture db\n')
checkpoint = run / 'dc_out_bound/kwt_encoder_12_compiled.ddc'
checkpoint.write_text('baseline checkpoint\n')
(binaries / 'dc_shell').write_text('''#!/usr/bin/env bash
set -eu
[[ ${KWT_DC_FIX_HOLD:-} != 1 && -s ${KWT_DC_CHECKPOINT:-} ]] || exit 3
[[ $2 == */audit_kwt_hold.tcl ]] || exit 4
case ${MOCK_AUDIT_MODE:-good} in
  bad) exit 9;;
  incomplete) echo "incomplete";;
  mutate) echo changed >> "$KWT_DC_CHECKPOINT"; echo KWT_HOLD_AUDIT_COMPLETE;;
  good) echo 'AUDIT_ACCEPTANCE: NONE'; echo KWT_HOLD_AUDIT_COMPLETE;;
esac
''', newline='\n')
bash = 'C:/Program Files/Git/bin/bash.exe'
bin_path = '/' + binaries.drive[0].lower() + binaries.as_posix()[2:]
command = f'export PATH="{bin_path}:$PATH"; bash "{(package / "tools/rerun_kwt_sram_synthesis.sh").as_posix()}" --run-dir "{run.as_posix()}" --audit-hold'
for mode in ('good', 'bad', 'incomplete', 'mutate'):
    env = dict(os.environ, MOCK_AUDIT_MODE=mode)
    result = subprocess.run([bash, '-c', command], cwd=run, env=env, capture_output=True, text=True)
    assert (result.returncode == 0) == (mode == 'good'), (mode, result.stdout, result.stderr)
    checkpoint.write_text('baseline checkpoint\n')
checkpoint.rename(checkpoint.with_suffix('.saved'))
result = subprocess.run([bash, '-c', command], cwd=run, capture_output=True, text=True)
assert result.returncode != 0 and 'requires a compiled checkpoint' in result.stdout, result.stdout
checkpoint.with_suffix('.saved').rename(checkpoint)
print('PASS: runner audit selection, failure/missing-marker propagation, immutable input and checkpoint guards')
