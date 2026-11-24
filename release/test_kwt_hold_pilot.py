from pathlib import Path
import os
import shutil
import subprocess
import tkinter

root = Path(__file__).resolve().parents[1]
base = root / 'release/kwt_hold_pilot_fixture'
base.mkdir(exist_ok=True)
for name in ('kwt_sram_pins.vh', 'std.db', 'RAMTP1024X16_tt_1p10v_1p10v_25c.db', 'baseline.ddc'):
    (base / name).write_text('fixture\n', newline='\n')
script = root / 'syn/dc_compact.tcl'

def run_tcl(mode, phase=False):
    t = tkinter.Tcl()
    state = {'repaired': False, 'pilot': False}
    outputs, exits, compiles = [], [], []
    def seq(v): return list(v) if isinstance(v, tuple) else list(t.splitlist(v))
    def attr(obj, field):
        if field == 'period': return '6.667'
        if field == 'area': return '17757.843725'
        if field == 'ref_name': return 'RAMTP1024X16'
        if field == 'slack':
            if obj == 'maxpath':
                if state['repaired']: return '-0.001' if mode == 'bad_setup' else '0.030'
                return '0.040' if mode == 'setup_drift' and state['pilot'] else '0.0487933'
            if state['repaired']: return '-0.001' if mode == 'bad_hold' else '0.012'
            return '-0.1484576' if state['pilot'] else '-1.04846'
        raise AssertionError((obj, field))
    def report(*a):
        assert '>' in a, a
        Path(a[-1]).write_text('Total cell area: ' + ('3000000' if mode == 'bad_area' else '970000') + '\n')
        return ''
    def sdc(*a):
        io = 0.6 if state['repaired'] and mode == 'budget_drift' else 0.5
        Path(a[-1]).write_text('create_clock -period 6.667 [get_ports clk]\n'
            'set_clock_uncertainty -setup 1.0 [get_clocks clk]\n'
            f'set_clock_uncertainty -hold {0.1 if state["pilot"] else 1.0} [get_clocks clk]\n'
            f'set_input_delay -clock clk {io} [get_ports input]\n', newline='\n')
        return ''
    def write(*a):
        assert '-output' in a
        target = Path(a[-1])
        assert target.parent.name == mode and target.name != 'baseline.ddc'
        target.write_text('fixture output\n')
        return ''
    def budget(*a):
        assert a == ('-hold', '0.10', 'clk')
        state['pilot'] = True
        return ''
    def compile_cmd(*a):
        assert a == ('-incremental_mapping', '-only_hold_time'), a
        compiles.append(a)
        state['repaired'] = True
        return ''
    def exit_cmd(code):
        exits.append(int(code))
        if int(code): raise tkinter.TclError('exit')
        return ''
    callbacks = {
        'set_app_var': lambda *a: '', 'define_design_lib': lambda *a: '',
        'read_ddc': lambda *a: '', 'current_design': lambda *a: '', 'link': lambda: 1,
        'get_lib_cells': lambda *a: ('lib/cell',), 'get_lib_pins': lambda *a: ('lib/pin',),
        'sizeof_collection': lambda a: len(seq(a)), 'get_attribute': attr,
        'get_cells': lambda *a: tuple(f'macro{i}' for i in range(40)),
        'get_pins': lambda *a: tuple(f'macro{i}/clk' for i in range(80)) if phase and 'CLKA' in a[-1] else ('macro/output',),
        'get_ports': lambda *a: ('clk',), 'set_dont_touch': lambda *a: '',
        'get_clocks': lambda *a: ('clk',),
        'get_timing_paths': lambda *a: ('minpath',) if '-delay_type' in a and a[a.index('-delay_type')+1] == 'min' else ('maxpath',),
        'get_object_name': lambda a: a, 'write_sdc': sdc, 'write': write,
        'set_clock_uncertainty': budget, 'set_fix_hold': lambda *a: '', 'compile': compile_cmd,
        'puts': lambda *a: outputs.append(' '.join(a)) or '', 'exit': exit_cmd,
    }
    for cmd in ('report_area', 'report_timing', 'report_reference', 'report_qor', 'check_timing',
                'report_power', 'report_clock_gating', 'report_constraint', 'check_design'):
        callbacks[cmd] = report
    callbacks['write_sdf'] = lambda *a: Path(a[-1]).write_text('sdf\n') and ''
    for cmd, fn in callbacks.items(): t.createcommand(cmd, fn)
    t.eval('set search_path {}; proc foreach_in_collection {v xs body} {upvar 1 $v x; foreach x $xs {uplevel 1 $body}}')
    env = {'KWT_DC_CHECKPOINT': base / 'baseline.ddc', 'KWT_STDCELL_DB': base / 'std.db',
           'KWT_SRAM_DB_DIR': base, 'KWT_SRAM_CONFIG_DIR': base, 'KWT_DC_REPORT_DIR': base / mode,
           'KWT_DC_FIX_HOLD': '1'}
    for key, value in env.items(): t.setvar(f'env({key})', value.as_posix() if isinstance(value, Path) else value)
    t.eval('unset -nocomplain env(KWT_DC_EXPECT_SPLIT_PHASE)')
    if phase: t.setvar('env(KWT_DC_EXPECT_SPLIT_PHASE)', '1')
    t.eval('unset -nocomplain env(KWT_DC_PILOT_HOLD_NS)')
    if mode != 'original': t.setvar('env(KWT_DC_PILOT_HOLD_NS)', '0.10')
    try: t.eval(script.read_text())
    except tkinter.TclError:
        if exits != [1]: raise
    success = mode in ('good', 'bad_setup', 'bad_hold', 'bad_area', 'original')
    assert exits == [0 if success else 1], (mode, outputs)
    if success:
        assert len(compiles) == 1
        if phase:
            assert sum(line.startswith('PHASE_') and '_WNS:' in line for line in outputs) == 4, outputs
        if mode == 'original':
            assert 'HOLD_REPAIR_STATUS: PASS' in outputs, outputs
            assert not any(s.startswith('PILOT_HOLD_REPAIR_STATUS:') for s in outputs)
            assert not state['pilot']
        else:
            expected = 'PASS' if mode == 'good' else 'FAIL'
            assert f'PILOT_HOLD_REPAIR_STATUS: {expected}' in outputs
            assert not any(s.startswith('HOLD_REPAIR_STATUS:') for s in outputs)
            assert any(s.startswith('ORIGINAL_HOLD_STATUS: FAIL') for s in outputs)
            assert any(s.startswith('ORIGINAL_BUDGET_CLOSURE: NOT_ESTABLISHED') for s in outputs)
    else:
        assert 'KWT_DC_COMPLETE' not in outputs

