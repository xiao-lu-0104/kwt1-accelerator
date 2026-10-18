"""Pure-NumPy KWT-1 reference implementation.

Mirrors the official TF graph exactly (float32 first), serving as the
ground truth for RTL and as the host for quantization experiments.

Tensor contract (batch = 1 everywhere):
  mfcc    (98, 40)   official SpeechFeatures output
  x       (99, 64)   class token + 98 patches + pos_emb
  block:  attn = LN1(x + MHA(x)); out = LN2(attn + FFN(attn))
"""
import numpy as np
from scipy.special import erf as _scipy_erf

D_MODEL = 64
N_LAYER = 12
N_TOKEN = 99
MLP_DIM = 256
HEAD_DIM = 64
EPS_LN = 1e-6


def gelu(x):
    return 0.5 * x * (1.0 + _erf(x / np.sqrt(2.0)))


def _erf(x):
    return _scipy_erf(x).astype(np.float32)


def layer_norm(x, gamma, beta, eps=EPS_LN):
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps) * gamma + beta


def softmax(x):
    m = x.max(axis=-1, keepdims=True)
    e = np.exp(x - m)
    return e / e.sum(axis=-1, keepdims=True)


def mha(x, q_w, k_w, v_w, o_w, o_b):
    q = x @ q_w
    k = x @ k_w
    v = x @ v_w
    score = (q @ k.T) / np.sqrt(np.float32(HEAD_DIM))
    weights = softmax(score)
    out = weights @ v
    return out @ o_w + o_b, weights


def block(x, p):
    attn, weights = mha(x, p['q_w'], p['k_w'], p['v_w'], p['o_w'], p['o_b'])
    x1 = layer_norm(x + attn, p['ln1_g'], p['ln1_b'])
    h = gelu(x1 @ p['ff1_w'] + p['ff1_b'])
    f = h @ p['ff2_w'] + p['ff2_b']
    out = layer_norm(x1 + f, p['ln2_g'], p['ln2_b'])
    return out, weights


def load_params(npz_path):
    z = np.load(npz_path)
    params = {
        'pos_emb': z['pos_emb'][0].astype(np.float32),
        'class_emb': z['class_emb'][0, 0].astype(np.float32),
        'patch_proj_w': z['patch_proj_w'].astype(np.float32),
        'patch_proj_b': z['patch_proj_b'].astype(np.float32),
        'head_w': z['head_w'].astype(np.float32),
        'head_b': z['head_b'].astype(np.float32),
        'layers': [],
    }
    for i in range(N_LAYER):
        p = 'l%d/' % i
        params['layers'].append({
            k: z[p + k].astype(np.float32)
            for k in ('q_w', 'k_w', 'v_w', 'o_w', 'o_b', 'ff1_w', 'ff1_b',
                      'ff2_w', 'ff2_b', 'ln1_g', 'ln1_b', 'ln2_g', 'ln2_b')
        })
    return params


def embed(mfcc, params):
    x = mfcc @ params['patch_proj_w'] + params['patch_proj_b']
    x = np.concatenate([params['class_emb'][None, :], x], axis=0)
    return x + params['pos_emb']


def forward(mfcc, params, keep_layers=False):
    """mfcc: (98, 40) -> logits (12,)."""
    x = embed(mfcc, params)
    trace = {'x_in': x}
    if keep_layers:
        trace['layers'] = []
    for i, p in enumerate(params['layers']):
        x, _ = block(x, p)
        if keep_layers:
            trace['layers'].append(x)
    logits = x[0] @ params['head_w'] + params['head_b']
    if keep_layers:
        trace['logits'] = logits
        return logits, trace
    return logits


def forward_batch(mfcc_batch, params, keep_layers=False):
    outs = []
    traces = []
    for i in range(mfcc_batch.shape[0]):
        if keep_layers:
            lg, tr = forward(mfcc_batch[i], params, True)
            traces.append(tr)
        else:
            lg = forward(mfcc_batch[i], params)
        outs.append(lg)
    logits = np.stack(outs, axis=0)
    if keep_layers:
        return logits, traces
    return logits
