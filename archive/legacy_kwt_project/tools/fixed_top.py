"""Fully integer KWT-1 inference: MFCC -> patch_proj -> 12 layers -> head.

Bit-exact with the RTL datapath. Used to verify that the front-end
(patch projection + positional embedding) and the classifier head can be
done in the same integer arithmetic as the encoder.
"""
import numpy as np

import kwt_numpy as kn
import fixed_encoder as fe

QMAX8 = 127


def build_bias(b, sw, s_in, wb=4):
    """Bias in the accumulator domain (same convention as fixed_encoder)."""
    return np.round(b / (np.float32(s_in) * sw)).astype(np.int64)


def top_forward(mfcc, params, sc, stats, layers, return_logits=False):
    """One sample, integer only."""
    s_mfcc = np.float32(stats['mfcc'] / QMAX8)
    mfcc_q = np.clip(np.round(mfcc / s_mfcc), -QMAX8, QMAX8).astype(np.int32)

    # ---- patch projection (40 -> 64), int4 weights, int8 activations ----
    qw_p, sw_p, m_p = fe.build_wq(params['patch_proj_w'], s_mfcc, sc['x'], wb=4)
    bq_p = build_bias(params['patch_proj_b'], sw_p, s_mfcc)
    pq = fe.mm_fixed(mfcc_q, qw_p, m_p, bq_p)          # (98, 64), scale s_x

    # ---- class token + positional embedding, both pre-quantised to s_x ----
    pos_q = np.clip(np.round(params['pos_emb'] / np.float32(sc['x'])), -QMAX8, QMAX8).astype(np.int32)
    cls_q = np.clip(np.round(params['class_emb'] / np.float32(sc['x'])), -QMAX8, QMAX8).astype(np.int32)

    x_q = np.empty((99, 64), np.int32)
    x_q[0] = np.clip(cls_q + pos_q[0], -QMAX8, QMAX8)
    x_q[1:] = np.clip(pq + pos_q[1:], -QMAX8, QMAX8)

    # ---- 12 encoder layers ----
    for L in layers:
        x_q = L.forward(x_q)

    # ---- classifier head on the class token ----
    qw_h, sw_h, m_h = fe.build_wq(params['head_w'], sc['out'], sc['logit'], wb=4)
    bq_h = build_bias(params['head_b'], sw_h, sc['out'])
    logit_q = fe.mm_fixed(x_q[0:1], qw_h, m_h, bq_h)   # (1, 12)

    if return_logits:
        return int(np.argmax(logit_q[0])), logit_q[0], x_q
    return int(np.argmax(logit_q[0]))


def build_all(params, sc, stats):
    layers, s_in = [], sc['x']
    for p in params['layers']:
        layers.append(fe.FixedEncoderLayer(p, sc, s_in))
        s_in = sc['out']
    return layers


if __name__ == '__main__':
    import os
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    mfcc, labels, ref_logits = z['mfcc'], z['label'], z['logits']

    stats = fe.calibrate(params, mfcc, 40)
    sc = fe.make_scales(stats)
    stats['mfcc'] = float(np.abs(mfcc[:60]).max())
    sc['logit'] = float(np.abs(ref_logits[:60]).max() / QMAX8)

    layers = build_all(params, sc, stats)

    n = 600
    preds = np.empty(n, np.int64)
    for i in range(n):
        preds[i] = top_forward(mfcc[i], params, sc, stats, layers)

    acc_ref = float((ref_logits[:n].argmax(axis=1) == labels[:n]).mean())
    acc_int = float((preds == labels[:n]).mean())
    agree = float((preds == ref_logits[:n].argmax(axis=1)).mean())
    print('s_mfcc=%.6f  s_logit=%.6f' % (stats['mfcc'] / QMAX8, sc['logit']))
    print('float acc=%.4f  int acc=%.4f  drop=%.2f pp  agreement=%.4f'
          % (acc_ref, acc_int, (acc_ref - acc_int) * 100, agree))
