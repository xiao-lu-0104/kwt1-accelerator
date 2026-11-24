"""Vectors for rtl/kwt_encoder_layer.v (layer 0, sample 0)."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe

OUT = os.path.join(ROOT, 'sim', 'vectors', 'enc')
TOK, D, FF = 99, 64, 256
TACT = TOK * D
HACT = TOK * FF


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % (int(v) & MASK[fmt]) for v in values) + '\n')


MASK = {'%02x': 0xFF, '%x': 0xF, '%04x': 0xFFFF, '%08x': 0xFFFFFFFF}


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    with open(os.path.join(ROOT, 'models', 'quant', 'scales.json'), encoding='utf-8') as f:
        doc = json.load(f)
    lay = doc['layers'][0]

    p = params['layers'][0]
    L = fe.FixedEncoderLayer(p, sc, sc['x'])
    x_f = kn.embed(z['mfcc'][0], params)
    x_q, _ = fe.q_tensor(x_f, stats['x'])
    expect = L.forward(x_q)

    dump(os.path.join(OUT, 'x.mem'), np.asarray(x_q.reshape(-1)), '%02x')
    for name, qw in (('q', L.qw_q), ('k', L.qw_k), ('v', L.qw_v), ('o', L.qw_o),
                     ('f1', L.qw_f1), ('f2', L.qw_f2)):
        dump(os.path.join(OUT, '%s_wgt.mem' % name),
             np.asarray(qw.T.reshape(-1)), '%x')
    for name, m, bq in (('q', L.m_q, None), ('k', L.m_k, None), ('v', L.m_v, None),
                        ('o', L.m_o, L.bq_o), ('f1', L.m_f1, L.bq_f1),
                        ('f2', L.m_f2, L.bq_f2)):
        dump(os.path.join(OUT, '%s_m.mem' % name), np.asarray(m), '%08x')
        if bq is not None:
            dump(os.path.join(OUT, '%s_b.mem' % name), np.asarray(bq), '%08x')
    for name, g, b in (('ln1', lay['ln1']['gamma_q'], lay['ln1']['beta_q']),
                       ('ln2', lay['ln2']['gamma_q'], lay['ln2']['beta_q'])):
        dump(os.path.join(OUT, '%s_g.mem' % name), np.asarray(g), '%04x')
        dump(os.path.join(OUT, '%s_b.mem' % name), np.asarray(b), '%04x')

    eps_q = int(round(doc['ln_eps_q']))
    dump(os.path.join(OUT, 'params.mem'),
         [lay['m_score'], lay['m_ctx'],
          lay['align1']['ma'], lay['align1']['mb'],
          lay['align2']['ma'], lay['align2']['mb'], eps_q], '%08x')
    dump(os.path.join(OUT, 'expect.mem'), np.asarray(expect.reshape(-1)), '%02x')

    print('eps_q=%d m_score=%d m_ctx=%d a1=%s a2=%s' % (
        eps_q, lay['m_score'], lay['m_ctx'], lay['align1'], lay['align2']))
    print('out range [%d, %d]' % (expect.min(), expect.max()))


if __name__ == '__main__':
    main()
