"""Freeze a new basic P&R flow and a small VNC-transfer launcher."""
import ast
import base64
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def build_tcl():
    source = (HERE/'ContinuePr.tcl').read_text()
    switch = source.index('    switch $Action {')
    prefix = source[:switch]
    # clock_opt may expose top-level VDD/VSS ports during auto PG connection.
    # Keep the original geometry check for every signal port and reject all
    # other port additions or removals, with names in the native error log.
    physical = (HERE/'PgPhysical.tcl').read_text()
    start_guard = physical.index('proc PgCheckSourceIo {File} {')
    end_guard = physical.index('\n}', start_guard) + 2
    guard = physical[start_guard:end_guard]
    guard = guard.replace('proc PgCheckSourceIo {File} {', 'proc FastCheckSourceIo {File} {', 1)
    guard = guard.replace('    if {[sizeof_collection $Ports]!=[dict size $Expected]} {error "Recovered IO port count changed"}',
                          '    set Seen 0; set Extras {}')
    guard = guard.replace('        if {![dict exists $Expected $N]} {error "Unexpected recovered signal port: $N"}',
                          '        if {![dict exists $Expected $N]} {lappend Extras $N; continue}\n        incr Seen')
    guard = guard[:-2] + '''
    puts "FAST_IO_AUDIT: expected=[dict size $Expected] actual=[sizeof_collection $Ports] matched=$Seen extra=$Extras"
    if {$Seen != [dict size $Expected]} {error "Original IO ports missing: expected=[dict size $Expected] matched=$Seen extra=$Extras"}
    foreach N $Extras {
        if {$N ni {VDD VSS}} {error "Unexpected added port after CTS: $N; all extras=$Extras"}
    }
    if {[llength $Extras]>2} {error "Unexpected extra PG port count: $Extras"}
}\n'''
    if 'set Seen 0; set Extras {}' not in guard or 'incr Seen' not in guard:
        raise ValueError('Could not construct CTS IO audit')
    prefix = prefix.replace('source [file join [file dirname [info script]] PgPhysical.tcl]',
                            'source [file join [file dirname [info script]] PgPhysical.tcl]\n'+guard)
    prefix = prefix.replace('PgCheckSourceIo $BaselineIo', 'FastCheckSourceIo $BaselineIo')
    actions = {}
    matches = list(re.finditer(r'^        (\w+) \{\n', source[switch:], re.M))
    for index, match in enumerate(matches):
        start = switch+match.start()
        end = switch+matches[index+1].start() if index+1 < len(matches) else source.index('        default {error', start)
        actions[match.group(1)] = source[start:end]
    setup = actions['01_rc']
    commands = '''            CpSame [PgReadSignature $BaselineLeaves] [CpLeaves] INITIAL_LOGICAL_LEAVES
            PrStep macro_keepout [list create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros]
            set Option place.coarse.continue_on_missing_scandef
            PrStep no_scan_functional [list set_app_options -name $Option -value true]
            PrStep initial_legalize [list legalize_placement]
'''
    setup = setup.replace('            CpSave\n', commands+'            CpSave\n')
    pg = (HERE/'PgStage.tcl').read_text()
    start = pg.index('        pg_core {\n')+len('        pg_core {\n')
    end = pg.index('        default {error "Unknown PG phase', start)
    body = pg[start:end].rsplit('        }', 1)[0]
    # Reserve lower routing layers for signal wires. This is a sparse engineering PG.
    body = '\n'.join(line for line in body.splitlines()
                     if not any(token in line for token in ('horizontal_layer: M3', 'vertical_layer: M4', 'horizontal_layer: M5')))+'\n'
    body = body.replace('{pitch: 42}', '{pitch: 84}').replace('-pitch 42', '-pitch 84')
    body = body.replace('MESH707_42', 'MESH707_84_BASIC').replace('PgSave mesh42', 'PgSave mesh84')
    body = body.replace('{{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 84}',
                        '{{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 168}')
    old = '-via_rule {{{layers: M4} {layers: M5} {via_master: PIN707_1X1}}}'
    if body.count(old) != 1:
        raise ValueError('Expected original macro-via expression')
    body = body.replace(old, '-via_rule {{intersection: adjacent} {via_master: PIN707_1X1}}')
    pg_action = '        02_pg_basic {\n'+body+'        }\n'
    helpers = '''proc PgConnect {} {CpConnect}
proc PgSave {Tag} {
    CpSave
    PrStep pg_subcheckpoint_$Tag [list write_def "${Tag}.def"]
}
'''
    prefix = prefix.replace('if {[catch {\n    source ContinueConfig.tcl', helpers+'\nif {[catch {\n    source ContinueConfig.tcl')
    clocks = '''        04_build_clock {
            CpReport clock_opt_manual.txt [list man clock_opt]
            set F [open clock_opt_manual.txt r];set Manual [read $F];close $F
            foreach Token {build_clock route_clock -from -to} {
                if {[string first $Token $Manual]<0} {error "Installed clock_opt manual lacks $Token"}
            }
            PrStep build_clock [list clock_opt -from build_clock -to build_clock]
            CpConnect;CpSave;CpTiming
        }
        04_route_clock {
            PrStep route_clock [list clock_opt -from route_clock -to route_clock]
            PrStep propagate [list set_propagated_clock [all_clocks]]
            CpConnect;CpSave;CpTiming
            if {[llength [info commands report_clock_qor]]} {CpReport clock_qor.rpt [list report_clock_qor]}
        }
'''
    route = actions['05_route']
    route = route.replace('            PrStep route [list route_auto]', '''            CpReport route_auto_manual.txt [list man route_auto]
            set F [open route_auto_manual.txt r];set Manual [read $F];close $F
            if {[string first -max_detail_route_iterations $Manual]>=0} {
                PrStep signal_route [list route_auto -max_detail_route_iterations 3]
            } else {
                puts "ROUTING_EFFORT: installed route_auto has no iteration option; using default"
                PrStep signal_route [list route_auto]
            }''')
    route = route.replace('            CpReport route_check.rpt [list check_routes]\n', '')
    export = actions['07_export']
    export = export.replace('foreach Command {write_parasitics write_sdf write_gds}', 'foreach Command {write_gds}')
    export = '\n'.join(line for line in export.splitlines()
                       if 'CpReport spef_export.log' not in line and 'CpReport sdf_export.log' not in line)+'\n'
    suffix = source[source.index('        default {error "Unknown action'):]
    result = prefix+'    switch $Action {\n'+setup+pg_action+clocks+route+export+actions['connectivity']+actions['drc']+suffix
    return result.replace('PgCheckSourceIo $BaselineIo', 'FastCheckSourceIo $BaselineIo')


