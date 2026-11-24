from pathlib import Path
import os, subprocess, runpy
root=Path(__file__).resolve().parents[1]
runpy.run_path(str(root/'release/test_kwt_hold_pilot.py'))
base=root/'release/kwt_hold_audit_fixture'
package,run,binaries=base/'package',base/'run',base/'bin'
(run/'logs').mkdir(exist_ok=True)
results=(run/'results.tsv').read_text()
phase_results=results+'tb_kwt_sram_phase\tPASS\n'
(run/'results.tsv').write_text(phase_results)
(run/'runner.log').write_text('FUNCTIONAL_RESULT: PASS (full; fresh split-phase RTL; actual foundry Verilog, not timing signoff)\n')
phase_log='KWT_DC_COMPLETE\n'+''.join('PHASE_'+name+'_WNS: 1.0 ns\n' for name in ('CLOCK_max','CLOCK_min','WRITE_max','WRITE_min'))
(run/'logs/dc.log').write_text(phase_log)
checkpoint=run/'dc_out_bound/kwt_encoder_12_compiled.ddc'
checkpoint_original=checkpoint.read_bytes()
(binaries/'dc_shell').write_text('''#!/usr/bin/env bash
set -eu
[[ ${KWT_DC_EXPECT_SPLIT_PHASE:-} == 1 && ${KWT_DC_FIX_HOLD:-} == 1 && ${KWT_DC_PILOT_HOLD_NS:-} == 0.10 ]] || exit 3
[[ "$KWT_DC_CHECKPOINT" == */dc_out_bound/kwt_encoder_12_compiled.ddc ]] || exit 4
echo 'ORIGINAL_HOLD_STATUS: FAIL (original checkpoint, original constraints)'
if [[ "$MOCK_PHASE" == timeout ]]; then exit 124; fi
if [[ "$MOCK_PHASE" == mutate ]]; then echo changed >> "$KWT_DC_CHECKPOINT"; fi
for name in CLOCK_max CLOCK_min WRITE_max WRITE_min; do
    if [[ "$MOCK_PHASE" == missing && "$name" == WRITE_min ]]; then continue; fi
    value=1.0
    if [[ "$MOCK_PHASE" == negative && "$name" == CLOCK_min ]]; then value=-0.1; fi
    if [[ "$MOCK_PHASE" == malformed && "$name" == CLOCK_min ]]; then value=NaN; fi
    echo "PHASE_${name}_WNS: $value ns"
done
echo 'PILOT_HOLD_REPAIR_STATUS: PASS'
echo KWT_DC_COMPLETE
''',newline='\n')
bash='C:/Program Files/Git/bin/bash.exe'
binpath='/'+binaries.drive[0].lower()+binaries.as_posix()[2:]
command=f'export PATH="{binpath}:$PATH"; bash "{(package/"tools/rerun_kwt_sram_synthesis.sh").as_posix()}" --run-dir "{run.as_posix()}" --phase-pilot 0.10'
for mode in ('good','negative','missing','malformed','timeout','mutate'):
    result=subprocess.run([bash,'-c',command],cwd=run,env=dict(os.environ,MOCK_PHASE=mode),capture_output=True,text=True)
    (base/('phase_'+mode+'.log')).write_text(result.stdout+result.stderr)
    assert (result.returncode==0)==(mode=='good'),(mode,result.stdout,result.stderr)
    if mode=='timeout': assert result.returncode==124 and 'PILOT_RESULT: TIMEOUT' in result.stdout
    checkpoint.write_bytes(checkpoint_original)
    print('PASS: phase pilot '+mode)
for mode in ('no_phase_test','no_full_pass','incomplete_dc','bad_baseline_clock','malformed_baseline_clock','no_checkpoint','changed_input'):
    (run/'results.tsv').write_text(results if mode=='no_phase_test' else phase_results)
    (run/'runner.log').write_text('no full pass\n' if mode=='no_full_pass' else 'FUNCTIONAL_RESULT: PASS (full; fresh split-phase RTL; actual foundry Verilog, not timing signoff)\n')
    log=phase_log
    if mode=='incomplete_dc': log=log.replace('KWT_DC_COMPLETE','incomplete')
    if mode=='bad_baseline_clock': log=log.replace('CLOCK_min_WNS: 1.0','CLOCK_min_WNS: -0.1')
    if mode=='malformed_baseline_clock': log=log.replace('CLOCK_min_WNS: 1.0','CLOCK_min_WNS: NaN')
    (run/'logs/dc.log').write_text(log)
    if mode=='no_checkpoint': checkpoint.rename(checkpoint.with_suffix('.saved'))
    original_input=(run/'input.txt').read_bytes()
    if mode=='changed_input': (run/'input.txt').write_text('changed')
    result=subprocess.run([bash,'-c',command],cwd=run,env=dict(os.environ,MOCK_PHASE='good'),capture_output=True,text=True)
    assert result.returncode==2,(mode,result.stdout,result.stderr)
    if mode=='no_checkpoint': checkpoint.with_suffix('.saved').rename(checkpoint)
    (run/'input.txt').write_bytes(original_input)
    print('PASS: phase pilot rejects '+mode)
