#!/usr/bin/env python
"""Original software-head consistency check, stdlib only (Python 2.7/3).

Reads the upstream-generated Head.npz without installing NumPy on the server.
This checks the synthetic test input, not speech classification accuracy.
"""
from __future__ import print_function
import argparse
import ast
import io
import json
import math
import os
import struct
import zipfile


def npy(data):
    source = io.BytesIO(data)
    if source.read(6) != b'\x93NUMPY':
        raise ValueError('Not an NPY array')
    major, minor = struct.unpack('BB', source.read(2))
    fmt = '<H' if major == 1 else '<I' if major in (2, 3) else None
    if fmt is None:
        raise ValueError('Unsupported NPY version')
    size = struct.unpack(fmt, source.read(struct.calcsize(fmt)))[0]
    header = ast.literal_eval(source.read(size).decode('ascii'))
    if header['fortran_order'] or header['descr'] not in ('<f4', '<f8'):
        raise ValueError('Expected little-endian C-order floats')
    count = 1
    for dim in header['shape']:
        count *= dim
    values = struct.unpack('<' + str(count) + ('f' if header['descr'] == '<f4' else 'd'), source.read())
    return header['shape'], values


def check(directory):
    with open(os.path.join(directory, 'Actual11.bin'), 'rb') as stream:
        actual = stream.read()
    with open(os.path.join(directory, 'Expected11.bin'), 'rb') as stream:
        expected = stream.read()
    if len(actual) != 12672 or actual != expected:
        raise ValueError('Final encoder bytes do not match reference')
    with zipfile.ZipFile(os.path.join(directory, 'Head.npz')) as head:
        shape, weight = npy(head.read('Weight.npy'))
        bshape, bias = npy(head.read('Bias.npy'))
    if shape != (64, 12) or bshape != (12,):
        raise ValueError('Unexpected classifier dimensions')
    token = struct.unpack('<64h', actual[:128])
    logits = [math.fsum(token[k] / 1024.0 * weight[k * 12 + c] for k in range(64)) + bias[c]
              for c in range(12)]
    with open(os.path.join(directory, 'Reference.json')) as stream:
        reference = json.load(stream)
    if any(abs(a-b) > 1e-12 for a, b in zip(logits, reference['fixed_logits'])):
        raise ValueError('Software-head logits differ from original reference')
    category = max(range(12), key=lambda c: logits[c])
    if category != reference['fixed_class']:
        raise ValueError('Software-head class differs from fixed reference')
    report = dict(rtl_class=category, fixed_class=reference['fixed_class'],
                  float_class=reference['float_class'], logits=logits, accuracy_evaluated=False)
    with open(os.path.join(directory, 'ServerClassification.json'), 'w') as stream:
        json.dump(report, stream, indent=2)
    print('PASS software head: class=%d; synthetic input; accuracy not evaluated' % category)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    check(args.directory)
