"""Quantization experiments v2: per-tap calibrated scales.

Every tensor that would live in SRAM gets its own scale. Residual adds are
simulated as "quantize each operand, add in float, requantize" which is the
optimistic bound for an RTL that can align scales before adding.
"""
import argparse
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn  # noqa: E402

TAPS = ['x', 'q', 'k', 'v', 'attn_w', 'attn_ctx', 'attn_proj',
        'ln1', 'gelu', 'ff2', 'out']


def qmax_of(bits):
    return 2 ** (bits - 1) - 1


def quant_weight(w, bits=8, per_channel=True, group=None):
    qm = qmax_of(bits)
    if w.ndim == 1:
        am = np.abs(w).max()
        s = am / qm if am > 0 else 1.0
        return np.clip(np.round(w / s), -qm, qm) * s, np.float32(s)
    if group:
        out = np.empty_like(w)
        for c in range(w.shape[1]):
            for g in range(0, w.shape[0], group):
                blk = w[g:g + group, c]
                am = np.abs(blk).max()
                s = am / qm if am > 0 else 1.0
                out[g:g + group, c] = np.clip(np.round(blk / s), -qm, qm) * s
        return out, None
    if per_channel:
        am = np.abs(w).max(axis=0)
        s = np.where(am > 0, am / qm, 1.0).astype(np.float32)
        return np.clip(np.round(w / s), -qm, qm) * s, s
    am = np.abs(w).max()
    s = np.float32(am / qm if am > 0 else 1.0)
    return np.clip(np.round(w / s), -qm, qm) * s, s


def quant_act(x, absmax, bits=8):
    """Symmetric per-tensor fake quantization. absmax is the calibrated range."""
    qm = qmax_of(bits)
    if bits >= 32 or absmax <= 0:
        return x
    scale = absmax / qm
    return np.clip(np.round(x / scale), -qm, qm) * scale


def quantize_params(params, bits=8, per_channel=True, group=None):
    out = {k: params[k] for k in ('pos_emb', 'class_emb', 'patch_proj_b', 'head_b')}
    q = lambda w: quant_weight(w, bits, per_channel, group)[0]
    out['patch_proj_w'] = q(params['patch_proj_w'])
    out['head_w'] = q(params['head_w'])
    out['layers'] = []
    for p in params['layers']:
        d = dict(p)
        for k in ('q_w', 'k_w', 'v_w', 'o_w', 'ff1_w', 'ff2_w'):
            d[k] = q(p[k])
        out['layers'].append(d)
    return out


def rec(taps, name, v):
    taps.setdefault(name, []).append(v.reshape(-1))


def forward_tapped(mfcc, params, taps):
    x = kn.embed(mfcc, params)
    rec(taps, 'x', x)
    for p in params['layers']:
        q = x @ p['q_w']
        k = x @ p['k_w']
        v = x @ p['v_w']
        rec(taps, 'q', q)
        rec(taps, 'k', k)
        rec(taps, 'v', v)
        w = kn.softmax((q @ k.T) / np.sqrt(np.float32(64)))
        rec(taps, 'attn_w', w)
        ctx = w @ v
        rec(taps, 'attn_ctx', ctx)
        proj = ctx @ p['o_w'] + p['o_b']
        rec(taps, 'attn_proj', proj)
        x1 = kn.layer_norm(x + proj, p['ln1_g'], p['ln1_b'])
        rec(taps, 'ln1', x1)
        h = kn.gelu(x1 @ p['ff1_w'] + p['ff1_b'])
        rec(taps, 'gelu', h)
        f = h @ p['ff2_w'] + p['ff2_b']
        rec(taps, 'ff2', f)
        x = kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b'])
        rec(taps, 'out', x)
    rec(taps, 'logits', x[0] @ params['head_w'] + params['head_b'])
    return taps


def collect_scales(mfcc_batch, params, pct=100.0):
    taps = {}
    for i in range(mfcc_batch.shape[0]):
        forward_tapped(mfcc_batch[i], params, taps)
    scales = {}
    for k, vals in taps.items():
        a = np.abs(np.concatenate(vals))
        scales[k] = np.float32(np.percentile(a, pct) if pct < 100 else a.max())
    return scales


