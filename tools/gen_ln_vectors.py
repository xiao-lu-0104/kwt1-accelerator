"""Bit-exact LN reference + vectors for rtl/kwt_layernorm.v."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

N = 64
ROWS = 20
OUT_DIR = os.path.join(ROOT, 'sim', 'vectors', 'ln')
RSQRT_LUT = [max(1, int(round(65536.0 / np.sqrt((k + 0.5) * 1024)))) for k in range(256)]


def ln_row_rtl(row, gamma_q, beta_q, eps_q):
    n = len(row)
    s = int(sum(row))
    mean = (s + n // 2) >> 6
    var = int(sum((int(x) - mean) ** 2 for x in row))
    var = (var >> 6) + eps_q
    idx = 255 if (var >> 10) > 255 else (var >> 10)
    inv = RSQRT_LUT[idx]
    for _ in range(3):
        y0sq = (inv * inv) >> 16
        vy = var * y0sq
        t3 = 196608 - vy
        y1 = (inv * t3) >> 17
        inv = y1 if y1 > 0 else 1
    out = []
    for i, x in enumerate(row):
        d = int(x) - mean
        y_q8 = (d * inv) >> 8
        g = y_q8 * int(gamma_q[i])
        o = (g >> 16) + int(beta_q[i])
        out.append(int(np.clip(o, -127, 127)))
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), 'r', encoding='utf-8') as f:
        doc = json.load(f)
    L0 = doc['layers'][0]
    gamma_q = L0['ln1']['gamma_q']
    beta_q = L0['ln1']['beta_q']
    eps_q = int(round(doc['ln_eps_q']))

    rng = np.random.RandomState(20261020)
    scales = [float(L0['s_r1'])]
    rows = []
    for r in range(ROWS):
        if r == 0:
            row = np.zeros(N, np.int64)
        elif r == 1:
            row = np.full(N, 100, np.int64)
        elif r == 2:
            row = np.tile([100, -100], N // 2).astype(np.int64)
        else:
            std = 20.0 + 250.0 * rng.rand()       # realistic int16 residual range
            row = np.round(rng.randn(N) * std).astype(np.int64)
        row = np.clip(row, -32768, 32767)
        rows.append(row)
    rows = np.stack(rows)

    expect = np.stack([ln_row_rtl(r, gamma_q, beta_q, eps_q) for r in rows])

    def dump(path, values, fmt):
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write('\n'.join(fmt % v for v in values) + '\n')

    dump(os.path.join(OUT_DIR, 'x.mem'), np.asarray(rows.reshape(-1)) & 0xFFFF, '%04x')
    dump(os.path.join(OUT_DIR, 'gamma.mem'), np.asarray(gamma_q) & 0xFFFF, '%04x')
    dump(os.path.join(OUT_DIR, 'beta.mem'), np.asarray(beta_q) & 0xFFFF, '%04x')
    dump(os.path.join(OUT_DIR, 'expect.mem'), np.asarray(expect.reshape(-1)) & 0xFF, '%02x')

    print('rows=%d  eps_q=%d' % (ROWS, eps_q))
    print('gamma_q[0:4]', gamma_q[:4], 'beta_q[0:4]', beta_q[:4])
    print('row3 in :', rows[3][:8])
    print('row3 out:', expect[3][:8])


if __name__ == '__main__':
    main()
