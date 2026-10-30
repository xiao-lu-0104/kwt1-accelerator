#!/usr/bin/env python
"""Read-only comparison with the GitHub reference files shipped beside this script.
Python 2.7/3; writes a new detailed report, never edits platform sources.
"""
from __future__ import print_function
import argparse
import difflib
import io
import os

FILES = [
    'rtl/e203/core/config.v',
    'rtl/e203/core/e203_clkgate.v',
    'rtl/e203/core/e203_dtcm_ram.v',
    'rtl/e203/core/e203_exu_decode.v',
    'rtl/e203/core/e203_itcm_ram.v',
    'rtl/e203/mems/sirv_mrom_top.v',
    'tb/tb_top.v',
    'vsim/README.md',
    'vsim/bin/run.makefile',
]


def read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace', newline=None) as stream:
        return stream.read().splitlines()


def compare(old, new, old_label, new_label):
    if not os.path.isfile(old) or not os.path.isfile(new):
        return ['MISSING: ' + (old if not os.path.isfile(old) else new)]
    return list(difflib.unified_diff(read(old), read(new),
                                   fromfile=old_label, tofile=new_label, n=3, lineterm=''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--reference', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reference'))
    parser.add_argument('--out', default='e203_diff_details.txt')
    parser.add_argument('--max-lines', type=int, default=35)
    parser.add_argument('--file', choices=FILES, help='Display only this file; full report still includes all comparisons.')
    args = parser.parse_args()
    if args.max_lines < 1:
        parser.error('--max-lines must be positive')
    sections = []
    for path in FILES:
        sections.append((path, compare(os.path.join(args.reference, *path.split('/')),
                                      os.path.join(args.root, *path.split('/')),
                                      'github/' + path, 'competition/' + path)))
    sections.append(('INSTALL: tb/tb_top.v', compare(os.path.join(args.root, 'tb', 'tb_top.v'),
                    os.path.join(args.root, 'vsim', 'install', 'tb', 'tb_top.v'),
                    'competition/tb/tb_top.v', 'competition/vsim/install/tb/tb_top.v')))
    # Do not overwrite any existing report or accidentally truncate a source.
    out = os.path.abspath(args.out)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with io.open(fd, 'w', encoding='utf-8', newline='\n') as stream:
        for label, lines in sections:
            stream.write(u'\n===== ' + label + u' =====\n')
            stream.write(u'\n'.join(lines or [u'IDENTICAL_AFTER_NEWLINE_NORMALIZATION']) + u'\n')
    for label, lines in sections:
        print('\n===== %s (%d diff lines) =====' % (label, len(lines)))
        if args.file and label != args.file:
            continue
        for line in (lines or ['IDENTICAL_AFTER_NEWLINE_NORMALIZATION'])[:args.max_lines]:
            print(line)
        if len(lines) > args.max_lines:
            print('... remaining lines saved in full report')
    print('\nFULL_REPORT: ' + out)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (IOError, OSError) as error:
        print('ERROR: %s' % error)
        raise SystemExit(2)
