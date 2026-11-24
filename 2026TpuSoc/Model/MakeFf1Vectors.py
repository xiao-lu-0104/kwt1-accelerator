"""Standalone FF1 vectors at each layer's actual pre-FF1 (Norm1) input."""
import argparse
import json
from pathlib import Path

import numpy as np

from MakeVectors import Synthetic
from Reference import Encoder, Linear, Quantize, QuantizeParameters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=Path('workspace/Model/official'))
    parser.add_argument('--out', type=Path, default=Path('workspace/Sim/out/Ff1'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = []
    for name in ('normal', 'zero', 'extreme'):
        inputs, params = Synthetic(2026)
        if name == 'zero':
            inputs = np.zeros_like(inputs)
            params = {key: np.ones_like(value) if key.endswith('Gamma') else np.zeros_like(value)
                      for key, value in params.items()}
        if name == 'extreme':
            inputs = np.where(np.indices(inputs.shape).sum(axis=0) % 2, -32., 32767 / 1024)
            params = {key: np.where(np.indices(value.shape).sum(axis=0) % 2, -32., 32767 / 1024)
                      for key, value in params.items()}
        cases.append((name, inputs, params))
    for layer in range(12):
        cases.append((f'Layer{layer}', np.load(args.model / f'Input{layer}.npy'),
                      dict(np.load(args.model / f'Layer{layer}.npz'))))
    commands, reports = [], []
    for name, inputs, params in cases:
        stages = Encoder(inputs, params)
        fixed_params, fractions = QuantizeParameters(params)
        fixed_input = Quantize(stages['Norm1'])
        fraction = fractions['Ff1Weight']
        expected = Linear(fixed_input, fixed_params['Ff1Weight'],
                          fixed_params['Ff1Bias'], Shift=fraction)
        packed = np.concatenate([fixed_params['Ff1Weight'].T.reshape(-1),
                                 fixed_params['Ff1Bias']])
        directory = args.out / name
        directory.mkdir(exist_ok=True)
        paths = [directory / item for item in ('Input.bin', 'Params.bin', 'Expected.bin')]
        for path, values in zip(paths, (fixed_input, packed, expected)):
            np.asarray(values, dtype='<i2').tofile(path)
        # Legacy local SoC host test only: one task image, not the future
        # cycle-driven competition-platform parameter loader.
        image = bytearray(0x4000 + packed.size * 2)
        image[:fixed_input.size * 2] = np.asarray(fixed_input, dtype='<i2').tobytes()
        image[0x4000:] = np.asarray(packed, dtype='<i2').tobytes()
        (directory / 'Ddr.bin').write_bytes(image)
        (directory / 'Expected0.bin').write_bytes(paths[2].read_bytes())
        (directory / 'Fraction.txt').write_text(str(fraction) + '\n')
        commands.append(' '.join([*(str(path.resolve()) for path in paths), str(fraction), name]))
        reports.append({'case': name, 'input': 'quantized float-reference Norm1 output',
                        'fraction': fraction, 'output_elements': int(expected.size),
                        'input_bytes': fixed_input.size * 2, 'parameter_bytes': packed.size * 2,
                        'output_bytes': expected.size * 2})
    (args.out / 'Cases.txt').write_text('\n'.join(commands) + '\n')
    (args.out / 'Vectors.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(f'FF1 vectors: {len(cases)} cases, 25344 signed16 outputs/case')


if __name__ == '__main__':
    main()
