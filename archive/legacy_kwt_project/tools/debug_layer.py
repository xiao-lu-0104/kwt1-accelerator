"""Compare one encoder block step by step between TF and NumPy."""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_model as km  # noqa: E402
import kwt_numpy as kn  # noqa: E402
import tensorflow as tf  # noqa: E402
import tensorflow.compat.v1 as tf1  # noqa: E402

flags = km.load_flags(
    os.path.join(ROOT, 'external', 'keyword-transformer', 'models_data_v2_12_labels',
                 'kwt1', 'flags.json'),
    data_dir=os.path.join(ROOT, 'data', 'speech_commands_v0.02'),
    train_dir=os.path.join(ROOT, 'external', 'keyword-transformer',
                           'models_data_v2_12_labels', 'kwt1'),
    batch_size=None,
)
sess = tf1.Session()
tf1.keras.backend.set_session(sess)
model = km.load_model(flags)
kwt = [l for l in model.layers if l.name.startswith('kws_transformer')][0]
blk = kwt.enc_layers[0]

z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_0_200.npz'))
x0 = z['x_in'][0]                      # (99,64) encoder input
ref0 = z['x_out_0'][0]                 # (99,64) block 0 output
params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
p = params['layers'][0]


def rel(a, b):
    return np.sqrt(np.mean((a - b) ** 2)) / (np.sqrt(np.mean(b ** 2)) + 1e-12)


# ---- TF path ----
xt = tf.constant(x0[None], dtype=tf.float32)
attn_t, w_t = blk.att(xt)
out1_t = blk.layernorm1(xt + attn_t)
ffn_t = blk.ffn(out1_t)
out2_t = blk.layernorm2(out1_t + ffn_t)
attn_t, w_t, out1_t, ffn_t, out2_t = sess.run([attn_t, w_t, out1_t, ffn_t, out2_t])
attn_t, w_t, out1_t, ffn_t, out2_t = [
    a[0] for a in (attn_t, w_t, out1_t, ffn_t, out2_t)]

# ---- NumPy path ----
attn_n, w_n = kn.mha(x0, p['q_w'], p['k_w'], p['v_w'], p['o_w'], p['o_b'])
out1_n = kn.layer_norm(x0 + attn_n, p['ln1_g'], p['ln1_b'])
ffn_n = kn.gelu(out1_n @ p['ff1_w'] + p['ff1_b']) @ p['ff2_w'] + p['ff2_b']
out2_n = kn.layer_norm(out1_n + ffn_n, p['ln2_g'], p['ln2_b'])

print('attention weights  rel=%.3e  max=%.3e' % (rel(w_n, w_t), np.abs(w_n - w_t).max()))
print('attn output        rel=%.3e  max=%.3e' % (rel(attn_n, attn_t), np.abs(attn_n - attn_t).max()))
print('out1 (LN1)         rel=%.3e  max=%.3e' % (rel(out1_n, out1_t), np.abs(out1_n - out1_t).max()))
print('ffn output         rel=%.3e  max=%.3e' % (rel(ffn_n, ffn_t), np.abs(ffn_n - ffn_t).max()))
print('out2 (LN2)         rel=%.3e  max=%.3e' % (rel(out2_n, out2_t), np.abs(out2_n - out2_t).max()))
print('out2 vs ref        rel=%.3e' % rel(out2_n, ref0))
print('out2_tf vs ref     rel=%.3e' % rel(out2_t, ref0))

# isolate pieces of attention
q = x0 @ p['q_w']
k = x0 @ p['k_w']
v = x0 @ p['v_w']
q_t, k_t, v_t = sess.run([blk.att.query_dense(xt), blk.att.key_dense(xt),
                          blk.att.value_dense(xt)])
print('q rel=%.3e  k rel=%.3e  v rel=%.3e' % (
    rel(q, q_t[0]), rel(k, k_t[0]), rel(v, v_t[0])))

score = (q @ k.T) / np.sqrt(64.0)
score_t = sess.run(tf.matmul(blk.att.query_dense(xt), blk.att.key_dense(xt), transpose_b=True))[0] / np.sqrt(64.0)
print('score rel=%.3e' % rel(score, score_t))

# check parameter shapes
print('q_w shape', p['q_w'].shape, 'ff1_w', p['ff1_w'].shape, 'ln1_g', p['ln1_g'].shape)

# ---- FFN internals ----
h_t = blk.ffn.layers[0](out1_t[None])[0]
g_t = blk.ffn.layers[1](h_t[None])[0]
f_t = blk.ffn.layers[2](g_t[None])[0]
h_t, g_t, f_t = sess.run([h_t, g_t, f_t])

h_n = out1_t @ p['ff1_w'] + p['ff1_b']
g_n = kn.gelu(h_n)
f_n = g_n @ p['ff2_w'] + p['ff2_b']

print('ff1 out (pre-gelu) rel=%.3e  max=%.3e' % (rel(h_n, h_t), np.abs(h_n - h_t).max()))
print('gelu out           rel=%.3e  max=%.3e' % (rel(g_n, g_t), np.abs(g_n - g_t).max()))
print('ff2 out            rel=%.3e  max=%.3e' % (rel(f_n, f_t), np.abs(f_n - f_t).max()))

# what if tfa GELU is approximate?
g_appr = 0.5 * h_n * (1 + np.tanh(np.sqrt(2 / np.pi) * (h_n + 0.044715 * h_n ** 3)))
print('gelu approx vs tf  rel=%.3e' % rel(g_appr, g_t))

w_ff1 = sess.run(blk.ffn.layers[0].kernel)
b_ff1 = sess.run(blk.ffn.layers[0].bias)
print('ff1 kernel match:', np.allclose(w_ff1, p['ff1_w'], atol=0), 'bias match:',
      np.allclose(b_ff1, p['ff1_b'], atol=0))
print('ff1 bias tf[:6]', b_ff1[:6])
print('ff1 bias np[:6]', p['ff1_b'][:6])
