"""Generate requant test vectors (bit-exact semantics of rtl/kwt_requant.v)."""
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'sim', 'vectors')
N_VEC = 400


def requant(acc, m_int):
    """Must match RTL exactly: (acc*m + 2^30) >>> 31, then saturate to [-127,127]."""
    prod = acc * m_int
    shifted = (prod + (1 << 30)) >> 31          # python >> on int is arithmetic
    if shifted > 127:
        return 127
    if shifted < -127:
        return -127
    return shifted


rng = np.random.RandomState(4242)
lines = [str(N_VEC)]

cases = []
# boundary / saturation cases
for acc in (0, 1, -1, 2**31 - 1, -2**31, 127 << 31, -(127 << 31)):
    for m in (1 << 30, (1 << 31) - 1, 1):
        a = int(np.clip(acc, -2**31, 2**31 - 1))
        cases.append((a, m))
# random cases with realistic M in [0.01, 1.0)
for _ in range(N_VEC - len(cases)):
    acc = int(rng.randint(-200000, 200000))
    m = int(rng.uniform(0.01, 1.0) * (1 << 31))
    m = min(m, 2**31 - 1)
    cases.append((acc, m))

for acc, m in cases[:N_VEC]:
    q = requant(acc, m)
    lines.append('%08x %08x %02x' % (acc & 0xFFFFFFFF, m & 0xFFFFFFFF, q & 0xFF))

os.makedirs(OUT_DIR, exist_ok=True)
path = os.path.join(OUT_DIR, 'requant.txt')
with open(path, 'w', encoding='ascii', newline='\n') as f:
    f.write('\n'.join(lines) + '\n')
print('wrote %s (%d vectors)' % (path, N_VEC))