def main():
    tcl = build_tcl().replace('\r\n', '\n')
    (HERE/'FastEngineeringPr.tcl').write_text(tcl)
    files = {'tools/FastEngineeringPr.py': (HERE/'FastEngineeringPr.py').read_bytes().replace(b'\r\n', b'\n'),
             'tools/FastEngineeringPr.tcl': tcl.encode()}
    ast.parse(files['tools/FastEngineeringPr.py'].decode(), feature_version=(3, 6))
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        for name, contents in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(contents)
            info.mode = 0o644
            info.mtime = 1704067200
            archive.addfile(info, io.BytesIO(contents))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream:
        stream.write(data.getvalue())
    payload = compressed.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    shell = '''#!/usr/bin/env bash
set -euo pipefail
origin=/tmp/tpusoc_continue_pr_20261111_707cd7f_MDON2L
cd "$origin"
sha256sum --quiet -c PACKAGE.sha256
out=$(mktemp -d /tmp/tpusoc_basic_pr_707cd7f_XXXXXX)
cp -a tools "$out/"
printf 'WORK_DIR: %s\\n' "$out"
base64 -d > "$out/payload.tar.gz" <<'BASIC707'
'''+base64.encodebytes(payload).decode()+'''BASIC707
echo "'''+digest+'''  $out/payload.tar.gz" | sha256sum -c -
tar -xzf "$out/payload.tar.gz" -C "$out"
cd "$out"
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/FastEngineeringPr.py "$out" 2>&1 | tee runner.log
'''
    path = ROOT/'workspace/Server/tpusoc_basic_pr_20261111_707cd7f_v1.sh'
    path.write_bytes(shell.encode())
    print(str(path))
    print('BYTES', len(shell.encode()), 'SHA256', hashlib.sha256(shell.encode()).hexdigest())


if __name__ == '__main__':
    main()
