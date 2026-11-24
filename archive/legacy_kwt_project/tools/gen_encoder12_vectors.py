"""Vectors for rtl/kwt_encoder_12.v -- all 12 layers of KWT-1.

Flattens every layer's parameters into one ROM image so the hardware
scheduler can switch layers by changing the base index.
"""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe

OUT = os.path.join(ROOT, 'sim', 'vectors', 'enc12')
TOK, D, FF, NL = 99, 64, 256, 12
TACT = TOK * D
NW4, NWF = D * D, D * FF
NBC = 3 * D + D + FF + D   # 576 bias/multiplier words
WROM_LAYER = 4 * NW4 + 2 * NWF   # 49152

MASK = {'%02x': 0xFF, '%x': 0xF, '%04x': 0xFFFF, '%08x': 0xFFFFFFFF}


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % (int(v) & MASK[fmt]) for v in values) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), encoding='utf-8') as f:
        doc = json.load(f)

    layers, wrom, bm, bb, lg, lb, lc = [], [], [], [], [], [], []
    s_in = sc['x']
    for i, p in enumerate(params['layers']):
        L = fe.FixedEncoderLayer(p, sc, s_in)
        layers.append(L)
        for qw in (L.qw_q, L.qw_k, L.qw_v, L.qw_o):
            wrom.extend(np.asarray(qw.T.reshape(-1)))
        for qw in (L.qw_f1, L.qw_f2):
            wrom.extend(np.asarray(qw.T.reshape(-1)))
        bm.extend(np.asarray(L.m_q));  bb.extend([0] * D)
        bm.extend(np.asarray(L.m_k));  bb.extend([0] * D)
        bm.extend(np.asarray(L.m_v));  bb.extend([0] * D)
        bm.extend(np.asarray(L.m_o));  bb.extend(np.asarray(L.bq_o))
        bm.extend(np.asarray(L.m_f1)); bb.extend(np.asarray(L.bq_f1))
        bm.extend(np.asarray(L.m_f2)); bb.extend(np.asarray(L.bq_f2))
        lay = doc['layers'][i]
        lg.extend(lay['ln1']['gamma_q'] + lay['ln2']['gamma_q'])
        lb.extend(lay['ln1']['beta_q'] + lay['ln2']['beta_q'])
        lc.extend([lay['m_score'], lay['m_ctx'],
                   lay['align1']['ma'], lay['align1']['mb'],
                   lay['align2']['ma'], lay['align2']['mb']])
        s_in = sc['out']

    # bias/m layout per layer: QKV(192) + O(64) + FFN1(256) + FFN2(64) = 576
    bm_rom, bb_rom = bm, bb

    x_f = kn.embed(z['mfcc'][0], params)
    x_q, _ = fe.q_tensor(x_f, stats['x'])
    expect = x_q
    for L in layers:
        expect = L.forward(expect)

    dump(os.path.join(OUT, 'wrom.mem'), wrom, '%x')
    dump(os.path.join(OUT, 'brom_m.mem'), bm_rom, '%08x')
    dump(os.path.join(OUT, 'brom_b.mem'), bb_rom, '%08x')
    dump(os.path.join(OUT, 'lnrom_g.mem'), lg, '%04x')
    dump(os.path.join(OUT, 'lnrom_b.mem'), lb, '%04x')
    dump(os.path.join(OUT, 'lconst.mem'), lc, '%08x')
    dump(os.path.join(OUT, 'x.mem'), np.asarray(x_q.reshape(-1)), '%02x')
    dump(os.path.join(OUT, 'expect.mem'), np.asarray(expect.reshape(-1)), '%02x')

    print('wrom %d nibbles, brom %d, lnrom %d, lconst %d' %
          (len(wrom), len(bm_rom), len(lg), len(lc)))
    print('out range [%d, %d]' % (expect.min(), expect.max()))


if __name__ == '__main__':
    main()
