"""Vectors for rtl/kwt_top.v -- one full KWT-1 inference."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe
import fixed_top as ft

OUT = os.path.join(ROOT, 'sim', 'vectors', 'top')
TOK, D, FF, NL, TP = 99, 64, 256, 12, 98
TACT, PACT = TOK * D, TP * D
QMAX8 = 127
MASK = {'%02x': 0xFF, '%x': 0xF, '%04x': 0xFFFF, '%08x': 0xFFFFFFFF}


def dump(path, values, fmt):
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(fmt % (int(v) & MASK[fmt]) for v in values) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    mfcc = z['mfcc'][0]

    stats = fe.calibrate(params, z['mfcc'], 40)
    sc = fe.make_scales(stats)
    stats['mfcc'] = float(np.abs(z['mfcc'][:60]).max())
    sc['logit'] = float(np.abs(z['logits'][:60]).max() / QMAX8)
    layers = ft.build_all(params, sc, stats)

    # ---- activations and expected results for NSAMP samples ----
    NSAMP = 3
    s_mfcc = np.float32(stats['mfcc'] / QMAX8)
    mf_all, exp_pred, exp_logit = [], [], []
    for si in range(NSAMP):
        sm = z['mfcc'][si]
        mq = np.clip(np.round(sm / s_mfcc), -QMAX8, QMAX8).astype(np.int32)
        full = np.zeros((TP, D), np.int32)
        full[:, :40] = mq
        mf_all.append(full.reshape(-1))
        pr, lg, _ = ft.top_forward(sm, params, sc, stats, layers, return_logits=True)
        exp_pred.append(pr)
        exp_logit.append(lg)
        print('  sample %d: pred=%d logits=%s' % (si, pr, lg))

    # ---- patch projection weights (64x64, rows 40..63 zero) ----
    qw_p, sw_p, m_p = fe.build_wq(params['patch_proj_w'], s_mfcc, sc['x'], wb=4)
    bq_p = ft.build_bias(params['patch_proj_b'], sw_p, s_mfcc)
    pw = np.zeros((D, D), np.int64)
    pw[:, :40] = qw_p.T                       # pw[out, in]

    # ---- class token + positional embedding ----
    pos_q = np.clip(np.round(params['pos_emb'] / np.float32(sc['x'])), -QMAX8, QMAX8).astype(np.int32)
    cls_q = np.clip(np.round(params['class_emb'] / np.float32(sc['x'])), -QMAX8, QMAX8).astype(np.int32)
    cp = np.empty((TOK, D), np.int32)
    cp[0] = np.clip(cls_q + pos_q[0], -QMAX8, QMAX8)
    cp[1:] = pos_q[1:]

    # ---- head weights (16x64, columns 12..15 zero) ----
    qw_h, sw_h, m_h = fe.build_wq(params['head_w'], sc['out'], sc['logit'], wb=4)
    bq_h = ft.build_bias(params['head_b'], sw_h, sc['out'])
    hw = np.zeros((16, D), np.int64)
    hw[:NL, :] = qw_h.T

    # ---- expected result ----
    pred, logit_q, x_q = ft.top_forward(mfcc, params, sc, stats, layers, return_logits=True)
    dump(os.path.join(OUT, 'mfcc.mem'), np.concatenate(mf_all), '%02x')
    dump(os.path.join(OUT, 'pp_wgt.mem'), pw.reshape(-1), '%x')
    dump(os.path.join(OUT, 'pp_m.mem'), np.asarray(m_p), '%08x')
    dump(os.path.join(OUT, 'pp_b.mem'), np.asarray(bq_p), '%08x')
    dump(os.path.join(OUT, 'cp.mem'), cp.reshape(-1), '%02x')
    dump(os.path.join(OUT, 'hd_wgt.mem'), hw.reshape(-1), '%x')
    m_h_full = np.zeros(16, np.int64); m_h_full[:NL] = np.asarray(m_h)
    b_h_full = np.zeros(16, np.int64); b_h_full[:NL] = np.asarray(bq_h)
    dump(os.path.join(OUT, 'hd_m.mem'), m_h_full, '%08x')
    dump(os.path.join(OUT, 'hd_b.mem'), b_h_full, '%08x')
    dump(os.path.join(OUT, 'expect.mem'), exp_pred, '%08x')
    dump(os.path.join(OUT, 'expect_x.mem'), x_q.reshape(-1), '%02x')

    print('s_mfcc=%.6f s_logit=%.6f' % (s_mfcc, sc['logit']))
    print('pred=%d logits=%s' % (pred, logit_q))


if __name__ == '__main__':
    main()
