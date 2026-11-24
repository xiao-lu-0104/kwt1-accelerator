"""Verify the v4 run before reusing its mapped checkpoint; Python 2.7/3."""
from __future__ import print_function
import hashlib
import json
import os
import shutil
import sys

COMMIT = '88e529eff28f4ba75fc250fe2e03310e267b3af7'
MANIFEST = 'c200b421384d726f89ceB7f8bb76be5c63c3a98ee40949643243d471ff7703bc'.lower()


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            data = stream.read(1024*1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def read(path):
    with open(path, 'rb') as stream:
        return stream.read()


def prepare(original, work):
    manifest = os.path.join(original, 'package_manifest.sha256')
    if sha(manifest) != MANIFEST:
        raise ValueError('Expected exact single-clock v4 package manifest')
    entries = {}
    for line in read(manifest).decode('ascii').splitlines():
        digest, relative = line.split(None, 1)
        entries[relative] = digest
    for relative, digest in entries.items():
        if relative.startswith(('Rtl/', 'Backend/', 'e203_hbirdv2/', 'Server/')):
            path = os.path.join(original, 'project', *relative.split('/'))
            if os.path.islink(path) or sha(path) != digest:
                raise ValueError('Run source changed: '+relative)
    for relative, marker in [('logs/vcs_run_SpBindingTest.log', b'PASS SP_BINDING:'),
                             ('logs/library.log', b'SP_LIBRARY_COMPLETE:')]:
        if marker not in read(os.path.join(original, *relative.split('/'))):
            raise ValueError('Missing previous passing evidence: '+relative)
    top = 'E203TpuBackend'
    summary = read(os.path.join(original, top, 'summary.txt'))
    if ('SOURCE_COMMIT: '+COMMIT).encode('ascii') not in summary or b'ASIC_REPORTS_COMPLETE:' not in summary:
        raise ValueError('Expected complete single-clock summary')
    libraries = []
    for line in read(os.path.join(original, 'library_sha256.txt')).decode('utf-8').splitlines():
        digest, path = line.split(None, 1)
        if sha(path) != digest:
            raise ValueError('Cached library changed: '+path)
        libraries.append(dict(path=path, sha256=digest))
    spdb = os.path.join(original, 'sram_db', 'RAMSP1024X16_tt_1p10v_1p10v_25c.db')
    std = [entry['path'] for entry in libraries if entry['path'] != spdb]
    if len(libraries) != 2 or len(std) != 1 or not any(entry['path'] == spdb for entry in libraries):
        raise ValueError('Expected one standard-cell and one SRAM DB')
    checkpoint = os.path.join(original, top, top+'_mapped.ddc')
    digest = sha(checkpoint)
    copy = os.path.join(work, 'input.ddc')
    shutil.copyfile(checkpoint, copy)
    if sha(copy) != digest:
        raise ValueError('Checkpoint copy mismatch')
    for name, path in [('StdDb.txt', std[0]), ('SpDb.txt', spdb)]:
        with open(os.path.join(work, name), 'w') as stream:
            stream.write(path+'\n')
    record = dict(original_run=original, source_commit=COMMIT, libraries=libraries,
                  checkpoint=dict(path=checkpoint, sha256=digest),
                  checkpoint_copy=dict(path=copy, sha256=digest))
    with open(os.path.join(work, 'inputs.json'), 'w') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print('HOLD_INPUTS_VERIFIED: v4 sources, passing macro test, cached DB hashes, private DDC copy')


def recheck(work):
    with open(os.path.join(work, 'inputs.json')) as stream:
        record = json.load(stream)
    for entry in [record['checkpoint'], record['checkpoint_copy']] + record['libraries']:
        if sha(entry['path']) != entry['sha256']:
            raise ValueError('Reused input changed: '+entry['path'])
    print('ORIGINAL_CHECKPOINT_AND_LIBRARIES: UNCHANGED (hash verified)')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--recheck':
        recheck(sys.argv[2])
    elif len(sys.argv) == 3:
        prepare(os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2]))
    else:
        raise SystemExit('Usage: VerifyHoldInputs.py ORIGINAL_RUN NEW_WORK | --recheck NEW_WORK')
