"""Fixed-point encoder model (12 layers), used to validate accuracy and to
serve as the golden model for RTL.

Quantization points (all static, per-tensor unless noted):
  x      int8   block input
  qkv    int8   Q/K/V projection output (per-tensor, so QK^T has one scale)
  score  int16  QK^T output, scale 1/256
  p      uint8  softmax probability, scale 1/127
  ctx    int8   attention context
  o      int8   output projection
  r1/r2  int16  residual domain
  ln1/ln2 int8  LayerNorm output
  h      int8   GELU output
  f      int8   FFN2 output
  out    int8   block output

matmul is bit-exact integer; LN/GELU are quantize-in / float-compute /
quantize-out, which bounds the error a fixed-point implementation can achieve.
"""
import numpy as np
from scipy.special import erf

import fixed_softmax as fsm
import kwt_numpy as kn

QMAX8 = 127
QMAX16 = 32767
N_TOK = 99
D = 64
MLP = 256

TAP_NAMES = ['x', 'q', 'k', 'v', 'score', 'p', 'ctx', 'o', 'r1', 'ln1', 'hin', 'h', 'f', 'r2', 'out']


def sat8(v):
    return np.clip(v, -QMAX8, QMAX8)


def q_tensor(x, absmax, qmax=QMAX8):
    s = np.float32(absmax / qmax) if absmax > 0 else np.float32(1.0)
    q = np.clip(np.round(x / s), -qmax, qmax).astype(np.int32)
    return q, float(s)


ALIGN_FRAC = 10


def align_add(a, sa, b, sb):
    """Add two quantized tensors in a common int16 domain.

    Scale ratios are applied with Q10 fixed-point multipliers (hardware: two
    multipliers + one adder), NOT rounded to integers.
    """
    s = min(sa, sb)
    ma = int(round(sa / s * (1 << ALIGN_FRAC)))
    mb = int(round(sb / s * (1 << ALIGN_FRAC)))
    r = (a.astype(np.int64) * ma + b.astype(np.int64) * mb + (1 << (ALIGN_FRAC - 1))) >> ALIGN_FRAC
    return np.clip(r, -QMAX16, QMAX16).astype(np.int32), s


def build_wq(w, sx, sy, wb=4):
    """Per-channel int weight + bias + Q1.31 multiplier."""
    qmax = (1 << (wb - 1)) - 1
    am = np.abs(w).max(axis=0)
    sw = np.where(am > 0, am / qmax, 1.0).astype(np.float32)
    qw = np.clip(np.round(w / sw), -qmax, qmax).astype(np.int64)
    m = (sx * sw) / np.float32(sy)
    m_int = np.round(m * float(1 << 31)).astype(np.int64)
    return qw, sw, m_int


def mm_fixed(x_q, qw, m_int, bq=None, out_bits=8):
    """Bit-exact with the RTL: acc = x@w + bq; q = sat((acc*m + 2^30)>>31)."""
    acc = x_q.astype(np.int64) @ qw
    if bq is not None:
        acc = acc + bq
    prod = acc * m_int
    shifted = (prod + (1 << 30)) >> 31
    lim = QMAX8 if out_bits == 8 else QMAX16
    return np.clip(shifted, -lim, lim).astype(np.int32)


def mm_act(x_q, w_q, m_int, out_bits=8):
    acc = x_q.astype(np.int64) @ w_q.astype(np.int64)
    prod = acc * m_int
    shifted = (prod + (1 << 30)) >> 31
    lim = QMAX8 if out_bits == 8 else QMAX16
    return np.clip(shifted, -lim, lim).astype(np.int32)


def gelu_float(x):
    return 0.5 * x * (1.0 + erf(x / np.sqrt(2.0)))


def layernorm_q(x_q, s_in, gamma, beta, s_out, eps=1e-6):
    x = x_q.astype(np.float32) * np.float32(s_in)
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    y = (x - mean) / np.sqrt(var + np.float32(eps)) * gamma + beta
    return np.clip(np.round(y / np.float32(s_out)), -QMAX8, QMAX8).astype(np.int32)


# ----------------------------------------------------------------------
# Bit-exact integer LayerNorm, mirroring rtl/kwt_layernorm.v
# ----------------------------------------------------------------------
RSQRT_LUT = [max(1, int(round(65536.0 / np.sqrt((k + 0.5) * 1024)))) for k in range(256)]
LN_EPS_Q = 0