for mode in ('good', 'bad_setup', 'bad_hold', 'bad_area', 'budget_drift', 'setup_drift', 'original'):
    run_tcl(mode)
run_tcl('good', phase=True)
print('PASS: pilot/original status separation, real optimization invocation, setup/hold/area failure, budget invariance')

# Reuse the already-tested runner fixture after its audit cases complete.
subprocess.run(['python', str(root / 'release/test_kwt_hold_audit.py')], check=True)
fixture = root / 'release/kwt_hold_audit_fixture'
package, run, binaries = fixture / 'package', fixture / 'run', fixture / 'bin'
shutil.copyfile(script, package / 'syn/dc_compact.tcl')
(binaries / 'dc_shell').write_text('''#!/usr/bin/env bash
set -eu
[[ ${KWT_DC_FIX_HOLD:-} == 1 && ${KWT_DC_PILOT_HOLD_NS:-} == 0.10 && -s ${KWT_DC_CHECKPOINT:-} ]] || exit 3
[[ $2 == */dc_compact.tcl ]] || exit 4
echo 'ORIGINAL_HOLD_STATUS: FAIL'
case ${MOCK_PILOT:-good} in
  good) echo 'PILOT_HOLD_REPAIR_STATUS: PASS';;
  bad) echo 'PILOT_HOLD_REPAIR_STATUS: FAIL';;
  fake) echo 'HOLD_REPAIR_STATUS: PASS';;
  timeout) exit 124;;
esac
echo KWT_DC_COMPLETE
''', newline='\n')
bash = 'C:/Program Files/Git/bin/bash.exe'
bin_path = '/' + binaries.drive[0].lower() + binaries.as_posix()[2:]
prefix = f'export PATH="{bin_path}:$PATH"; bash "{(package / "tools/rerun_kwt_sram_synthesis.sh").as_posix()}" --run-dir "{run.as_posix()}"'
for mode in ('good', 'bad', 'fake', 'timeout'):
    result = subprocess.run([bash, '-c', prefix + ' --pilot-hold 0.10'], cwd=run,
        env=dict(os.environ, MOCK_PILOT=mode), capture_output=True, text=True)
    assert (result.returncode == 0) == (mode == 'good'), (mode, result.stdout, result.stderr)
    if mode == 'timeout': assert result.returncode == 124 and 'PILOT_RESULT: TIMEOUT' in result.stdout
for arg in ('--pilot-hold ""', '--pilot-hold -0.1', '--pilot-hold NaN', '--pilot-hold 1.0', '--audit-hold --pilot-hold 0.10'):
    result = subprocess.run([bash, '-c', prefix + ' ' + arg], cwd=run, capture_output=True, text=True)
    assert result.returncode == 2, (arg, result.stdout, result.stderr)
print('PASS: runner explicit pilot budget, invalid/mixed options, status/failure/timeout propagation')
