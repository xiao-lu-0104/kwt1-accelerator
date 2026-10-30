#!/usr/bin/env python
"""Focused, read-only follow-up to the SRAM inventory (Python 2.7 / 3)."""
from __future__ import print_function
import argparse
import glob
import io
import os
import re
import subprocess


def read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as stream:
        return stream.read()


def samples(text, token, limit=2):
    lines = text.splitlines()
    found = []
    candidates = []
    # Omit port declarations, buffers and specify checks; keep surrounding
    # comments because they can document normal operation and access settings.
    for i, line in enumerate(lines):
        if not re.search(token, line, re.I):
            continue
        if re.search(r'^\s*(input|output|inout|module|parameter|buf\s*\(|\.)', line):
            continue
        if re.search(r'\$(setup|hold|width|period|recovery|removal)|\*>|\bifnone\b', line):
            continue
        if not line.strip() or line.lstrip().startswith('//'):
            continue
        score = 2 if re.search(r'\bif\b|\bcase\b|\?|==|!=|&&|\|\|', line) else 0
        candidates.append((-score, i))
    for _, i in sorted(candidates)[:limit]:
        start, end = max(0, i-1), min(len(lines), i+3)
        # Flatten only the display; full source and line numbers are retained
        # in the report. Do not interpret the logical polarity automatically.
        snippet = ' '.join(x.strip() for x in lines[start:end])
        found.append('%d: %s' % (i+1, snippet))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/storage1/admin_public_dir/SRAM_Lib_2025')
    parser.add_argument('--out', default=os.path.expanduser('~/soc/kwt_sram_controls_20261029.txt'))
    args = parser.parse_args()
    full = []
    print('=== SRAM CONTROL CHECK (read-only; no binding approved yet) ===')
    for name in ('RAMTP1024X16', 'RAMTP128X16'):
        base = os.path.join(args.root, name)
        print('\nMACRO: ' + name)
        for suffix in ('.v', '_rtl.v'):
            path = os.path.join(base, 'verilog', name+suffix)
            if not os.path.isfile(path):
                print('MISSING_MODEL: ' + path)
                continue
            text = read(path)
            full.append('\n=== %s ===\n%s' % (path, text))
            print('MODEL: ' + path)
            # Show power-related preprocessing exactly, before any task body.
            directives = [x.strip() for x in text.splitlines()
                          if re.search(r'^\s*`(?:ifdef|ifndef|define|include)', x)]
            print('DIRECTIVES: ' + ' | '.join(directives[:10]))
            for token in ('EMAA|EMAB', 'RET1N', 'COLLDISN', 'CENA', 'CENB', 'WENB', 'posedge'):
                matches = samples(text.split('specify', 1)[0], token)
                print('  [%s] %s' % (token, ' | '.join(matches) if matches else '<no executable match>'))
        tt = sorted(glob.glob(os.path.join(base, 'lib', '*_tt_*25c.lib')))
        print('TT_25C_LIBS: ' + str(len(tt)))
        for path in tt:
            text = read(path)
            full.append('\n=== LIBRARY %s ===\n%s' % (path, text))
            print('LIB: ' + path)
            fields = re.findall(
                r'\blibrary\s*\([^\n]+|\bcell\s*\([^\n]+|\barea\s*:[^;]+;|'
                r'\bnom_(?:voltage|temperature)\s*:[^;]+;', text)
            print('  ' + ' '.join(' '.join(x.split()) for x in fields[:7]))
        docs = []
        if os.path.isdir(base):
            for directory, _, filenames in os.walk(base):
                for filename in sorted(filenames):
                    if filename.lower().endswith(('.pdf', '.html', '.txt', '.doc')):
                        docs.append(os.path.join(directory, filename))
        for path in docs[:4]:
            print('DOC: ' + path)
        for path in [p for p in docs if p.lower().endswith('.pdf')][:1]:
            try:
                text = subprocess.check_output(['pdftotext', '-layout', path, '-']).decode('utf-8', 'replace')
            except (OSError, subprocess.CalledProcessError):
                print('PDF_TEXT: pdftotext unavailable; document not changed')
                break
            full.append('\n=== PDF TEXT %s ===\n%s' % (path, text))
            lines = text.splitlines()
            indexes = [i for i,x in enumerate(lines) if re.search('EMAA|EMAB|COLLDISN|RET1N', x)]
            for i in indexes[:5]:
                print('PDF: ' + ' '.join(x.strip() for x in lines[max(0,i-1):i+3]))
    with io.open(args.out, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(u'\n'.join(full))
    print('\nFULL_LOCAL_REPORT: ' + os.path.abspath(args.out))
    print('No source/library files modified. Library conversion not performed.')


if __name__ == '__main__':
    main()
