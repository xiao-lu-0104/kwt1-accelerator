"""Run calibration and persist every scale / multiplier the RTL needs.

Output: models/quant/scales.json
  - tensor scales
  - per-layer per-channel weight scales and Q1.31 multipliers
  - GELU LUT, exp LUT
  - LayerNorm gamma/beta in Q8 / output domain
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
import fixed_softmax as fsm

OUT_DIR = os.path.join(ROOT, 'models', 'quant')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))

    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)

    layers = []
    s_in = sc['x']
    for i, p in enumerate(params['layers']):
        qw_q, sw_q, m_q = fe.build_wq(p['q_w'], s_in, sc['q'], 4)
        qw_k, sw_k, m_k = fe.build_wq(p['k_w'], s_in, sc['k'], 4)
        qw_v, sw_v, m_v = fe.build_wq(p['v_w'], s_in, sc['v'], 4)
        qw_o, sw_o, m_o = fe.build_wq(p['o_w'], sc['ctx'], sc['o'], 4)
        qw_f1, sw_f1, m_f1 = fe.build_wq(p['ff1_w'], sc['ln1'], sc['hin'], 4)
        qw_f2, sw_f2, m_f2 = fe.build_wq(p['ff2_w'], sc['h'], sc['f'], 4)

        bq_o = np.round(p['o_b'] / (np.float32(sc['ctx']) * sw_o)).astype(np.int64)
        bq_f1 = np.round(p['ff1_b'] / (np.float32(sc['ln1']) * sw_f1)).astype(np.int64)
        bq_f2 = np.round(p['ff2_b'] / (np.float32(sc['h']) * sw_f2)).astype(np.int64)

        m_score = int(round(float((sc['q'] * sc['k'] / 8.0) / sc['score']) * (1 << 31)))
        m_ctx = int(round(float((sc['p'] * sc['v']) / sc['ctx']) * (1 << 31)))

        # LayerNorm constants: gamma_q = gamma * s_r * 256 / s_out, beta_q = beta / s_out
        s_r1 = min(sc['x'], sc['o'])
        s_r2 = min(sc['ln1'], sc['f'])
        g1 = np.round(p['ln1_g'].astype(np.float64) / sc['ln1'] * 256.0).astype(np.int64)
        b1 = np.round(p['ln1_b'].astype(np.float64) / sc['ln1']).astype(np.int64)
        g2 = np.round(p['ln2_g'].astype(np.float64) / sc['out'] * 256.0).astype(np.int64)
        b2 = np.round(p['ln2_b'].astype(np.float64) / sc['out']).astype(np.int64)

        # residual alignment multipliers (Q10)
        ma1 = int(round(s_in / s_r1 * 1024))
        mb1 = int(round(sc['o'] / s_r1 * 1024))
        ma2 = int(round(sc['ln1'] / s_r2 * 1024))
        mb2 = int(round(sc['f'] / s_r2 * 1024))

        layers.append({
            'index': i,
            's_in': float(s_in),
            'q': {'w_scale': sw_q.tolist(), 'm_int': m_q.tolist()},
            'k': {'w_scale': sw_k.tolist(), 'm_int': m_k.tolist()},
            'v': {'w_scale': sw_v.tolist(), 'm_int': m_v.tolist()},
            'o': {'w_scale': sw_o.tolist(), 'm_int': m_o.tolist(), 'bias_q': bq_o.tolist()},
            'ff1': {'w_scale': sw_f1.tolist(), 'm_int': m_f1.tolist(), 'bias_q': bq_f1.tolist()},
            'ff2': {'w_scale': sw_f2.tolist(), 'm_int': m_f2.tolist(), 'bias_q': bq_f2.tolist()},
            'm_score': m_score,
            'm_ctx': m_ctx,
            's_r1': float(s_r1),
            's_r2': float(s_r2),
            'ln1': {'gamma_q': g1.tolist(), 'beta_q': b1.tolist()},
            'ln2': {'gamma_q': g2.tolist(), 'beta_q': b2.tolist()},
            'align1': {'ma': ma1, 'mb': mb1},
            'align2': {'ma': ma2, 'mb': mb2},
        })
        s_in = sc['out']

    # GELU LUT: index = hin + 127, value in s_h domain
    gelu_lut = []
    for i in range(256):
        x_real = (i - 127) * sc['hin']
        g = 0.5 * x_real * (1.0 + __import__('scipy.special', fromlist=['erf']).erf(x_real / np.sqrt(2.0)))
        gelu_lut.append(int(np.clip(round(g / sc['h']), -127, 127)))

    doc = {
        'scales': {k: float(v) for k, v in sc.items()},
        'stats_absmax': {k: float(v) for k, v in stats.items()},
        'layers': layers,
        'gelu_lut': gelu_lut,
        'exp_lut': [int(v) for v in fsm.LUT],
        'ln_eps_q': float(1e-6 / (min(sc['x'], sc['o']) ** 2)),
    }

    path = os.path.join(OUT_DIR, 'scales.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)

    print('wrote', path)
    print('size %.1f KB' % (os.path.getsize(path) / 1024))
    print('scales:', {k: round(v, 6) for k, v in doc['scales'].items()})
    print('layer0 m_score=%d m_ctx=%d align1=%s' % (
        layers[0]['m_score'], layers[0]['m_ctx'], layers[0]['align1']))


if __name__ == '__main__':
    main()
