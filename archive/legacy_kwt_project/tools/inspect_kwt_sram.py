#!/usr/bin/env python
"""Read-only foundry SRAM inventory. Runs with Python 2.7 or Python 3.

Print declarations, not inferred wiring. No library extraction or EDA commands.
"""
from __future__ import print_function
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys


def read_text(path):
    opener = gzip.open if path.lower().endswith('.gz') else open
    with opener(path, 'rb') as stream:
        return stream.read().decode('utf-8', 'replace')


def no_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def shape(name):
    # Accept naming in both depth x width and width x depth order.
    match = re.search(r'(?<!\d)(128|1024|4096)[xX_]+16(?!\d)', name)
    if match:
        return int(match.group(1))
    match = re.search(r'(?<!\d)16[xX_]+(128|1024|4096)(?!\d)', name)
    return int(match.group(1)) if match else None


def modules(path):
    text = no_comments(read_text(path))
    found = []
    for match in re.finditer(r'\bmodule\s+(\w+)\b(.*?)\bendmodule\b', text, re.S):
        name, body = match.groups()
        if not shape(name):
            continue
        # Preserve header/parameters, including preprocessor alternatives.
        header = body.split(';', 1)[0].strip()
        # Non-ANSI declarations are outside the module header. ANSI pins are
        # already present there and must not be duplicated.
        tail = body.split(';', 1)[1] if ';' in body else ''
        declarations = re.findall(
            r'\b(?:input|output|inout|parameter|localparam)\b[^;]*;', tail, re.S)
        extra = re.findall(r'`include\s+"[^"]+"', body)
        found.append({'name': name, 'depth': shape(name),
                      'header': ' '.join(header.split()),
                      'declarations': [' '.join(x.split()) for x in declarations],
                      'includes': extra})
    return found


def inspect(roots):
    entries, errors = [], []
    for root in roots:
        if not os.path.isdir(root):
            errors.append('Root not found: ' + root)
            continue
        for directory, subdirs, filenames in os.walk(root):
            subdirs[:] = sorted(d for d in subdirs if d not in ('.git', 'run', 'work'))
            for name in sorted(filenames):
                lower = name.lower()
                path = os.path.join(directory, name)
                kind = None
                if lower.endswith(('.v', '.sv', '.v.gz', '.sv.gz')):
                    kind = 'verilog'
                elif lower.endswith(('.db', '.lib', '.lib.gz', '.lef', '.zip', '.tar.gz')) and (
                        shape(path) or lower.endswith(('.zip', '.tar.gz'))):
                    kind = 'library_or_archive'
                if kind is None:
                    continue
                try:
                    entry = {'path': path, 'kind': kind, 'bytes': os.path.getsize(path)}
                    if kind == 'verilog':
                        entry['modules'] = modules(path)
                        with open(path, 'rb') as stream:
                            entry['sha256'] = hashlib.sha256(stream.read()).hexdigest()
                    entries.append(entry)
                except (IOError, OSError, ValueError) as exc:
                    errors.append('%s: %s' % (path, exc))
    return entries, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', help='library root (repeatable)')
    parser.add_argument('--out', default='kwt_sram_inventory.json')
    parser.add_argument('--details', help='print complete matching module text (exact module name)')
    args = parser.parse_args()
    roots = args.root or ['/storage1/admin_public_dir/SRAM_Lib_2025']
    entries, errors = inspect([os.path.abspath(os.path.expanduser(x)) for x in roots])
    report = {'roots': roots, 'files': entries, 'errors': errors,
              'required_default': {'1024x16': 36, '4096x16': 1},
              'contract': 'one synchronous read plus independent simultaneous full-word write'}
    with io.open(args.out, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + u'\n')
    print('=== KWT SRAM INVENTORY (read-only) ===')
    print('REQUIRED: 36 x 1024x16 + 1 x 4096x16; simultaneous 1R+1W, synchronous read')
    print('ROOTS: ' + ', '.join(roots))
    print('FILES: %d; ERRORS: %d' % (len(entries), len(errors)))
    for error in errors:
        print('ERROR: ' + error)
    candidates = [(entry, module) for entry in entries
                  for module in entry.get('modules', [])]
    # Display the exact named dual-port macros first. Other candidates are
    # retained in JSON; never silently select a macro for synthesis.
    candidates.sort(key=lambda item: (
        0 if 'RAMTP' in item[1]['name'].upper() else 1,
        item[1]['depth'], item[0]['path']))
    seen = set()
    for entry, module in candidates:
        signature = (module['name'], module['header'], tuple(module['declarations']))
        if signature in seen:
            continue
        seen.add(signature)
        print('\nMODEL: ' + entry['path'])
        print('SHA256: ' + entry['sha256'])
        print('module ' + module['name'] + ' ' + module['header'] + ';')
        for declaration in module['declarations']:
            print('  ' + declaration)
        for include in module['includes']:
            print('  ' + include)
    if args.details:
        detail_seen = set()
        for entry, module in candidates:
            if module['name'] != args.details or entry['sha256'] in detail_seen:
                continue
            detail_seen.add(entry['sha256'])
            print('\n=== MODEL BODY: %s ===' % entry['path'])
            source = no_comments(read_text(entry['path']))
            for match in re.finditer(r'\bmodule\s+(\w+)\b(.*?)\bendmodule\b', source, re.S):
                if match.group(1) == args.details:
                    print('module ' + match.group(1) + match.group(2) + 'endmodule')
    print('\n=== LIBRARY / ARCHIVE PATHS ===')
    library_entries = [e for e in entries if e['kind'] == 'library_or_archive']
    # Avoid hundreds of duplicate PVT corners in terminal output.
    shown = 0
    for entry in library_entries:
        if shown >= 36:
            break
        print(entry['path'])
        shown += 1
    if len(library_entries) > shown:
        print('... %d further paths in JSON' % (len(library_entries) - shown))
    if not candidates:
        print('NO_MATCHING_MODEL: need Verilog model declarations before writing adapter')
    print('FULL_REPORT: ' + os.path.abspath(args.out))
    print('INFO: this inventory does not validate port polarity, collision semantics or timing')
    return 2 if errors or not candidates else 0


if __name__ == '__main__':
    sys.exit(main())
