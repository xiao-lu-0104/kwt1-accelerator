"""Step through forward_quant to find where it collapses."""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn  # noqa: E402
import quant_experiment as qe  # noqa: E402

z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_0_200.npz'))
mfcc = z['mfcc'][:20]
params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
scales = qe.collect_scales(mfcc, params)
params_q = qe.quantize_params(params, 8, True, None)
bits = 8

qa = lambda x, name: qe.quant_act(x, scales[name], bits)


def show(tag, a, ref=None):
    if ref is None:
        print('%-12s min=%9.4f max=%9.4f absmean=%.4f' % (tag, a.min(), a.max(), np.abs(a).mean()))
    else:
        rel = np.sqrt(np.mean((a - ref) ** 2)) / (np.sqrt(np.mean(ref ** 2)) + 1e-12)
        print('%-12s min=%9.4f max=%9.4f absmean=%.4f  rel=%.3e' % (
            tag, a.min(), a.max(), np.abs(a).mean(), rel))


x_f = kn.embed(mfcc[0], params)
x = qa(kn.embed(mfcc[0], params_q), 'x')
show('x float', x_f)
show('x quant', x, x_f)

p_f = params['layers'][0]
p = params_q['layers'][0]

q_f = x_f @ p_f['q_w']
q = qa(x @ p['q_w'], 'q')
show('q', q, q_f)

k = qa(x @ p['k_w'], 'k')
v = qa(x @ p['v_w'], 'v')
w_f = kn.softmax((q_f @ (x_f @ p_f['k_w']).T) / np.sqrt(np.float32(64)))
w = qa(kn.softmax((q @ k.T) / np.sqrt(np.float32(64))), 'attn_w')
show('attn_w', w, w_f)
print('  attn_w quant unique levels:', len(np.unique(w)))

ctx_f = w_f @ (x_f @ p_f['v_w'])
ctx = qa(w @ v, 'attn_ctx')
show('ctx', ctx, ctx_f)

proj_f = ctx_f @ p_f['o_w'] + p_f['o_b']
proj = qa(ctx @ p['o_w'] + p['o_b'], 'attn_proj')
show('proj', proj, proj_f)

x1_f = kn.layer_norm(x_f + proj_f, p_f['ln1_g'], p_f['ln1_b'])
x1 = qa(kn.layer_norm(x + proj, p['ln1_g'], p['ln1_b']), 'ln1')
show('ln1', x1, x1_f)

h_f = kn.gelu(x1_f @ p_f['ff1_w'] + p_f['ff1_b'])
h = qa(kn.gelu(x1 @ p['ff1_w'] + p['ff1_b']), 'gelu')
show('gelu', h, h_f)

f_f = h_f @ p_f['ff2_w'] + p_f['ff2_b']
f = qa(h @ p['ff2_w'] + p['ff2_b'], 'ff2')
show('ff2', f, f_f)

out_f = kn.layer_norm(x1_f + f_f, p_f['ln2_g'], p_f['ln2_b'])
out = qa(kn.layer_norm(x1 + f, p['ln2_g'], p['ln2_b']), 'out')
show('out', out, out_f)

print('\nscales:', {k: float(v) for k, v in scales.items()})
