#!/usr/bin/env python
"""Read E203 platform source evidence without compiling or changing the platform.

Python 2.7/3, standard library only. Raw Verilog evidence is not elaboration.
"""
from __future__ import print_function

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import tempfile


FILES = [
    'rtl/e203/core/config.v',
    'rtl/e203/core/e203_defines.v',
    'rtl/e203/core/e203_core.v',
    'rtl/e203/core/e203_cpu_top.v',
    'rtl/e203/core/e203_exu_nice.v',
    'rtl/e203/core/e203_exu_lsu.v',
    'rtl/e203/core/e203_dtcm_ctrl.v',
    'rtl/e203/core/e203_itcm_ctrl.v',
    'rtl/e203/core/e203_dtcm_ram.v',
    'rtl/e203/core/e203_itcm_ram.v',
    'rtl/e203/subsys/e203_subsys_main.v',
    'rtl/e203/subsys/e203_subsys_top.v',
    'rtl/e203/subsys/e203_subsys_nice_core.v',
    'rtl/e203/soc/e203_soc_top.v',
    'tb/tb_top.v',
    'vsim/bin/run.makefile',
    'vsim/Makefile',
]
PATTERN = re.compile(
    r'ADDR_WIDTH|TCM_ADDR_BASE|HAS_(?:ITCM|DTCM|NICE|ECC)|'
    r'nice_(?:mem_holdup|icb_|req_)|ext2(?:i|d)tcm_icb_|'
    r'LSU take|LSU.*priority|ARBT_(?:SCHEME|ALLOW)|FIFO_OUTS_NUM|'
    r'VSRC_DIR|VTB_DIR|RTL_V_FILES|SIM_OPTIONS|SIM_TOOL|'
    r'FPGA_SOURCE|\bFPGA\b|install|readmem')


def read(path):
    with open(path, 'rb') as source:
        return source.read()


def decode(data):
    return data.decode('utf-8', 'replace')


def uncomment(text):
    # Preserve line numbers. Commented alternative widths must not become active.
    text = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'),
                  text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


def inside(path, root):
    path = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(root))
    return path == root or path.startswith(root + os.sep)


