#!/usr/bin/env python
"""Read-only clock-to-clock Liberty/model excerpts; Python 2.7 / 3."""
from __future__ import print_function
import argparse
import glob
import hashlib
import io
import os
import re
import subprocess


def read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as stream:
        return stream.read()


def without_comments(text):
    # Preserve quoted text and line numbers.
    token = re.compile(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*')
    return token.sub(lambda m: m.group(0) if m.group(0).startswith('"') else
                     re.sub(r'[^\n]', ' ', m.group(0)), text)


def groups(text, keyword):
    """Yield direct/nested groups with balanced braces, respecting strings/comments."""
    clean = without_comments(text)
    pattern = re.compile(r'\b' + re.escape(keyword) + r'\s*\(\s*("(?:\\.|[^"\\])*"|[^)]*)\s*\)\s*\{')
    for match in pattern.finditer(clean):
        depth, quoted, escaped, pos = 1, False, False, match.end()
        start = pos
        while pos < len(clean) and depth:
            char = clean[pos]
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
            pos += 1
        if depth:
            raise ValueError('Unbalanced %s group' % keyword)
        yield match.group(1).strip().strip('"'), clean[start:pos-1]


def field(text, name):
    match = re.search(r'\b' + name + r'\s*:\s*("(?:\\.|[^"\\])*"|[^;]+)\s*;', text)
    return match.group(1).strip().strip('"') if match else '<absent>'


def clock_arcs(text):
    result = []
    for pin, body in groups(text, 'pin'):
        if pin not in ('CLKA', 'CLKB'):
            continue
        for _, timing in groups(body, 'timing'):
            related = field(timing, 'related_pin')
            if not any(p in related.split() for p in ('CLKA', 'CLKB')):
                continue
            tables = []
            for table in ('rise_constraint', 'fall_constraint'):
                for _, values in groups(timing, table):
                    data = re.search(r'\bvalues\s*\(([\s\S]*?)\)\s*;', values)
                    if data:
                        nums = [float(x) for x in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', data.group(1))]
                        if nums:
                            tables.append('%s min=%g max=%g' % (table, min(nums), max(nums)))
            result.append((pin, related, field(timing, 'timing_type'), field(timing, 'when'), tables))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/storage1/admin_public_dir/SRAM_Lib_2025')
    parser.add_argument('--run-dir', required=True)
    args = parser.parse_args()
    name = 'RAMTP1024X16'
    base = os.path.join(args.root, name)
    lib = os.path.join(base, 'lib', name + '_tt_1p10v_1p10v_25c.lib')
    model = os.path.join(args.run_dir, 'models', name, name + '.v')
    print('=== SRAM CLOCK ARC EVIDENCE (read-only; no timing exceptions applied) ===')
    for path in (lib, model):
        if not os.path.isfile(path):
            parser.error('Required verified source missing: ' + path)
        with open(path, 'rb') as stream:
            print('SOURCE: %s; SHA256: %s' % (path, hashlib.sha256(stream.read()).hexdigest()))
    text = read(lib)
    print('LIB_TIME_UNIT: ' + field(text, 'time_unit'))
    arcs = clock_arcs(text)
    if not arcs:
        parser.error('No CLKA/CLKB timing groups parsed; inspect source manually')
    for pin, related, kind, when, tables in arcs:
        print('CLOCK_ARC: %s -> %s; type=%s; when=%s; %s' %
              (related, pin, kind, when, '; '.join(tables) or 'no constraint table'))
    # Print complete cross-clock specify statements, never infer legality from absence.
    statements = re.findall(r'\$(?:setuphold|hold|setup|skew|fullskew|timeskew|nochange)\b[^;]*;', without_comments(read(model)), re.I)
    cross = [s for s in statements if re.search('CLKA', s, re.I) and re.search('CLKB', s, re.I)]
    for statement in cross[:8]:
        print('RAW_MODEL_CLOCK_CHECK (preprocessor not evaluated): ' + ' '.join(statement.split()))
    if not cross:
        print('MODEL_CLOCK_CHECK: no literal cross-clock statement found; not proof of legality')
    docs = sorted(glob.glob(os.path.join(base, '*', '*.pdf')) + glob.glob(os.path.join(base, '*.pdf')))
    if not docs:
        print('MACRO_PDF: none found at macro root / one directory level')
    pattern = re.compile(r'CLKA.{0,60}CLKB|(?:same|common|simultaneous|synchronous).{0,60}clock|clock.{0,50}(?:collision|contention|separation)|\btcc\b', re.I)
    for path in docs[:3]:
        print('MACRO_PDF: ' + path)
        try:
            pdf = subprocess.check_output(['pdftotext', '-layout', path, '-']).decode('utf-8', 'replace')
        except (OSError, subprocess.CalledProcessError):
            print('MACRO_PDF_TEXT: unavailable; no conclusion about synchronous-clock legality')
            continue
        lines = pdf.splitlines()
        matches = [i for i, line in enumerate(lines) if pattern.search(line)]
        for i in matches[:6]:
            print('MACRO_DOC_LINE_%d: %s' % (i+1, ' '.join(x.strip() for x in lines[max(0, i-1):i+3])))
    print('LIBRARY_STATUS: unchanged; collision checks and all timing arcs retained')


if __name__ == '__main__':
    main()
