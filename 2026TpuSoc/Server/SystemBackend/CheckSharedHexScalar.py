"""Standard-library scalar translation of the frozen Reference.py fixed-point path.

Checks quantized HEX consistency only: no NumPy, RTL rerun, float conversion,
installation, network access or official-sample accuracy measurement.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time

REFERENCE_SHA256 = 'e50545d6e42a5629c9aabc53b3681bd7ee8ed9875c99e8296003e0c3368ead00'
EXP = [math.floor(math.exp(-index / 64) * (1 << 20) + 0.5) for index in range(1025)]
GELU = [math.floor((index / 64) * .5 * (1 + math.erf(index / 64 / math.sqrt(2))) * 2048 + .5)
        for index in range(513)]


def integer_root(value):
    """Exact integer square root, including Python runtimes predating math.isqrt."""
    if value < 0:
        raise ValueError('Negative square root')
    if value < 2:
        return value
    root = 1 << ((value.bit_length() + 1) // 2)
    while True:
        following = (root + value // root) // 2
        if following >= root:
            return root
        root = following


ISQRT = getattr(math, 'isqrt', integer_root)


def shift(value, bits):
    if bits <= 0:
        raise ValueError('Positive rounding shift required')
    result = (abs(value) + (1 << (bits - 1))) >> bits
    return -result if value < 0 else result


def clip(value):
    return max(-32768, min(32767, value))


def linear(rows, columns, bias=None, fraction=10):
    if not rows or not columns or any(len(column) != len(rows[0]) for column in columns):
        raise ValueError('Inconsistent linear dimensions')
    bias = [0] * len(columns) if bias is None else bias
    if len(bias) != len(columns) or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('Inconsistent linear inputs/bias')
    return [[clip(shift(sum(a * b for a, b in zip(row, column)), fraction) + add)
             for column, add in zip(columns, bias)] for row in rows]


def softmax(rows):
    result = []
    for row in rows:
        peak = max(row)
        exps = []
        for value in row:
            delta = peak - value
            index, fraction = min(delta >> 4, 1023), delta & 15
            value = (EXP[index] * (16 - fraction) + EXP[index + 1] * fraction + 8) >> 4
            exps.append(value if delta < 16384 else 0)
        reciprocal = (1 << 44) // sum(exps)
        result.append([clip(shift(value * reciprocal, 29)) for value in exps])
    return result


def gelu(rows):
    result = []
    for row in rows:
        output = []
        for value in row:
            magnitude = abs(value)
            index, fraction = min(magnitude >> 5, 511), magnitude & 31
            transformed = (GELU[index] * (32 - fraction) + GELU[index + 1] * fraction + 16) >> 5
            if magnitude >= 16384:
                transformed = magnitude
            output.append(clip(transformed - magnitude if value < 0 else transformed))
        result.append(output)
    return result


def norm(rows, residual, gamma, beta, fraction):
    if len(gamma) != 64 or len(beta) != 64 or len(rows) != len(residual):
        raise ValueError('Expected 64-wide layer normalization')
    output = []
    for row, previous in zip(rows, residual):
        if len(row) != 64 or len(previous) != 64:
            raise ValueError('Expected 64-wide residual')
        added = [a + b for a, b in zip(row, previous)]
        mean = shift(sum(added), 2)
        centered = [value * 16 - mean for value in added]
        variance = (sum(value * value for value in centered) >> 6) + 1074
        reciprocal = (1 << 34) // ISQRT(variance)
        output.append([clip(shift(shift(value * reciprocal, 23) * gain, fraction) + offset)
                       for value, gain, offset in zip(centered, gamma, beta)])
    return output


def encoder(rows, params, fractions):
    def dense(value, name):
        return linear(value, params[name + 'Columns'], params.get(name + 'Bias'), fractions[name])
    stages = {}
    query = stages['Query'] = dense(rows, 'Query')
    key = stages['Key'] = dense(rows, 'Key')
    value = stages['Value'] = dense(rows, 'Value')
    stages['Score'] = linear(query, key, fraction=15)
    stages['Probability'] = softmax(stages['Score'])
    stages['Context'] = linear(stages['Probability'], list(zip(*value)), fraction=15)
    stages['Attention'] = dense(stages['Context'], 'Output')
    stages['Norm1'] = norm(stages['Attention'], rows, params['Norm1Gamma'], params['Norm1Beta'], fractions['Norm1'])
    stages['Ff1'] = dense(stages['Norm1'], 'Ff1')
    stages['Gelu'] = gelu(stages['Ff1'])
    stages['Ff2'] = dense(stages['Gelu'], 'Ff2')
    stages['Output'] = norm(stages['Ff2'], stages['Norm1'], params['Norm2Gamma'], params['Norm2Beta'], fractions['Norm2'])
    return stages


def raw(path):
    words = path.read_text(encoding='utf-8').split()
    if not words or any(not re.fullmatch(r'[0-9a-fA-F]{8}', word) for word in words):
        raise ValueError('Invalid 32-bit HEX: ' + str(path))
    return b''.join(int(word, 16).to_bytes(4, 'little') for word in words)


def values(path, count):
    data = raw(path)
    if len(data) != count * 2:
        raise ValueError('Unexpected value count: ' + str(path))
    return list(struct.unpack('<' + str(count) + 'h', data))


def matrix(data, width):
    if len(data) % width:
        raise ValueError('Unaligned matrix')
    return [data[index:index + width] for index in range(0, len(data), width)]


def same(actual, expected, name):
    if len(actual) != len(expected):
        raise ValueError('Shape mismatch: ' + name)
    for index, (got, wanted) in enumerate(zip(actual, expected)):
        if got != wanted:
            raise ValueError('Numerical mismatch: %s index=%d actual=%d expected=%d' % (name, index, got, wanted))


def replay(vectors, model):
    reference_sha = hashlib.sha256((model / 'Reference.py').read_bytes()).hexdigest()
    if reference_sha != REFERENCE_SHA256:
        raise ValueError('Scalar translation requires the unchanged frozen Reference.py')
    started = time.monotonic()
    cases, layers = [], []
    for name in ('normal', 'zero', 'extreme', *(f'Layer{i}' for i in range(12))):
        source = vectors / ('Ff1_' + name)
        rows = matrix(values(source / 'Input.hex', 99 * 64), 64)
        packed = values(source / 'Layer0.hex', 64 * 256 + 256)
        fraction_bytes = raw(source / 'Fractions.hex')
        if len(fraction_bytes) != 4:
            raise ValueError('Unexpected FF1 fraction words')
        fraction = int.from_bytes(fraction_bytes, 'little')
        if not 1 <= fraction <= 15:
            raise ValueError('Invalid FF1 fraction')
        actual = linear(rows, matrix(packed[:64 * 256], 64), packed[64 * 256:], fraction)
        same([value for row in actual for value in row], values(source / 'Expected0.hex', 99 * 256), 'ff1/' + name)
        cases.append({'case': name, 'values': 99 * 256})
        print('SCALAR_CASE: ff1/' + name + ' PASS', flush=True)
    scale_bytes = raw(vectors / 'Fractions.hex')
    if len(scale_bytes) != 48:
        raise ValueError('Expected twelve fraction words')
    current = matrix(values(vectors / 'Input.hex', 99 * 64), 64)
    groups = (('Query', 64, 64, False), ('Key', 64, 64, False), ('Value', 64, 64, False),
              ('Output', 64, 64, True), ('Norm1', 0, 64, True), ('Ff1', 64, 256, True),
              ('Ff2', 256, 64, True), ('Norm2', 0, 64, True))
    for layer in range(12):
        packed = values(vectors / f'Layer{layer}.hex', 99584 // 2)
        word = int.from_bytes(scale_bytes[4 * layer:4 * layer + 4], 'little')
        params, fractions, offset = {}, {}, 0
        for index, (name, inputs, outputs, bias) in enumerate(groups):
            fractions[name] = ((word >> (4 * index)) & 15) + 1
            if fractions[name] > 15:
                raise ValueError('Invalid encoder fraction')
            if inputs:
                size = inputs * outputs
                params[name + 'Columns'] = matrix(packed[offset:offset + size], inputs)
                offset += size
                if bias:
                    params[name + 'Bias'] = packed[offset:offset + outputs]
                    offset += outputs
            else:
                params[name + 'Gamma'] = packed[offset:offset + outputs]
                params[name + 'Beta'] = packed[offset + outputs:offset + 2 * outputs]
                offset += 2 * outputs
        if offset != len(packed):
            raise ValueError('Unconsumed parameters')
        current = encoder(current, params, fractions)['Output']
        same([value for row in current for value in row], values(vectors / f'Expected{layer}.hex', 99 * 64),
             'encoder/layer' + str(layer))
        layers.append({'layer': layer, 'values': 99 * 64})
        print('SCALAR_CASE: encoder/layer' + str(layer) + ' PASS', flush=True)
    return {'status': 'PASS_FIXED_POINT_HEX_REPLAY', 'implementation': 'PYTHON_STDLIB_SCALAR',
            'canonical_reference_sha256': reference_sha, 'ff1_cases': cases, 'encoder_layers': layers,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'scope': 'Scalar translation of frozen Reference.py fixed-point path versus quantized HEX. '
                     'No NumPy execution, RTL rerun, float-parameter conversion or official accuracy score.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.vectors.resolve(), args.model.resolve())
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('NUMERICAL_REPLAY: PASS_FIXED_POINT_HEX_REPLAY implementation=PYTHON_STDLIB_SCALAR ff1_cases=15 encoder_layers=12', flush=True)


if __name__ == '__main__':
    main()