def forward_quant(mfcc, params, s, bits_a=8, bits_attn=16):
    qa = lambda x, name, b=bits_a: quant_act(x, s[name], b)
    x = qa(kn.embed(mfcc, params), 'x')
    for p in params['layers']:
        q = qa(x @ p['q_w'], 'q')
        k = qa(x @ p['k_w'], 'k')
        v = qa(x @ p['v_w'], 'v')
        w = qa(kn.softmax((q @ k.T) / np.sqrt(np.float32(64))), 'attn_w', bits_attn)
        ctx = qa(w @ v, 'attn_ctx')
        proj = qa(ctx @ p['o_w'] + p['o_b'], 'attn_proj')
        x1 = qa(kn.layer_norm(x + proj, p['ln1_g'], p['ln1_b']), 'ln1')
        h = qa(kn.gelu(x1 @ p['ff1_w'] + p['ff1_b']), 'gelu')
        f = qa(h @ p['ff2_w'] + p['ff2_b'], 'ff2')
        x = qa(kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b']), 'out')
    return x[0] @ params['head_w'] + params['head_b']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', default=None)
    ap.add_argument('--bits-w', type=int, default=8)
    ap.add_argument('--bits-a', type=int, default=8)
    ap.add_argument('--per-channel', type=int, default=1)
    ap.add_argument('--group', type=int, default=0)
    ap.add_argument('--pct', type=float, default=100.0)
    ap.add_argument('--bits-attn', type=int, default=16)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--tag', default=None)
    args = ap.parse_args()

    npz = args.ref or os.path.join(ROOT, 'models', 'ref', 'ref_validation_0_200.npz')
    z = np.load(npz)
    mfcc, labels, logits_ref = z['mfcc'], z['label'], z['logits']
    if args.limit:
        mfcc, labels, logits_ref = mfcc[:args.limit], labels[:args.limit], logits_ref[:args.limit]

    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    scales = collect_scales(mfcc, params, args.pct)
    print('calibrated absmax (pct=%.1f):' % args.pct)
    for k in TAPS + ['logits']:
        print('  %-10s %.4f' % (k, scales[k]))

    params_q = quantize_params(params, args.bits_w, bool(args.per_channel),
                               args.group or None)

    preds_ref = logits_ref.argmax(axis=1)
    logits_q = np.stack([forward_quant(mfcc[i], params_q, scales, args.bits_a, args.bits_attn)
                         for i in range(mfcc.shape[0])])

    acc_ref = float((preds_ref == labels).mean())
    acc_q = float((logits_q.argmax(axis=1) == labels).mean())
    agree = float((logits_q.argmax(axis=1) == preds_ref).mean())
    rel = float(np.sqrt(np.mean((logits_q - logits_ref) ** 2)) /
                (np.sqrt(np.mean(logits_ref ** 2)) + 1e-12))

    tag = args.tag or 'w%d%s_a%d%s_a%d' % (
        args.bits_w, 'pc' if args.per_channel else 'pt', args.bits_a,
        '_g%d' % args.group if args.group else '', args.bits_attn)
    print('\n%s' % tag)
    print('acc_ref=%.4f acc_quant=%.4f  drop=%.2f pp  agreement=%.4f  logit_rel=%.2e'
          % (acc_ref, acc_q, (acc_ref - acc_q) * 100, agree, rel))

    out = {'tag': tag, 'bits_w': args.bits_w, 'bits_a': args.bits_a,
           'bits_attn': args.bits_attn,
           'per_channel': bool(args.per_channel), 'group': args.group, 'pct': args.pct,
           'acc_ref': acc_ref, 'acc_quant': acc_q, 'drop_pp': (acc_ref - acc_q) * 100,
           'agreement': agree, 'logit_rel': rel,
           'scales': {k: float(v) for k, v in scales.items()}}
    os.makedirs(os.path.join(ROOT, 'models', 'quant'), exist_ok=True)
    with open(os.path.join(ROOT, 'models', 'quant', 'result_%s.json' % tag), 'w') as f:
        json.dump(out, f, indent=2)
    print('saved models/quant/result_%s.json' % tag)


if __name__ == '__main__':
    main()
