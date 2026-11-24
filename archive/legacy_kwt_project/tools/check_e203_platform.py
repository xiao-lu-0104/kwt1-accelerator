#!/usr/bin/env python
"""Offline E203 source comparison; compatible with Python 2.7 and Python 3.

Create locally: python tools/check_e203_platform.py --make external/e203_hbirdv2
Check remotely: python check_e203_platform.py --check /path/to/e203_hbirdv2-master
Upload this script and e203_github_reference.json together. Read-only in check mode.
"""
from __future__ import print_function
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTS = ('rtl', 'tb', 'vsim')
RTL_EXT = ('.v', '.sv', '.vh', '.svh')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    with open(path, 'rb') as stream:
        return stream.read()


def normalized(data):
    # Ignore only Windows versus Unix line endings, not spaces or comments.
    return data.replace(b'\r\n', b'\n')


def show(label, paths):
    print('%s: %d' % (label, len(paths)))
    for path in paths:
        print('  ' + path)


def make_manifest(root, filename):
    args = ['git', '-C', root, 'ls-files', '-z', '--']
    args += list(ROOTS) + ['e203_core.core', 'e203_soc.core']
    paths = subprocess.check_output(args).decode('utf-8').split('\0')
    entries = {}
    for path in sorted(p for p in paths if p):
        data = read_bytes(os.path.join(root, *path.split('/')))
        entries[path] = {'sha256': digest(data),
                         'lf_sha256': digest(normalized(data)), 'bytes': len(data)}
    commit = subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'])
    manifest = {'commit': commit.decode('ascii').strip(), 'files': entries,
                'scope': 'git-tracked rtl/, tb/, vsim/, and two root .core files'}
    with io.open(filename, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + u'\n')
    print('Wrote %d reference files: %s' % (len(entries), filename))
    print('Git commit: ' + manifest['commit'])


def check(root, filename):
    with io.open(filename, 'r', encoding='utf-8') as stream:
        manifest = json.load(stream)
    print('Reference commit: ' + manifest['commit'])
    print('Scope: ' + manifest['scope'])
    print('Platform root: ' + root)
    same, newline, changed, missing = [], [], [], []
    installed_diff, installed_missing = [], []
    install = os.path.join(root, 'vsim', 'install')
    for path, entry in sorted(manifest['files'].items()):
        full = os.path.join(root, *path.split('/'))
        if not os.path.isfile(full):
            missing.append(path)
            continue
        data = read_bytes(full)
        if digest(data) == entry['sha256']:
            same.append(path)
        elif digest(normalized(data)) == entry['lf_sha256']:
            newline.append(path)
        else:
            changed.append(path)
        copy_rel = None
        if path.startswith('rtl/e203/'):
            copy_rel = 'rtl/' + path[len('rtl/e203/'):]
        elif path.startswith('tb/'):
            copy_rel = path
        if copy_rel and path.endswith(RTL_EXT) and os.path.isdir(install):
            copy = os.path.join(install, *copy_rel.split('/'))
            if not os.path.isfile(copy):
                installed_missing.append(copy_rel)
            elif normalized(read_bytes(copy)) != normalized(data):
                installed_diff.append(copy_rel)
    extra = []
    for top in ('rtl', 'tb'):
        for directory, dirs, files in os.walk(os.path.join(root, top)):
            dirs[:] = [d for d in dirs if d != '.git']
            for name in files:
                rel = os.path.relpath(os.path.join(directory, name), root).replace(os.sep, '/')
                if name.endswith(RTL_EXT) and rel not in manifest['files']:
                    extra.append(rel)
    print('BYTE_IDENTICAL: %d / %d' % (len(same), len(manifest['files'])))
    show('LINE_ENDINGS_ONLY', newline)
    show('CHANGED', changed)
    show('MISSING', missing)
    show('EXTRA_RTL', sorted(extra))
    if os.path.isdir(install):
        print('Checking vsim/install copies against current platform sources:')
        show('INSTALL_DIFFERS_FROM_SOURCE', installed_diff)
        show('INSTALL_MISSING_SOURCE_COPY', installed_missing)
    else:
        print('vsim/install not present; installed-copy comparison skipped.')
    failed = changed or missing or extra or installed_diff or installed_missing
    if failed:
        print('RESULT: DIFFERENCES_FOUND (review listed files before integration)')
    else:
        print('RESULT: MATCH_IN_CHECKED_SCOPE (line-ending differences permitted)')
    print('Generated run logs/waves, toolchains, and files outside the stated scope are not compared.')
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--make', metavar='LOCAL_GIT_ROOT')
    mode.add_argument('--check', metavar='SERVER_PLATFORM_ROOT')
    parser.add_argument('--manifest', default=os.path.join(HERE, 'e203_github_reference.json'))
    args = parser.parse_args()
    if args.make:
        make_manifest(os.path.abspath(args.make), args.manifest)
        return 0
    return check(os.path.abspath(args.check), args.manifest)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (IOError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(2)
