"""Generate vectors for tb_kwt_softmax.

Files:
  score.mem   rows of 99 int16 (one line per value)
  expect.mem  99 uint8 probabilities per case
TB drives 60 cases sequentially.
"""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import fixed_softmax as fsm  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'sim', 'vectors', 'softmax')
N = 99
CASES = 60
rng = np.random.RandomState(20261019)

scores = []
for k in range(CASES):
    if k == 0:
        s = np.zeros(N, np.int64)
    elif k == 1:
        s = np.full(N, -500, np.int64)
    elif k == 2:
        s = np.full(N, 5000, np.int64)
        s[0] = -5000
    elif k == 3:
        s = rng.randint(-5200, 5200, N).astype(np.int64)
        s[7] = 5200
    elif k == 4:
        s = np.arange(N, dtype=np.int64) * 100
    elif k == 5:
        s = -(np.arange(N, dtype=np.int64) * 100)
    else:
        s = rng.randint(-5200, 5200, N).astype(np.int64)
    scores.append(s)

scores = np.stack(scores)
probs = np.stack([fsm.softmax_fixed(s) for s in scores])

os.makedirs(OUT_DIR, exist_ok=True)


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % v for v in values) + '\n')


dump(os.path.join(OUT_DIR, 'score.mem'), np.asarray(scores.reshape(-1)) & 0xFFFF, '%04x')
dump(os.path.join(OUT_DIR, 'expect.mem'), probs.reshape(-1), '%02x')

print('wrote softmax vectors: %d cases x %d' % (CASES, N))
print('prob sample case 6:', probs[6][:10], 'sum', probs[6].sum())
print('prob sum range: %d..%d' % (probs.sum(axis=1).min(), probs.sum(axis=1).max()))
