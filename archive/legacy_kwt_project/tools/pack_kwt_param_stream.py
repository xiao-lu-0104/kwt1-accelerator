#!/usr/bin/env python3
"""Pack existing golden parameters into the CPU's little-endian 64-bit records.

Only representation changes: weights, bias/multiplier, LN and constants come
directly from enc12 vectors. No calibration, quantization or reference changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def load_values(directory, name, count, bits):
    values = [int(word, 16) for word in (directory / name).read_text().split()]
    if len(values) != count or any(value < 0 or value >= (1 << bits) for value in values):
        raise ValueError('Wrong count or width: ' + name)
    return values


def pack_records(directory):
    weights = load_values(directory, 'wrom.mem', 12*49152, 4)
    bias = load_values(directory, 'brom_b.mem', 12*576, 32)
    multiplier = load_values(directory, 'brom_m.mem', 12*576, 32)
    gamma = load_values(directory, 'lnrom_g.mem', 12*128, 16)
    beta = load_values(directory, 'lnrom_b.mem', 12*128, 16)
    constants = load_values(directory, 'lconst.mem', 12*6, 32)
    records = []
    for layer in range(12):
        for offset in range(0, 49152, 16):
            records.append(sum(weights[layer*49152+offset+i] << (4*i) for i in range(16)))
        for offset in range(576):
            records.append(bias[layer*576+offset] | (multiplier[layer*576+offset] << 32))
        for offset in range(128):
            records.append(gamma[layer*128+offset] | (beta[layer*128+offset] << 16))
        records.extend(value << 32 for value in constants[layer*6:(layer+1)*6])
    assert len(records) == 12*3782
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vectors', type=Path, default=Path(__file__).resolve().parents[1]/'sim/vectors/enc12')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    records = pack_records(args.vectors)
    args.out.mkdir(parents=True, exist_ok=True)
    payload = b''.join(struct.pack('<Q', record) for record in records)
    words = [part for record in records for part in (record & 0xffffffff, record >> 32)]
    with (args.out/'param_stream.mem').open('x', encoding='ascii', newline='\n') as stream:
        stream.write(''.join('%08x\n' % word for word in words))
    with (args.out/'param_stream.bin').open('xb') as stream:
        stream.write(payload)
    report = {'layers': 12, 'records_per_layer': 3782, 'words_per_layer': 7564,
              'bytes_per_layer': 30256, 'bytes_total': len(payload),
              'byte_order': 'little', 'sha256': hashlib.sha256(payload).hexdigest()}
    with (args.out/'param_stream.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print('PARAM_STREAM: ' + json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
