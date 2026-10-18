"""Vectors for rtl/kwt_gelu.v: every int8 input, expected LUT output."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'sim', 'vectors', 'gelu')

with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), 'r', encoding='utf-8') as f:
    doc = json.load(f)
lut = doc['gelu_lut']

xs = list(range(-128, 128))
expect = []
for x in xs:
    idx = x + 127
    idx = 0 if idx < 0 else (254 if idx > 254 else idx)
    expect.append(lut[idx])

os.makedirs(OUT_DIR, exist_ok=True)


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % v for v in values) + '\n')


dump(os.path.join(OUT_DIR, 'x.mem'), [v & 0xFF for v in xs], '%02x')
dump(os.path.join(OUT_DIR, 'expect.mem'), [v & 0xFF for v in expect], '%02x')
print('gelu vectors: %d' % len(xs))
print('x=-128..-125 ->', expect[:4], ' x=0 ->', expect[128], ' x=127 ->', expect[-1])
