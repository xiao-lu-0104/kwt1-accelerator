"""Step-by-step comparison of the fixed-point layer vs float."""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn
import fixed_encoder as fe
import fixed_softmax as fsm


def rel(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    return np.sqrt(np.mean((a - b) ** 2)) / (np.sqrt(np.mean(b ** 2)) + 1e-12)


params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
mfcc = z['mfcc']

stats = fe.calibrate(params, mfcc, 40)
sc = fe.make_scales(stats)
L = fe.FixedEncoderLayer(params['layers'][0], sc)
p = params['layers'][0]

x_f = kn.embed(mfcc[0], params)
x_q, _ = fe.q_tensor(x_f, stats['x'])

# ---- float reference ----
q_f = x_f @ p['q_w']
k_f = x_f @ p['k_w']
v_f = x_f @ p['v_w']
s_f = (q_f @ k_f.T) / np.sqrt(np.float32(64))
w_f = kn.softmax(s_f)
ctx_f = w_f @ v_f
o_f = ctx_f @ p['o_w'] + p['o_b']
r1_f = x_f + o_f
x1_f = kn.layer_norm(r1_f, p['ln1_g'], p['ln1_b'])
hin_f = x1_f @ p['ff1_w'] + p['ff1_b']
h_f = kn.gelu(hin_f)
f_f = h_f @ p['ff2_w'] + p['ff2_b']
r2_f = x1_f + f_f
out_f = kn.layer_norm(r2_f, p['ln2_g'], p['ln2_b'])

# ---- fixed path ----
q = fe.mm_fixed(x_q, L.qw_q, L.m_q) * np.float32(sc['q'])
k = fe.mm_fixed(x_q, L.qw_k, L.m_k) * np.float32(sc['k'])
v = fe.mm_fixed(x_q, L.qw_v, L.m_v) * np.float32(sc['v'])
print('q   rel=%.3e' % rel(q, q_f))
print('  q_f[0,0:6]', np.round(q_f[0, :6], 4))
print('  q  [0,0:6]', np.round(q[0, :6], 4))
print('  sc_q=%.5f sw_q[0:3]=%s m_q[0:3]=%s' % (
    sc['q'], np.round(L.sw_q[:3], 5), L.m_q[:3]))
print('k   rel=%.3e' % rel(k, k_f))
print('v   rel=%.3e' % rel(v, v_f))

score_i = fe.mm_act(fe.mm_fixed(x_q, L.qw_q, L.m_q), fe.mm_fixed(x_q, L.qw_k, L.m_k).T,
                    L.m_score, out_bits=16)
score = score_i * np.float32(sc['score'])
print('score rel=%.3e  (absmax fixed %.2f float %.2f)' % (
    rel(score, s_f), np.abs(score).max(), np.abs(s_f).max()))

prob = fsm.softmax_fixed(score_i) / np.float32(127)
print('prob  rel=%.3e  (sum fixed %.1f)' % (rel(prob, w_f), fsm.softmax_fixed(score_i).sum(axis=1).mean()))

ctx_i = fe.mm_act(fsm.softmax_fixed(score_i), fe.mm_fixed(x_q, L.qw_v, L.m_v), L.m_ctx, 8)
ctx = ctx_i * np.float32(sc['ctx'])
print('ctx   rel=%.3e' % rel(ctx, ctx_f))

o = fe.mm_fixed(ctx_i, L.qw_o, L.m_o, L.bq_o) * np.float32(sc['o'])
print('o     rel=%.3e' % rel(o, o_f))

r1_i, s_r1 = fe.align_add(x_q, sc['x'], fe.mm_fixed(ctx_i, L.qw_o, L.m_o, L.bq_o), sc['o'])
r1 = r1_i * np.float32(s_r1)
print('r1    rel=%.3e  (absmax fixed %.2f float %.2f, s_r1 %.5f)' % (
    rel(r1, r1_f), np.abs(r1).max(), np.abs(r1_f).max(), s_r1))

x1 = fe.layernorm_q(r1_i, s_r1, p['ln1_g'], p['ln1_b'], sc['ln1']) * np.float32(sc['ln1'])
print('ln1   rel=%.3e' % rel(x1, x1_f))

hin_i = fe.mm_fixed(fe.layernorm_q(r1_i, s_r1, p['ln1_g'], p['ln1_b'], sc['ln1']),
                    L.qw_f1, L.m_f1, L.bq_f1)
hin = hin_i * np.float32(sc['hin'])
print('hin   rel=%.3e  (absmax fixed %.2f float %.2f)' % (
    rel(hin, hin_f), np.abs(hin).max(), np.abs(hin_f).max()))

h_q = np.clip(np.round(fe.gelu_float(hin) / np.float32(sc['h'])), -127, 127).astype(np.int32)
h = h_q * np.float32(sc['h'])
print('h     rel=%.3e' % rel(h, h_f))

f_i = fe.mm_fixed(h_q, L.qw_f2, L.m_f2, L.bq_f2)
f = f_i * np.float32(sc['f'])
print('f     rel=%.3e' % rel(f, f_f))

r2_i, s_r2 = fe.align_add(fe.layernorm_q(r1_i, s_r1, p['ln1_g'], p['ln1_b'], sc['ln1']),
                          sc['ln1'], f_i, sc['f'])
r2 = r2_i * np.float32(s_r2)
print('r2    rel=%.3e' % rel(r2, r2_f))

out = fe.layernorm_q(r2_i, s_r2, p['ln2_g'], p['ln2_b'], sc['out']) * np.float32(sc['out'])
print('out   rel=%.3e' % rel(out, out_f))
