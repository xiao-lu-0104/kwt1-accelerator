"""Vectors for rtl/kwt_attn_score.v using real Q/K from layer 0 sample 0."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe

OUT = os.path.join(ROOT, 'sim', 'vectors', 'score')
TOK = 99
D = 64
OUT_DIM = 100
GROUPS = OUT_DIM // 4      # 25
N_WORD = TOK * GROUPS      # 2475


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % v for v in values) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), 'r', encoding='utf-8') as f:
        doc = json.load(f)
    m_score = int(doc['layers'][0]['m_score'])

    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    L = fe.FixedEncoderLayer(params['layers'][0], sc, sc['x'])

    x_f = kn.embed(z['mfcc'][0], params)
    x_q, _ = fe.q_tensor(x_f, stats['x'])
    q = fe.mm_fixed(x_q, L.qw_q, L.m_q)
    k = fe.mm_fixed(x_q, L.qw_k, L.m_k)

    # score = Q @ K^T with scale folded into m_score, int16 output
    w = np.zeros((D, OUT_DIM), np.int64)
    w[:, :TOK] = k.T
    score = fe.mm_act(q, w, m_score, out_bits=16)

    dump(os.path.join(OUT, 'q.mem'), np.asarray(q.reshape(-1)) & 0xFF, '%02x')
    dump(os.path.join(OUT, 'k.mem'), np.asarray(k.reshape(-1)) & 0xFF, '%02x')
    dump(os.path.join(OUT, 'm.mem'), [m_score & 0xFFFFFFFF], '%08x')

    u = (score.astype(np.int64) & 0xFFFF)
    packed = (u[:, 0::4] | (u[:, 1::4] << 16) | (u[:, 2::4] << 32) | (u[:, 3::4] << 48))
    dump(os.path.join(OUT, 'expect.mem'),
         [int(v) & 0xFFFFFFFFFFFFFFFF for v in packed.reshape(-1)], '%016x')

    print('m_score=%d' % m_score)
    print('score range [%d, %d]  (int16 domain)' % (score.min(), score.max()))
    print('expect words: %d' % N_WORD)


if __name__ == '__main__':
    main()
