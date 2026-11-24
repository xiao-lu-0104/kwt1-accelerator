"""Offline files for cycle-driven loading of one reusable shared-SRAM slot."""
import argparse
import json
from pathlib import Path

import numpy as np
from Reference import Encoder, Quantize, QuantizeParameters


def words(path, data):
    raw = bytes(data)
    if len(raw) % 4:
        raise ValueError('Word file is not 32-bit aligned')
    path.write_text(''.join(f'{int.from_bytes(raw[i:i+4], "little"):08x}\n'
                            for i in range(0, len(raw), 4)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=Path('workspace/Model/official'))
    parser.add_argument('--ff1', type=Path, default=Path('workspace/Sim/out/Ff1'))
    parser.add_argument('--out', type=Path, default=Path('workspace/Sim/out/Shared'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    values = Quantize(np.load(args.model / 'Input0.npy'))
    words(args.out / 'Input.hex', np.asarray(values, dtype='<i2').tobytes())
    fractions = []
    for layer in range(12):
        params, scales = QuantizeParameters(dict(np.load(args.model / f'Layer{layer}.npz')))
        image = bytearray()
        for name in ('Query', 'Key', 'Value', 'Output', 'Norm1', 'Ff1', 'Ff2', 'Norm2'):
            if name.startswith('Norm'):
                group = np.concatenate([params[name + 'Gamma'], params[name + 'Beta']])
            else:
                group = params[name + 'Weight'].T.reshape(-1)
                if name + 'Bias' in params:
                    group = np.concatenate([group, params[name + 'Bias']])
            image.extend(np.asarray(group, dtype='<i2').tobytes())
        if len(image) != 99584:
            raise ValueError('Unexpected layer parameter length')
        names = ('QueryWeight', 'KeyWeight', 'ValueWeight', 'OutputWeight',
                 'Norm1Gamma', 'Ff1Weight', 'Ff2Weight', 'Norm2Gamma')
        fractions.append(sum((scales[name] - 1) << (4 * index) for index, name in enumerate(names)))
        words(args.out / f'Layer{layer}.hex', image)
        values = Encoder(values, params, Fixed=True, Fractions=scales)['Output']
        words(args.out / f'Expected{layer}.hex', np.asarray(values, dtype='<i2').tobytes())
    words(args.out / 'Fractions.hex', np.asarray(fractions, dtype='<u4').tobytes())
    for name in ('normal', 'zero', 'extreme', *(f'Layer{layer}' for layer in range(12))):
        target = args.out / ('Ff1_' + name)
        target.mkdir(exist_ok=True)
        source = args.ff1 / name
        for old, new in (('Input.bin', 'Input.hex'), ('Params.bin', 'Layer0.hex'),
                         ('Expected.bin', 'Expected0.hex')):
            words(target / new, (source / old).read_bytes())
        words(target / 'Fractions.hex', int((source / 'Fraction.txt').read_text()).to_bytes(4, 'little'))
    (args.out / 'Scope.json').write_text(json.dumps({
        'loader': 'All files read before timing; SRAM populated only by timed ICB writes',
        'input_bytes': 12672, 'encoder_layer_bytes': 99584, 'ff1_layer_bytes': 33280,
        'parameter_buffer_count': 1, 'cpu_data_work_region': '0x90035000..0x9003ffff'
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
