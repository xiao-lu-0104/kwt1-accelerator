"""Replay frozen quantized HEX vectors with the original numerical reference.

This checks fixed-point model/HEX consistency, not RTL execution or speech accuracy.
No network access, tool installation or float-parameter regeneration is performed.
"""
import argparse
import json
from pathlib import Path
import re
import sys


def raw_words(path):
    words = path.read_text(encoding='utf-8').split()
    if not words or any(not re.fullmatch(r'[0-9a-fA-F]{8}', word) for word in words):
        raise ValueError('Expected packed little-endian 32-bit HEX: ' + str(path))
    return b''.join(int(word, 16).to_bytes(4, 'little') for word in words)


def replay(vectors, model):
    sys.dont_write_bytecode = True
    import numpy as np
    sys.path.insert(0, str(model))
    from Reference import Encoder, Linear

    def values(path, count):
        result = np.frombuffer(raw_words(path), dtype='<i2').astype(np.int64)
        if result.size != count:
            raise ValueError('Unexpected value count: ' + str(path))
        return result

    def equal(actual, expected, name):
        if actual.shape != expected.shape:
            raise ValueError('Shape mismatch: ' + name)
        differences = np.flatnonzero(actual.reshape(-1) != expected.reshape(-1))
        if differences.size:
            index = int(differences[0])
            raise ValueError('Numerical mismatch: %s index=%d actual=%d expected=%d' %
                             (name, index, actual.flat[index], expected.flat[index]))

    ff1 = []
    for name in ('normal', 'zero', 'extreme', *(f'Layer{i}' for i in range(12))):
        source = vectors / ('Ff1_' + name)
        data = values(source / 'Input.hex', 99 * 64).reshape(99, 64)
        packed = values(source / 'Layer0.hex', 64 * 256 + 256)
        weight = packed[:64 * 256].reshape(256, 64).T
        fraction = int.from_bytes(raw_words(source / 'Fractions.hex'), 'little')
        if not 1 <= fraction <= 15:
            raise ValueError('Invalid FF1 fraction: ' + name)
        actual = Linear(data, weight, packed[64 * 256:], Shift=fraction)
        equal(actual, values(source / 'Expected0.hex', 99 * 256).reshape(99, 256), 'ff1/' + name)
        ff1.append({'case': name, 'values': int(actual.size)})

    scale_bytes = raw_words(vectors / 'Fractions.hex')
    if len(scale_bytes) != 48:
        raise ValueError('Expected twelve packed fraction words')
    current = values(vectors / 'Input.hex', 99 * 64).reshape(99, 64)
    encoders = []
    groups = (('Query', 64, 64, False), ('Key', 64, 64, False),
              ('Value', 64, 64, False), ('Output', 64, 64, True),
              ('Norm1', 0, 64, True), ('Ff1', 64, 256, True),
              ('Ff2', 256, 64, True), ('Norm2', 0, 64, True))
    for layer in range(12):
        packed = values(vectors / f'Layer{layer}.hex', 99584 // 2)
        scale_word = int.from_bytes(scale_bytes[4 * layer:4 * layer + 4], 'little')
        params, fractions, offset = {}, {}, 0
        for index, (name, inputs, outputs, bias) in enumerate(groups):
            fraction = ((scale_word >> (4 * index)) & 15) + 1
            if fraction > 15:
                raise ValueError('Invalid encoder fraction')
            if inputs:
                size = inputs * outputs
                params[name + 'Weight'] = packed[offset:offset + size].reshape(outputs, inputs).T
                offset += size
                fractions[name + 'Weight'] = fraction
                if bias:
                    params[name + 'Bias'] = packed[offset:offset + outputs]
                    offset += outputs
            else:
                params[name + 'Gamma'] = packed[offset:offset + outputs]
                params[name + 'Beta'] = packed[offset + outputs:offset + 2 * outputs]
                offset += 2 * outputs
                fractions[name + 'Gamma'] = fraction
        if offset != packed.size:
            raise ValueError('Unconsumed layer parameters')
        current = Encoder(current, params, Fixed=True, Fractions=fractions)['Output']
        equal(current, values(vectors / f'Expected{layer}.hex', 99 * 64).reshape(99, 64),
              'encoder/layer' + str(layer))
        encoders.append({'layer': layer, 'values': int(current.size)})
    return {'status': 'PASS_FIXED_POINT_HEX_REPLAY', 'numpy_version': np.__version__,
            'ff1_cases': ff1, 'encoder_layers': encoders,
            'scope': 'Original fixed-point numerical model versus frozen quantized HEX outputs; no RTL rerun or official accuracy score.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path(__file__).resolve().parent / 'Model')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(args.vectors.resolve(), args.model.resolve())
    except ModuleNotFoundError as error:
        if error.name != 'numpy':
            raise
        result = {'status': 'DEPENDENCY_UNAVAILABLE', 'dependency': 'numpy',
                  'scope': 'Source/HEX checksums can be checked, but numerical execution was not performed.'}
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('NUMERICAL_REPLAY: DEPENDENCY_UNAVAILABLE numpy; no installation attempted', flush=True)
        return 3
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('NUMERICAL_REPLAY: PASS ff1_cases=15 encoder_layers=12; model/HEX only', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