def ln_row_fixed(row, gamma_q, beta_q, eps_q=LN_EPS_Q):
    """One row of LayerNorm in the exact integer form the RTL implements."""
    n = len(row)
    s = int(row.sum())
    mean = (s + n // 2) >> 6
    var = int(((row.astype(np.int64) - mean) ** 2).sum())
    var = (var >> 6) + eps_q
    idx = 255 if (var >> 10) > 255 else (var >> 10)
    inv = RSQRT_LUT[idx]
    for _ in range(3):
        y0sq = (inv * inv) >> 16
        vy = var * y0sq
        t3 = 196608 - vy
        y1 = (inv * t3) >> 17
        inv = y1 if y1 > 0 else 1
    d = row.astype(np.int64) - mean
    y_q8 = (d * inv) >> 8
    g = y_q8 * gamma_q.astype(np.int64)
    o = (g >> 16) + beta_q.astype(np.int64)
    return np.clip(o, -QMAX8, QMAX8).astype(np.int32)


def layernorm_rows(x_q, gamma_q, beta_q, eps_q=LN_EPS_Q):
    return np.stack([ln_row_fixed(r, gamma_q, beta_q, eps_q) for r in x_q])


class FixedEncoderLayer:
    """One PostNorm transformer block with static scales."""

    def __init__(self, p, sc, s_in=None, wb=4):
        self.p = p
        self.sc = sc                      # dict of scales
        self.s_in = float(s_in if s_in is not None else sc['x'])
        sx = self.s_in
        self.qw_q, self.sw_q, self.m_q = build_wq(p['q_w'], sx, sc['q'], wb)
        self.qw_k, self.sw_k, self.m_k = build_wq(p['k_w'], sx, sc['k'], wb)
        self.qw_v, self.sw_v, self.m_v = build_wq(p['v_w'], sx, sc['v'], wb)
        self.qw_o, self.sw_o, self.m_o = build_wq(p['o_w'], sc['ctx'], sc['o'], wb)
        self.qw_f1, self.sw_f1, self.m_f1 = build_wq(p['ff1_w'], sc['ln1'], sc['hin'], wb)
        self.qw_f2, self.sw_f2, self.m_f2 = build_wq(p['ff2_w'], sc['h'], sc['f'], wb)
        # bias for o / ff1 / ff2 (QKV have none)
        self.bq_o = np.round(p['o_b'] / (np.float32(sc['ctx']) * self.sw_o)).astype(np.int64)
        self.bq_f1 = np.round(p['ff1_b'] / (np.float32(sc['ln1']) * self.sw_f1)).astype(np.int64)
        self.bq_f2 = np.round(p['ff2_b'] / (np.float32(sc['h']) * self.sw_f2)).astype(np.int64)
        # activation x activation multipliers
        self.m_score = int(round(float((sc['q'] * sc['k'] / 8.0) / sc['score']) * (1 << 31)))
        self.m_ctx = int(round(float((sc['p'] * sc['v']) / sc['ctx']) * (1 << 31)))
        # integer LayerNorm constants (same formulas as tools/calibrate.py)
        self.g1 = np.round(p['ln1_g'].astype(np.float64) / sc['ln1'] * 256.0).astype(np.int64)
        self.b1 = np.round(p['ln1_b'].astype(np.float64) / sc['ln1']).astype(np.int64)
        self.g2 = np.round(p['ln2_g'].astype(np.float64) / sc['out'] * 256.0).astype(np.int64)
        self.b2 = np.round(p['ln2_b'].astype(np.float64) / sc['out']).astype(np.int64)

    def forward(self, x_q):
        sc = self.sc
        # --- attention ---
        q = mm_fixed(x_q, self.qw_q, self.m_q)
        k = mm_fixed(x_q, self.qw_k, self.m_k)
        v = mm_fixed(x_q, self.qw_v, self.m_v)
        score = mm_act(q, k.T, self.m_score, out_bits=16)
        p = fsm.softmax_fixed(score)                      # uint8 0..127
        ctx = mm_act(p, v, self.m_ctx, out_bits=8)
        o = mm_fixed(ctx, self.qw_o, self.m_o, self.bq_o)
        # --- residual + LN1 ---
        r1, s_r1 = align_add(x_q, self.s_in, o, sc['o'])
        x1 = layernorm_rows(r1, self.g1, self.b1)
        # --- FFN ---
        h = mm_fixed(x1, self.qw_f1, self.m_f1, self.bq_f1)
        h = np.clip(np.round(gelu_float(h.astype(np.float32) * np.float32(sc['hin'])) /
                             np.float32(sc['h'])), -QMAX8, QMAX8).astype(np.int32)
        f = mm_fixed(h, self.qw_f2, self.m_f2, self.bq_f2)
        # --- residual + LN2 ---
        r2, s_r2 = align_add(x1, sc['ln1'], f, sc['f'])
        out = layernorm_rows(r2, self.g2, self.b2)
        return out


def calibrate(params, mfcc_batch, max_samples=40):
    """Collect absmax at every tap using the float model."""
    stats = {k: 0.0 for k in TAP_NAMES}

    def upd(name, arr):
        m = float(np.abs(arr).max())
        if m > stats[name]:
            stats[name] = m

    for i in range(min(max_samples, mfcc_batch.shape[0])):
        x = kn.embed(mfcc_batch[i], params)
        upd('x', x)
        for p in params['layers']:
            q = x @ p['q_w']
            k = x @ p['k_w']
            v = x @ p['v_w']
            upd('q', q)
            upd('k', k)
            upd('v', v)
            s = (q @ k.T) / np.sqrt(np.float32(64))
            upd('score', s)
            w = kn.softmax(s)
            upd('p', w)
            ctx = w @ v
            upd('ctx', ctx)
            o = ctx @ p['o_w'] + p['o_b']
            upd('o', o)
            r1 = x + o
            upd('r1', r1)
            x1 = kn.layer_norm(r1, p['ln1_g'], p['ln1_b'])
            upd('ln1', x1)
            hin = x1 @ p['ff1_w'] + p['ff1_b']
            upd('hin', hin)
            h = kn.gelu(hin)
            upd('h', h)
            f = h @ p['ff2_w'] + p['ff2_b']
            upd('f', f)
            r2 = x1 + f
            upd('r2', r2)
            x = kn.layer_norm(r2, p['ln2_g'], p['ln2_b'])
            upd('out', x)
    return stats


def make_scales(stats, score_scale=1.0 / 256.0, p_scale=1.0 / 127.0):
    sc = {}
    for k in TAP_NAMES:
        if k == 'score':
            sc[k] = score_scale
        elif k == 'p':
            sc[k] = p_scale
        elif k in ('r1', 'r2'):
            sc[k] = stats[k] / QMAX16
        else:
            sc[k] = stats[k] / QMAX8
    sc['r1'] = min(sc['x'], sc['o'])
    sc['r2'] = min(sc['ln1'], sc['f'])
    return sc


if __name__ == '__main__':
    import os
    import sys
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(ROOT, 'tools'))

    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    mfcc = z['mfcc']
    labels = z['label']
    logits_ref = z['logits']

    stats = calibrate(params, mfcc, 40)
    print('calibrated absmax:')
    for k in TAP_NAMES:
        print('  %-6s %.4f' % (k, stats[k]))

    sc = make_scales(stats)
    print('\nscales:')
    for k, v in sc.items():
        print('  %-6s %.6f' % (k, v))

    layers = []
    s_in = sc['x']
    for p in params['layers']:
        layers.append(FixedEncoderLayer(p, sc, s_in))
        s_in = sc['out']

    n = 600
    preds = []
    for i in range(n):
        x_abs = stats['x']
        x_q, _ = q_tensor(kn.embed(mfcc[i], params), x_abs)
        for L in layers:
            x_q = L.forward(x_q)
        logits = (x_q[0].astype(np.float32) * np.float32(sc['out'])) @ params['head_w'] + params['head_b']
        preds.append(int(np.argmax(logits)))
    preds = np.array(preds)

    acc_ref = float((logits_ref[:n].argmax(axis=1) == labels[:n]).mean())
    acc_fix = float((preds == labels[:n]).mean())
    agree = float((preds == logits_ref[:n].argmax(axis=1)).mean())
    print('\nfloat acc=%.4f  fixed acc=%.4f  drop=%.2f pp  agreement=%.4f'
          % (acc_ref, acc_fix, (acc_ref - acc_fix) * 100, agree))
