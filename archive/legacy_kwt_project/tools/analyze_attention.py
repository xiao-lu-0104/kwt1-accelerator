"""Analyze real attention score / probability distributions.

Drives the fixed-point softmax design: score int16 scale, LUT index mapping,
and the achievable probability accuracy.
"""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn  # noqa: E402


def main():
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    x_in = z['x_in']          # (600, 99, 64)

    scores = []
    probs = []
    for i in range(0, 20):    # 20 samples is plenty for a range estimate
        x = x_in[i]
        for li, p in enumerate(params['layers']):
            q = x @ p['q_w']
            k = x @ p['k_w']
            s = (q @ k.T) / np.sqrt(np.float32(64))
            scores.append(s.reshape(-1))
            w = kn.softmax(s)
            probs.append(w.reshape(-1))
            attn, _ = kn.mha(x, p['q_w'], p['k_w'], p['v_w'], p['o_w'], p['o_b'])
            x1 = kn.layer_norm(x + attn, p['ln1_g'], p['ln1_b'])
            h = kn.gelu(x1 @ p['ff1_w'] + p['ff1_b'])
            f = h @ p['ff2_w'] + p['ff2_b']
            x = kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b'])

    s = np.concatenate(scores)
    w = np.concatenate(probs)
    print('score  absmax=%.3f  p99.9=%.3f  std=%.3f' % (
        np.abs(s).max(), np.percentile(np.abs(s), 99.9), s.std()))
    print('score  min=%.3f max=%.3f' % (s.min(), s.max()))

    # per-row delta range (s - max)
    dmax = []
    for i in range(0, 20):
        x = x_in[i]
        for p in params['layers']:
            q = x @ p['q_w']
            k = x @ p['k_w']
            srow = (q @ k.T) / np.sqrt(np.float32(64))
            dmax.append((srow.max(axis=1) - srow).reshape(-1))
            attn, _ = kn.mha(x, p['q_w'], p['k_w'], p['v_w'], p['o_w'], p['o_b'])
            x1 = kn.layer_norm(x + attn, p['ln1_g'], p['ln1_b'])
            h = kn.gelu(x1 @ p['ff1_w'] + p['ff1_b'])
            f = h @ p['ff2_w'] + p['ff2_b']
            x = kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b'])
    d = np.concatenate(dmax)
    print('delta  absmax=%.3f  p99=%.3f  p99.9=%.3f' % (
        d.max(), np.percentile(d, 99), np.percentile(d, 99.9)))

    print('prob   min=%.3e max=%.3f  mean=%.5f' % (w.min(), w.max(), w.mean()))
    print('prob   p50=%.5f p99=%.4f' % (np.percentile(w, 50), np.percentile(w, 99)))
    print('fraction of probs < 1/255 = %.3f' % (w < 1.0 / 255).mean())
    print('fraction of probs < 1/127 = %.3f' % (w < 1.0 / 127).mean())


if __name__ == '__main__':
    main()
