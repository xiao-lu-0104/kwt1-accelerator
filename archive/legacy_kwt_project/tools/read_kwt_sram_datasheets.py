#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read competition RAMTP datasheets in place; save private text and excerpts.

Python 2.7 / 3, standard library only. No DC, library conversion or source edits.
"""
from __future__ import print_function
import argparse
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile

try:
    from html import unescape
except ImportError:
    from HTMLParser import HTMLParser
    unescape = HTMLParser().unescape

LIMIT = 16 * 1024 * 1024
try:
    text_type = unicode
except NameError:
    text_type = str


def as_text(value):
    return value if isinstance(value, text_type) else value.decode('utf-8', 'replace')


def text_decode(data):
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8-sig')
    except UnicodeError:
        return data.decode('gb18030', 'replace')


def html_text(text):
    text = re.sub(r'<(script|style)\b[^>]*>[\s\S]*?</\1\s*>', '', text, flags=re.I)
    text = re.sub(r'<(?:br|/p|/div|/tr|/td|/th|/li|/h[1-6])\b[^>]*>', '\n', text, flags=re.I)
    return unescape(re.sub(r'<[^>]*>', ' ', text))


def pdf_text(data, out_dir, key):
    # Tools operate on an isolated private copy; the shared datasheet is read-only.
    copy = os.path.join(out_dir, key + '.pdf')
    with open(copy, 'wb') as stream:
        stream.write(data)
    errors = []
    for command in (['pdftotext', '-layout', copy, '-'], ['mutool', 'draw', '-F', 'txt', copy]):
        try:
            with open(os.devnull, 'wb') as null:
                output = subprocess.check_output(command, stderr=null)
            if output.strip():
                return text_decode(output), 'PDF via ' + command[0]
            errors.append(command[0] + ': empty text')
        except (OSError, subprocess.CalledProcessError):
            errors.append(command[0] + ': unavailable/failed')
    return None, '; '.join(errors)


def postscript_text(data, out_dir, key):
    source = os.path.join(out_dir, key + '.ps')
    target = os.path.join(out_dir, key + '_ps_text.txt')
    pdf_target = os.path.join(out_dir, key + '_ps_converted.pdf')
    with open(source, 'wb') as stream:
        stream.write(data)
    errors = []
    interpreters = []
    if os.environ.get('KWT_GHOSTSCRIPT'):
        interpreters.append(os.environ['KWT_GHOSTSCRIPT'])
    interpreters.extend(['gs', 'gswin64c', 'gswin32c'])
    commands = [(name, [name, '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
                       '-sDEVICE=txtwrite', '-sOutputFile=' + target, '-f', source])
                for name in interpreters]
    commands.append(('ps2ascii', ['ps2ascii', source, target]))
    for index, (name, command) in enumerate(commands):
        log = os.path.join(out_dir, key + '_ps_%d.log' % index)
        try:
            # Never accept stale/partial output from an earlier failed converter.
            with open(target, 'wb'):
                pass
            with open(log, 'wb') as stream:
                subprocess.check_call(command, stdout=stream, stderr=subprocess.STDOUT)
            with open(target, 'rb') as stream:
                output = stream.read(LIMIT+1)
            if output.strip() and len(output) <= LIMIT:
                return text_decode(output), 'PostScript via ' + os.path.basename(name)
            errors.append(os.path.basename(name) + ': empty/oversized text')
        except (OSError, subprocess.CalledProcessError):
            errors.append(os.path.basename(name) + ': unavailable/failed; log=' + log)
    # Older Ghostscript installations can support pdfwrite but not txtwrite.
    try:
        log = os.path.join(out_dir, key + '_ps2pdf.log')
        with open(pdf_target, 'wb'):
            pass
        with open(log, 'wb') as stream:
            subprocess.check_call(['ps2pdf', '-dSAFER', source, pdf_target], stdout=stream, stderr=subprocess.STDOUT)
        with open(pdf_target, 'rb') as stream:
            converted = stream.read(LIMIT+1)
        if converted.lstrip().startswith(b'%PDF-') and len(converted) <= LIMIT:
            text, method = pdf_text(converted, out_dir, key + '_pdf')
            if text is not None:
                return text, 'PostScript via ps2pdf; ' + method
        errors.append('ps2pdf: no extractable PDF text')
    except (OSError, subprocess.CalledProcessError):
        errors.append('ps2pdf: unavailable/failed; log=' + log)
    return None, '; '.join(errors)


def extract(data, label, out_dir, depth=0):
    """Return text units and extraction failures; do not extract archive paths."""
    if depth > 3:
        return [], [(label, 'archive nesting limit')]
    if len(data) > LIMIT:
        return [], [(label, 'size exceeds 16 MiB limit')]
    key = hashlib.sha256(label.encode('utf-8')).hexdigest()[:16]
    if data.startswith(b'\x1f\x8b'):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                unpacked = stream.read(LIMIT+1)
            return extract(unpacked, label + '::gzip', out_dir, depth+1)
        except (IOError, EOFError, ValueError) as exc:
            return [], [(label, 'gzip error: ' + str(exc))]
    if data.startswith(b'PK\x03\x04'):
        units, failed = [], []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.infolist():
                    if item.filename.endswith('/'):
                        continue
                    if item.file_size > LIMIT:
                        failed.append((label + '::' + item.filename, 'size limit'))
                        continue
                    part, errors = extract(archive.read(item), label + '::' + as_text(item.filename), out_dir, depth+1)
                    units.extend(part)
                    failed.extend(errors)
        except (IOError, ValueError, zipfile.BadZipfile) as exc:
            failed.append((label, 'zip error: ' + str(exc)))
        return units, failed
    if data.lstrip().startswith(b'%PDF-'):
        text, method = pdf_text(data, out_dir, key)
        return ([(label, method, text)] if text is not None else []), ([] if text is not None else [(label, method)])
    if data.startswith(b'\xd0\xcf\x11\xe0'):
        return [], [(label, 'legacy Office binary; needs a document converter')]
    if data.lstrip().startswith(b'%!PS'):
        text, method = postscript_text(data, out_dir, key)
        return ([(label, method, text)] if text is not None else []), ([] if text is not None else [(label, method)])
    if data.lstrip().startswith(b'{\\rtf'):
        return [], [(label, 'RTF document; needs a document converter; not treated as plain text')]
    if b'\x00' in data[:4096] and not data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return [], [(label, 'unrecognized binary format; not interpreted as text')]
    text = text_decode(data)
    if re.search(r'<!doctype\s+html|<html\b|<body\b|<table\b', text, re.I):
        return [(label, 'HTML', html_text(text))], []
    return [(label, 'plain text', text)], []


def excerpts(text, count=10):
    lines = text.splitlines()
    # Prefer explicit operation/collision rules over a generic clock pin table.
    ranked = []
    high = re.compile(r'(same|common|simultan|synchron|asynchron|independen).{0,90}(clock|read|write)|'
                      r'clock.{0,90}(same|common|simultan|collision|contention|separat)|'
                      r'(collision|contention|same.address|same.row|\btcc\b|COLLDISN)', re.I)
    low = re.compile(r'CLKA|CLKB|RET1N|EMAA|EMAB|setup|hold|read.{0,12}write|clock', re.I)
    for i, line in enumerate(lines):
        score = 2 if high.search(line) else 1 if low.search(line) else 0
        if score:
            ranked.append((-score, i))
    selected, covered = [], set()
    for _, i in sorted(ranked):
        if i in covered:
            continue
        start, end = max(0, i-2), min(len(lines), i+4)
        covered.update(range(start, end))
        snippet = ' '.join(line.strip() for line in lines[start:end] if line.strip())
        selected.append((i+1, snippet[:800]))
        if len(selected) >= count:
            break
    return sorted(selected)


def pick_documents(paths, limit):
    candidates = []
    for path in paths:
        lower = path.lower()
        if lower.endswith(('.png', '.gif', '.jpg', '.jpeg', '.svg', '.css', '.js')):
            continue
        corner = 0 if '_tt_1p10v_1p10v_25c' in lower else 2 if re.search(r'(?:^|[/_.-])(?:ff|ss|tt)[_-]', lower) else 1
        known = 0 if lower.endswith(('.pdf', '.ps', '.eps', '.html', '.htm', '.ds', '.txt', '.gz', '.zip')) else 1
        candidates.append((corner, known, path))
    return [entry[2] for entry in sorted(candidates)[:limit]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/storage1/admin_public_dir/SRAM_Lib_2025')
    parser.add_argument('--out-dir')
    parser.add_argument('--macro', action='append', help='default: RAMTP1024X16 (the 40 physical cells)')
    parser.add_argument('--max-docs', type=int, default=1, help='per macro; prioritize current TT and generic documents')
    args = parser.parse_args()
    if args.out_dir:
        out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
        if os.path.exists(out_dir):
            parser.error('--out-dir must be new; do not overwrite earlier evidence')
        os.makedirs(out_dir)
    else:
        parent = os.path.expanduser('~/soc')
        if not os.path.isdir(parent):
            parser.error('~/soc absent; specify a new --out-dir')
        out_dir = tempfile.mkdtemp(prefix='kwt_sram_datasheets_' + time.strftime('%Y%m%d_%H%M%S') + '_', dir=parent)
    if args.max_docs < 1:
        parser.error('--max-docs must be positive')
    summary, inventory, failures = [], [], []
    summary.append('MODE: read-only datasheet extraction; no synthesis or timing exceptions')
    for name in args.macro or ['RAMTP1024X16']:
        if not re.match(r'^RAM(?:TP|SP)[0-9]+X[0-9]+$', name):
            parser.error('Unsupported macro name: ' + name)
        directory = os.path.join(args.root, name, 'datasheet')
        summary.append('DATASHEET_DIR: ' + directory)
        if not os.path.isdir(directory):
            failures.append((directory, 'directory absent'))
            continue
        paths = sorted(as_text(os.path.join(folder, filename)) for folder, _, files in os.walk(directory) for filename in files)
        if not paths:
            failures.append((directory, 'directory empty'))
        selected = pick_documents(paths, args.max_docs)
        summary.append('DOCUMENT_SELECTION: %d of %d files; current TT then generic docs; all paths in inventory.txt' % (len(selected), len(paths)))
        if paths and not selected:
            failures.append((directory, 'no document candidate found; see inventory.txt'))
        for path in paths:
            if path not in selected:
                inventory.append('FILE: %s; bytes=%s; not selected for this excerpt run' % (path, os.path.getsize(path)))
        # Selection order matters: the current TT document precedes other corners.
        for path in selected:
            print(('READ_DATASHEET: ' + path).encode('ascii', 'backslashreplace').decode('ascii'))
            sys.stdout.flush()
            with open(path, 'rb') as stream:
                data = stream.read(LIMIT+1)
            digest = hashlib.sha256(data).hexdigest() if len(data) <= LIMIT else '<size limit>'
            inventory.append('FILE: %s; bytes=%s; SHA256=%s' % (path, os.path.getsize(path), digest))
            units, failed = extract(data, path, out_dir)
            failures.extend(failed)
            for label, kind, text in units:
                key = hashlib.sha256(label.encode('utf-8')).hexdigest()[:16]
                text_path = os.path.join(out_dir, name + '_' + key + '.txt')
                with io.open(text_path, 'w', encoding='utf-8', newline='\n') as stream:
                    stream.write(text)
                summary.append('DATASHEET_TEXT: %s; format=%s; full_text=%s' % (label, kind, text_path))
                matches = excerpts(text)
                if not matches:
                    summary.append('EXCERPT: no keyword match; full text retained; no conclusion inferred')
                for line, snippet in matches:
                    summary.append('DATASHEET_LINE_%d: %s' % (line, snippet))
    for label, reason in failures:
        summary.append('EXTRACTION_UNRESOLVED: %s; %s' % (label, reason))
    summary.append('RESULT: ' + ('EXTRACTION_INCOMPLETE' if failures else 'EXTRACTION_COMPLETE (evidence only; not timing closure)'))
    summary.append('REPORT_DIR: ' + out_dir)
    for filename, lines in [('inventory.txt', inventory), ('summary.txt', summary)]:
        with io.open(os.path.join(out_dir, filename), 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(u'\n'.join(as_text(line) for line in lines) + u'\n')
    # ASCII escaping keeps Python 2 piping reliable while UTF-8 evidence is retained.
    for line in summary:
        print(as_text(line).encode('ascii', 'backslashreplace').decode('ascii'))
    return 2 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
