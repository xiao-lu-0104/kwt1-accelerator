"""Generate vectors for tb_kwt_gemm4.

Layout matches rtl/kwt_gemm4.v:
    act_flat[i*8 +: 8]          = activation i
    wgt_flat[c*256 + i*4 +: 4]  = weight of channel c, input i
Hex strings list the highest index first.
"""
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'sim', 'vectors')
N_VEC = 200

rng = np.random.RandomState(20261018)
lines = [str(N_VEC)]

for k in range(N_VEC):
    if k == 0:
        a = np.zeros(64, np.int64)
        w = np.zeros((4, 64), np.int64)
    elif k == 1:
        a = np.full(64, 127, np.int64)
        w = np.full((4, 64), 7, np.int64)
    elif k == 2:
        a = np.full(64, -128, np.int64)
        w = np.full((4, 64), -8, np.int64)
    else:
        a = rng.randint(-128, 128, 64).astype(np.int64)
        w = rng.randint(-8, 8, (4, 64)).astype(np.int64)

    accs = [int(np.sum(a * w[c])) for c in range(4)]
    for acc in accs:
        assert -2**31 <= acc < 2**31

    a_hex = ''.join('%02x' % (int(a[i]) & 0xFF) for i in range(63, -1, -1))
    w_hex = ''.join(
        '%x' % (int(w[c, i]) & 0xF)
        for c in range(3, -1, -1)
        for i in range(63, -1, -1))
    acc_hex = ['%08x' % (x & 0xFFFFFFFF) for x in accs]
    lines.append('%s %s %s' % (a_hex, w_hex, ' '.join(acc_hex)))

os.makedirs(OUT_DIR, exist_ok=True)
path = os.path.join(OUT_DIR, 'gemm4.txt')
with open(path, 'w', encoding='ascii', newline='\n') as f:
    f.write('\n'.join(lines) + '\n')
print('wrote %s (%d vectors)' % (path, N_VEC))