def audit(root, output=None):
    root = os.path.realpath(os.path.expanduser(root))
    if not os.path.isfile(os.path.join(root, FILES[0])):
        raise ValueError('Platform config.v not found under ' + root)
    if output:
        output = os.path.realpath(os.path.expanduser(output))
        if inside(output, root):
            raise ValueError('Report must be outside the platform directory')
        if os.path.lexists(output):
            raise ValueError('Report directory already exists: ' + output)
        os.makedirs(output)
    else:
        output = tempfile.mkdtemp(prefix='platform_read_', dir=os.path.dirname(root))
    records = []
    details = ['RAW SOURCE AUDIT; no preprocessing, compilation or simulation.']
    summary = ['PLATFORM: ' + root, 'REPORT: ' + output]
    data_by_name = {}
    for relative in FILES:
        path = os.path.join(root, relative)
        record = {'path': relative, 'exists': os.path.isfile(path)}
        if record['exists']:
            data = read(path)
            data_by_name[relative] = data
            record['sha256'] = hashlib.sha256(data).hexdigest()
            record['bytes'] = len(data)
            record['evidence'] = [
                {'line': number, 'text': line}
                for number, line in enumerate(decode(data).splitlines(), 1)
                if PATTERN.search(line)]
            details.append('\nFILE: ' + relative + ' SHA256=' + record['sha256'])
            details.extend('%d: %s' % (item['line'], item['text'])
                           for item in record['evidence'])
            if relative.startswith(('rtl/', 'tb/')):
                # vsim/Makefile copies rtl/e203 into install/rtl, flattening e203.
                suffix = relative[len('rtl/e203/'):] if relative.startswith('rtl/e203/') else relative[3:]
                prefix = 'rtl' if relative.startswith('rtl/') else 'tb'
                installed = os.path.join(root, 'vsim', 'install', prefix, suffix)
                record['installed_path'] = os.path.relpath(installed, root).replace(os.sep, '/')
                if os.path.isfile(installed):
                    other = read(installed)
                    record['installed_sha256'] = hashlib.sha256(other).hexdigest()
                    record['installed_evidence'] = [
                        {'line': number, 'text': line}
                        for number, line in enumerate(decode(other).splitlines(), 1)
                        if PATTERN.search(line)]
                    if data == other:
                        state = 'IDENTICAL'
                    elif data.replace(b'\r\n', b'\n') == other.replace(b'\r\n', b'\n'):
                        state = 'LINE_ENDINGS_ONLY'
                    else:
                        state = 'CONTENT_DIFFERS'
                    record['installed_state'] = state
                else:
                    record['installed_state'] = 'MISSING'
                details.append('INSTALL_COPY: ' + record['installed_state'])
                if record['installed_state'] == 'CONTENT_DIFFERS':
                    details.extend('INSTALL %d: %s' % (item['line'], item['text'])
                                   for item in record['installed_evidence'])
        else:
            details.append('\nMISSING: ' + relative)
        records.append(record)

    config = uncomment(decode(data_by_name[FILES[0]]))
    for kind in ('ITCM', 'DTCM'):
        name = 'E203_CFG_' + kind + '_ADDR_WIDTH'
        values = re.findall(r'^\s*`define\s+' + name + r'\s+(\d+)\b', config, re.M)
        if len(values) == 1 and 1 <= int(values[0]) <= 32:
            summary.append('%s: RAW_WIDTH=%s CAPACITY=%d_KiB' %
                           (kind, values[0], (1 << int(values[0])) // 1024))
        else:
            summary.append(kind + ': WIDTH_REQUIRES_REVIEW ' + repr(values))
    installed_config = os.path.join(root, 'vsim/install/rtl/core/config.v')
    if os.path.isfile(installed_config):
        installed_text = uncomment(decode(read(installed_config)))
        for kind in ('ITCM', 'DTCM'):
            values = re.findall(r'^\s*`define\s+E203_CFG_' + kind +
                                r'_ADDR_WIDTH\s+(\d+)\b', installed_text, re.M)
            summary.append('INSTALL_' + kind + '_RAW_WIDTH: ' + ','.join(values))
    else:
        summary.append('INSTALL_CONFIG: MISSING (build source selection requires review)')
    summary.append('NOTE: raw declarations/bindings below require guard and build review.')
    # Keep terminal output short enough to return as a few screenshots.
    excerpts = [
        ('rtl/e203/core/config.v', r'^\s*`define.*(?:TCM_ADDR_BASE|HAS_NICE|HAS_ECC)', 4),
        ('rtl/e203/subsys/e203_subsys_nice_core.v',
         r'nice_(?:mem_holdup|icb_cmd_valid|icb_rsp_valid)', 5),
        ('rtl/e203/core/e203_core.v',
         r'\.nice_(?:mem_holdup|icb_cmd_valid|icb_rsp_valid)', 4),
        ('rtl/e203/core/e203_dtcm_ctrl.v',
         r'LSU take|ARBT_SCHEME|FIFO_OUTS_NUM|ext2dtcm_icb_cmd_valid,', 4),
        ('rtl/e203/soc/e203_soc_top.v',
         r'\.ext2(?:i|d)tcm_icb_cmd_(?:valid|addr)', 4),
        ('vsim/bin/run.makefile', r'^\s*(?:VSRC_DIR|VTB_DIR|SIM_TOOL)\s*[:?+]?=', 3),
    ]
    for relative, expression, limit in excerpts:
        hits = [(number, line.strip())
                for number, line in enumerate(decode(data_by_name.get(relative, b'')).splitlines(), 1)
                if re.search(expression, line)]
        summary.append('EVIDENCE ' + relative + ':')
        summary.extend('  %d: %s' % item for item in hits[:limit])
        if not hits:
            summary.append('  NO_MATCH (review report / platform variant)')
    differences = [r for r in records if r.get('installed_state') == 'CONTENT_DIFFERS']
    missing = [r for r in records if r.get('installed_state') == 'MISSING']
    summary.append('SOURCE_INSTALL: CONTENT_DIFFERS=%d MISSING=%d (selected files only)' %
                   (len(differences), len(missing)))
    summary.extend('  DIFF ' + r['path'] for r in differences)
    summary.append('STATUS: EVIDENCE_COLLECTED; ELABORATION/SIMULATION_NOT_RUN')
    evidence = {'platform': root, 'utc': datetime.datetime.utcnow().isoformat() + 'Z',
                'scope': 'Selected source files; raw evidence, not active HDL configuration',
                'files': records, 'summary': summary}
    with io.open(os.path.join(output, 'evidence.json'), 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(evidence, indent=2, ensure_ascii=True) + u'\n')
    with io.open(os.path.join(output, 'report.txt'), 'w', encoding='utf-8') as stream:
        stream.write(u'\n'.join(summary + details) + u'\n')
    return summary, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='~/soc/e203_hbirdv2-master')
    parser.add_argument('--out', help='New report directory outside platform; default: unique sibling')
    args = parser.parse_args()
    try:
        summary, unused = audit(args.root, args.out)
        for line in summary:
            # Terminal summaries are ASCII even on an older server locale.
            print(line.encode('ascii', 'backslashreplace').decode('ascii'))
    except (IOError, OSError, ValueError) as error:
        print('PLATFORM_READ_ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
