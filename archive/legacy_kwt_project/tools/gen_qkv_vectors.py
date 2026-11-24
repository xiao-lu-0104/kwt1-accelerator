"""Vectors for rtl/kwt_attn_qkv.v using real layer-0 weights and sample 0."""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe

OUT = os.path.join(ROOT, 'sim', 'vectors', 'qkv')
TOK = 99
D = 64
GROUPS = D // 4
N_WORD = TOK * GROUPS


def pack4(a):
    """(99,64) int8 -> (99,16) uint32, 4 channels per word."""
    u = (a.astype(np.int32) & 0xFF).astype(np.uint32)
    return (u[:, 0::4] | (u[:, 1::4] << 8) | (u[:, 2::4] << 16) | (u[:, 3::4] << 24))


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
    x_q, sx = fe.q_tensor(x_f, stats['x'])
    assert abs(float(sx) - L.s_in) < 1e-5

    q = fe.mm_fixed(x_q, L.qw_q, L.m_q)
    k = fe.mm_fixed(x_q, L.qw_k, L.m_k)
    v = fe.mm_fixed(x_q, L.qw_v, L.m_v)

    dump(os.path.join(OUT, 'x.mem'), np.asarray(x_q.reshape(-1)) & 0xFF, '%02x')
    for name, qw, m in (('q', L.qw_q, L.m_q), ('k', L.qw_k, L.m_k), ('v', L.qw_v, L.m_v)):
        dump(os.path.join(OUT, '%s_wgt.mem' % name),
             np.asarray(qw.T.reshape(-1)) & 0xF, '%x')
        dump(os.path.join(OUT, '%s_bias.mem' % name), np.zeros(D, np.int64) & 0xFFFFFFFF, '%08x')
        dump(os.path.join(OUT, '%s_m.mem' % name), (m & 0xFFFFFFFF), '%08x')

    for name, arr in (('q', q), ('k', k), ('v', v)):
        dump(os.path.join(OUT, '%s_expect.mem' % name), pack4(arr).reshape(-1), '%08x')

    print('x_q range [%d, %d]' % (x_q.min(), x_q.max()))
    print('q range [%d, %d]  k [%d, %d]  v [%d, %d]' % (
        q.min(), q.max(), k.min(), k.max(), v.min(), v.max()))
    print('expect words per projection: %d' % N_WORD)


if __name__ == '__main__':
    main()
