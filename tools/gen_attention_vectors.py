"""Vectors for rtl/kwt_attention.v using real layer-0 weights and sample 0."""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe
import fixed_softmax as fsm

OUT = os.path.join(ROOT, 'sim', 'vectors', 'attn')
TOK = 99
D = 64
TACT = TOK * D
N_WORD = TOK * (D // 4)


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % v for v in values) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    p = params['layers'][0]
    L = fe.FixedEncoderLayer(p, sc, sc['x'])

    x_f = kn.embed(z['mfcc'][0], params)
    x_q, _ = fe.q_tensor(x_f, stats['x'])

    q = fe.mm_fixed(x_q, L.qw_q, L.m_q)
    k = fe.mm_fixed(x_q, L.qw_k, L.m_k)
    v = fe.mm_fixed(x_q, L.qw_v, L.m_v)
    w = np.zeros((D, 100), np.int64)
    w[:, :TOK] = k.T
    score = fe.mm_act(q, w, L.m_score, out_bits=16)
    pr = fsm.softmax_fixed(score[:, :TOK])
    ctx = fe.mm_act(pr, v, L.m_ctx, out_bits=8)
    o = fe.mm_fixed(ctx, L.qw_o, L.m_o, L.bq_o)

    dump(os.path.join(OUT, 'x.mem'), np.asarray(x_q.reshape(-1)) & 0xFF, '%02x')
    for name, qw, m, bq in (
            ('q', L.qw_q, L.m_q, np.zeros(D, np.int64)),
            ('k', L.qw_k, L.m_k, np.zeros(D, np.int64)),
            ('v', L.qw_v, L.m_v, np.zeros(D, np.int64)),
            ('o', L.qw_o, L.m_o, L.bq_o)):
        dump(os.path.join(OUT, '%s_wgt.mem' % name),
             np.asarray(qw.T.reshape(-1)) & 0xF, '%x')
        dump(os.path.join(OUT, '%s_m.mem' % name), (m & 0xFFFFFFFF), '%08x')
        dump(os.path.join(OUT, '%s_b.mem' % name), (bq & 0xFFFFFFFF), '%08x')

    u = (o.astype(np.int32) & 0xFF).astype(np.uint32)
    packed = (u[:, 0::4] | (u[:, 1::4] << 8) | (u[:, 2::4] << 16) | (u[:, 3::4] << 24))
    dump(os.path.join(OUT, 'expect.mem'), packed.reshape(-1), '%08x')
    dump(os.path.join(OUT, 'score_m.mem'), [L.m_score & 0xFFFFFFFF], '%08x')
    dump(os.path.join(OUT, 'ctx_m.mem'), [L.m_ctx & 0xFFFFFFFF], '%08x')

    print('o range [%d, %d]' % (o.min(), o.max()))
    print('expect words: %d' % N_WORD)


if __name__ == '__main__':
    main()
