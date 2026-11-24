#!/usr/bin/env python
"""Read-only RAMSP evidence, Python 2.7/3. Never infer or generate a binding."""
from __future__ import print_function
import argparse
import hashlib
import io
import json
import os
import re
import sys

from inspect_kwt_sram import modules, read_text
from inspect_kwt_sram_clock_arcs import groups, field, without_comments


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def audit(root, out):
    name = 'RAMSP1024X16'
    base = os.path.join(root, name)
    if not os.path.isdir(base):
        raise ValueError('Missing macro directory: ' + base)
    paths = sorted(os.path.join(folder, f) for folder, _, names in os.walk(base) for f in names)
    write(os.path.join(out, 'inventory.txt'), u'\n'.join(paths) + u'\n')
    model = os.path.join(base, 'verilog', name + '.v')
    liberty = os.path.join(base, 'lib', name + '_tt_1p10v_1p10v_25c.lib')
    for path in (model, liberty):
        if not os.path.isfile(path):
            raise ValueError('Expected input absent (no alternate source selected): ' + path)
    declarations = [m for m in modules(model) if m['name'] == name]
    if len(declarations) != 1:
        raise ValueError('Expected one raw module definition, got %d' % len(declarations))
    declaration = declarations[0]
    ports = [d for d in declaration['declarations'] if re.match(r'^(input|output|inout)\b', d)]
    raw = [u'module ' + name + u' ' + declaration['header'] + u';'] + ports
    write(os.path.join(out, 'ports_raw.txt'), u'\n'.join(raw) + u'\n')
    source = without_comments(read_text(model))
    checks = re.findall(r'\$(?:setuphold|setup|hold|width|period|recovery|removal)\b[^;]*;', source)
    write(os.path.join(out, 'timing_checks_raw.txt'),
          u'PREPROCESSOR NOT EVALUATED; raw evidence only.\n' + u'\n'.join(checks) + u'\n')
    control_lines = [u'%d: %s' % (n+1, line.strip()) for n, line in enumerate(source.splitlines())
                     if re.search(r'EMA|RET1N|Set Value|WEN|CEN|posedge|negedge', line)]
    write(os.path.join(out, 'controls_raw.txt'), u'\n'.join(control_lines) + u'\n')

    text = read_text(liberty)
    cells = [body for cell, body in groups(text, 'cell') if cell == name]
    if len(cells) != 1:
        raise ValueError('Expected one matching Liberty cell, got %d' % len(cells))
    pins, arcs = [], []
    for kind in ('pin', 'bus'):
        for pin, body in groups(cells[0], kind):
            pins.append(dict(kind=kind, name=pin, direction=field(body, 'direction'),
                             clock=field(body, 'clock'), function=field(body, 'function')))
            for _, timing in groups(body, 'timing'):
                arcs.append(dict(pin=pin, related_pin=field(timing, 'related_pin'),
                                 timing_type=field(timing, 'timing_type'), when=field(timing, 'when')))
    report = dict(macro=name, root=base, model=model, model_sha256=sha256(model),
                  liberty=liberty, liberty_sha256=sha256(liberty),
                  time_unit=field(text, 'time_unit'), area=field(cells[0], 'area'),
                  raw_declaration=declaration, pins=pins, timing_arcs=arcs, inventory=paths,
                  binding_status='PENDING_MANUAL_PORT_AND_DATASHEET_REVIEW',
                  timing_qualification='NOT_RUN')
    write(os.path.join(out, 'evidence.json'), json.dumps(report, indent=2, ensure_ascii=True) + u'\n')
    summary = [u'MACRO: ' + name, u'MODEL_SHA256: ' + report['model_sha256'],
               u'LIB_SHA256: ' + report['liberty_sha256'], u'LIB_TIME_UNIT: ' + report['time_unit'],
               u'LIB_AREA_RAW: ' + report['area'],
               u'RAW_PORTS: preprocessor not evaluated; optional power branches may be included']
    summary += raw
    summary += [u'LIB_CLOCK_PINS: ' + u', '.join(p['name'] for p in pins if p['clock'] == 'true'),
                u'BINDING_STATUS: PENDING_MANUAL_PORT_AND_DATASHEET_REVIEW',
                u'FOUNDRY_TIMING_STATUS: NOT_RUN',
                u'RESULT: AUDIT_COMPLETE_REVIEW_REQUIRED', u'REPORT_DIR: ' + out]
    write(os.path.join(out, 'summary.txt'), u'\n'.join(summary) + u'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/storage1/admin_public_dir/SRAM_Lib_2025')
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    out = os.path.abspath(os.path.expanduser(args.out_dir))
    if os.path.exists(out):
        parser.error('Output directory must be new')
    os.makedirs(out)
    try:
        summary = audit(os.path.abspath(os.path.expanduser(args.root)), out)
    except (IOError, OSError, ValueError) as exc:
        print('SP_AUDIT_ERROR: ' + str(exc))
        return 2
    for line in summary:
        print(line.encode('ascii', 'backslashreplace').decode('ascii'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
