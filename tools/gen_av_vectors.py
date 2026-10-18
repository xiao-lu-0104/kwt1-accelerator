"""Vectors for rtl/kwt_attn_av.v: real P (softmax) and V from layer 0."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe
import fixed_softmax as fsm

OUT = os.path.join(ROOT, 'sim', 'vectors', 'av')
TOK = 99
D = 64
N_WORD = TOK * (D // 4)     # 1584


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % v for v in values) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), 'r', encoding='utf-8') as f:
        doc = json.load(f)
    m_ctx = int(doc['layers'][0]['m_ctx'])

    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    L = fe.FixedEncoderLayer(params['layers'][0], sc, sc['x'])

    x_f = kn.embed(z['mfcc'][0], params)
    x_q, _ = fe.q_tensor(x_f, stats['x'])
    q = fe.mm_fixed(x_q, L.qw_q, L.m_q)
    k = fe.mm_fixed(x_q, L.qw_k, L.m_k)
    v = fe.mm_fixed(x_q, L.qw_v, L.m_v)

    w = np.zeros((D, 100), np.int64)
    w[:, :TOK] = k.T
    score = fe.mm_act(q, w, L.m_score, out_bits=16)
    p = fsm.softmax_fixed(score[:, :TOK])       # (99,99) uint8

    ctx = fe.mm_act(p, v, L.m_ctx, out_bits=8)  # (99,64) int8

    dump(os.path.join(OUT, 'p.mem'), p.reshape(-1), '%02x')
    dump(os.path.join(OUT, 'v.mem'), np.asarray(v.reshape(-1)) & 0xFF, '%02x')
    dump(os.path.join(OUT, 'm.mem'), [m_ctx & 0xFFFFFFFF], '%08x')

    u = (ctx.astype(np.int32) & 0xFF).astype(np.uint32)
    packed = (u[:, 0::4] | (u[:, 1::4] << 8) | (u[:, 2::4] << 16) | (u[:, 3::4] << 24))
    dump(os.path.join(OUT, 'expect.mem'), packed.reshape(-1), '%08x')

    print('m_ctx=%d' % m_ctx)
    print('p sum per row (mean) %.1f' % p.sum(axis=1).mean())
    print('ctx range [%d, %d]' % (ctx.min(), ctx.max()))
    print('expect words: %d' % N_WORD)


if __name__ == '__main__':
    main()
