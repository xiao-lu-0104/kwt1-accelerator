"""Ablation: start from the float model and enable quantization points one by one.

Goal: find which quantization point destroys accuracy when stacked 12 deep.
"""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe
import fixed_softmax as fsm

QMAX8 = 127


def run(params, mfcc, labels, ref_logits, sc, opts, n=120):
    """opts: dict of enabled quantization switches."""
    preds = []
    for i in range(n):
        # input
        if opts.get('x'):
            x_q, sx = fe.q_tensor(kn.embed(mfcc[i], params), sc['x'] * QMAX8)
            x = x_q.astype(np.float32) * np.float32(sx)
        else:
            x = kn.embed(mfcc[i], params)

        for p in params['layers']:
            if opts.get('w4'):
                qw_q, sw_q, _ = fe.build_wq(p['q_w'], 1.0, 1.0, 4)
                qw_k, sw_k, _ = fe.build_wq(p['k_w'], 1.0, 1.0, 4)
                qw_v, sw_v, _ = fe.build_wq(p['v_w'], 1.0, 1.0, 4)
                qw_o, sw_o, _ = fe.build_wq(p['o_w'], 1.0, 1.0, 4)
                qw_f1, sw_f1, _ = fe.build_wq(p['ff1_w'], 1.0, 1.0, 4)
                qw_f2, sw_f2, _ = fe.build_wq(p['ff2_w'], 1.0, 1.0, 4)
                b_o, b_f1, b_f2 = p['o_b'], p['ff1_b'], p['ff2_b']
            else:
                qw_q, sw_q = np.round(p['q_w'] * 127).astype(np.int64), np.full(64, 1 / 127.0)
                qw_k, sw_k = np.round(p['k_w'] * 127).astype(np.int64), np.full(64, 1 / 127.0)
                qw_v, sw_v = np.round(p['v_w'] * 127).astype(np.int64), np.full(64, 1 / 127.0)
                qw_o, sw_o = np.round(p['o_w'] * 127).astype(np.int64), np.full(64, 1 / 127.0)
                qw_f1, sw_f1 = np.round(p['ff1_w'] * 127).astype(np.int64), np.full(256, 1 / 127.0)
                qw_f2, sw_f2 = np.round(p['ff2_w'] * 127).astype(np.int64), np.full(64, 1 / 127.0)
                b_o, b_f1, b_f2 = p['o_b'], p['ff1_b'], p['ff2_b']

            wq = qw_q * np.float32(sw_q)
            wk = qw_k * np.float32(sw_k)
            wv = qw_v * np.float32(sw_v)
            wo = qw_o * np.float32(sw_o)
            w_f1 = qw_f1 * np.float32(sw_f1)
            w_f2 = qw_f2 * np.float32(sw_f2)

            q = x @ wq
            k = x @ wk
            v = x @ wv
            if opts.get('qkv8'):
                q = np.round(q / np.float32(sc['q'])) * np.float32(sc['q'])
                k = np.round(k / np.float32(sc['k'])) * np.float32(sc['k'])
                v = np.round(v / np.float32(sc['v'])) * np.float32(sc['v'])
            s = (q @ k.T) / np.sqrt(np.float32(64))
            if opts.get('score16'):
                s = np.round(s / np.float32(sc['score'])) * np.float32(sc['score'])
            if opts.get('prob8'):
                s_i = np.round(s / np.float32(sc['score'])).astype(np.int32)
                w = fsm.softmax_fixed(s_i).astype(np.float32) / np.float32(127)
            else:
                w = kn.softmax(s)
            ctx = w @ v
            if opts.get('ctx8'):
                ctx = np.round(ctx / np.float32(sc['ctx'])) * np.float32(sc['ctx'])
            o = ctx @ wo + b_o
            if opts.get('o8'):
                o = np.round(o / np.float32(sc['o'])) * np.float32(sc['o'])
            x1 = kn.layer_norm(x + o, p['ln1_g'], p['ln1_b'])
            if opts.get('ln8'):
                x1 = np.round(x1 / np.float32(sc['ln1'])) * np.float32(sc['ln1'])
            h = kn.gelu(x1 @ w_f1 + b_f1)
            if opts.get('h8'):
                h = np.round(h / np.float32(sc['h'])) * np.float32(sc['h'])
            f = h @ w_f2 + b_f2
            if opts.get('f8'):
                f = np.round(f / np.float32(sc['f'])) * np.float32(sc['f'])
            x = kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b'])
            if opts.get('out8'):
                x = np.round(x / np.float32(sc['out'])) * np.float32(sc['out'])
        logits = x[0] @ params['head_w'] + params['head_b']
        preds.append(int(np.argmax(logits)))
    preds = np.array(preds)
    acc = float((preds == labels[:n]).mean())
    agree = float((preds == ref_logits[:n].argmax(axis=1)).mean())
    return acc, agree


def main():
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    mfcc, labels, ref_logits = z['mfcc'], z['label'], z['logits']
    stats = fe.calibrate(params, mfcc, 40)
    sc = fe.make_scales(stats)

    configs = [
        ('float', {}),
        ('x8', {'x': 1}),
        ('w4 only', {'w4': 1}),
        ('x8+w4', {'x': 1, 'w4': 1}),
        ('x8+w4+qkv8', {'x': 1, 'w4': 1, 'qkv8': 1}),
        ('+score16', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1}),
        ('+prob8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1}),
        ('+ctx8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1}),
        ('+o8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1, 'o8': 1}),
        ('+ln8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1, 'o8': 1, 'ln8': 1}),
        ('+h8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1, 'o8': 1,
                 'ln8': 1, 'h8': 1}),
        ('+f8', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1, 'o8': 1,
                 'ln8': 1, 'h8': 1, 'f8': 1}),
        ('all', {'x': 1, 'w4': 1, 'qkv8': 1, 'score16': 1, 'prob8': 1, 'ctx8': 1, 'o8': 1,
                 'ln8': 1, 'h8': 1, 'f8': 1, 'out8': 1}),
    ]

    print('%-14s %8s %8s' % ('config', 'acc', 'agree'))
    for name, opts in configs:
        acc, agree = run(params, mfcc, labels, ref_logits, sc, opts)
        print('%-14s %7.2f%% %7.2f%%' % (name, acc * 100, agree * 100))


if __name__ == '__main__':
    main()
