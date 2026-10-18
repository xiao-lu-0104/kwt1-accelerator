"""Generate test vectors for tb_kwt_dot64.

Format:
    line 0: number of vectors
    then per line: <act 128 hex chars> <wgt 64 hex chars> <acc 8 hex chars>

Bit order matches Verilog slicing:
    act_flat[i*8 +: 8] = activation i   -> hex string lists index 63 first
    wgt_flat[i*4 +: 4] = weight i
"""
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'sim', 'vectors')
N_VEC = 300

rng = np.random.RandomState(20261017)
lines = [str(N_VEC)]

for k in range(N_VEC):
    if k == 0:
        a = np.zeros(64, np.int64)
        w = np.zeros(64, np.int64)
    elif k == 1:
        a = np.full(64, 127, np.int64)
        w = np.full(64, 7, np.int64)
    elif k == 2:
        a = np.full(64, -128, np.int64)
        w = np.full(64, -8, np.int64)   # int4 min (out of spec range, boundary test)
    elif k == 3:
        a = np.full(64, 127, np.int64)
        w = np.full(64, -8, np.int64)
    elif k == 4:
        a = np.full(64, -128, np.int64)
        w = np.full(64, 7, np.int64)
    else:
        a = rng.randint(-128, 128, 64).astype(np.int64)
        w = rng.randint(-8, 8, 64).astype(np.int64)

    acc = int(np.sum(a * w))
    assert -2**31 <= acc < 2**31, acc

    a_hex = ''.join('%02x' % (int(a[i]) & 0xFF) for i in range(63, -1, -1))
    w_hex = ''.join('%x' % (int(w[i]) & 0xF) for i in range(63, -1, -1))
    acc_hex = '%08x' % (acc & 0xFFFFFFFF)
    lines.append('%s %s %s' % (a_hex, w_hex, acc_hex))

os.makedirs(OUT_DIR, exist_ok=True)
path = os.path.join(OUT_DIR, 'dot64.txt')
with open(path, 'w', encoding='ascii', newline='\n') as f:
    f.write('\n'.join(lines) + '\n')

print('wrote %s (%d vectors)' % (path, N_VEC))
print('sample acc range: see vectors')
