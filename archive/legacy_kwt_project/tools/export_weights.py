"""Export all KWT-1 weights into a structured .npz and print statistics."""
import json
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_model as km  # noqa: E402
import tensorflow as tf  # noqa: E402
import tensorflow.compat.v1 as tf1  # noqa: E402


def get_kwt(model):
    for layer in model.layers:
        if layer.name.startswith('kws_transformer'):
            return layer
    raise RuntimeError('kws_transformer layer not found')


def main():
    sess = tf1.Session()
    tf1.keras.backend.set_session(sess)

    flags = km.load_flags(
        os.path.join(ROOT, 'external', 'keyword-transformer', 'models_data_v2_12_labels',
                     'kwt1', 'flags.json'),
        data_dir=os.path.join(ROOT, 'data', 'speech_commands_v0.02'),
        train_dir=os.path.join(ROOT, 'external', 'keyword-transformer',
                               'models_data_v2_12_labels', 'kwt1'),
        batch_size=None,
    )
    model = km.load_model(flags)
    kwt = get_kwt(model)
    head = [l for l in model.layers if l.name.startswith('sequential')][0]

    def val(v):
        return sess.run(v)

    out = {}
    stats = []

    def add(name, v):
        arr = np.asarray(v)
        out[name] = arr
        stats.append((name, arr.shape, float(arr.min()), float(arr.max()),
                      float(arr.mean()), float(arr.std())))

    add('pos_emb', val(kwt.pos_emb))
    add('class_emb', val(kwt.class_emb))
    add('patch_proj_w', val(kwt.patch_proj.kernel))
    add('patch_proj_b', val(kwt.patch_proj.bias))
    add('head_w', val(head.layers[0].kernel))
    add('head_b', val(head.layers[0].bias))

    for i, blk in enumerate(kwt.enc_layers):
        p = 'l%d/' % i
        add(p + 'q_w', val(blk.att.query_dense.kernel))
        add(p + 'k_w', val(blk.att.key_dense.kernel))
        add(p + 'v_w', val(blk.att.value_dense.kernel))
        add(p + 'o_w', val(blk.att.combine_heads.kernel))
        add(p + 'o_b', val(blk.att.combine_heads.bias))
        add(p + 'ff1_w', val(blk.ffn.layers[0].kernel))
        add(p + 'ff1_b', val(blk.ffn.layers[0].bias))
        add(p + 'ff2_w', val(blk.ffn.layers[2].kernel))
        add(p + 'ff2_b', val(blk.ffn.layers[2].bias))
        add(p + 'ln1_g', val(blk.layernorm1.gamma))
        add(p + 'ln1_b', val(blk.layernorm1.beta))
        add(p + 'ln2_g', val(blk.layernorm2.gamma))
        add(p + 'ln2_b', val(blk.layernorm2.beta))

    os.makedirs(os.path.join(ROOT, 'models'), exist_ok=True)
    path = os.path.join(ROOT, 'models', 'kwt1_weights.npz')
    np.savez_compressed(path, **out)

    total = sum(a.size for a in out.values())
    print('saved', path)
    print('tensors=%d  elements=%d' % (len(out), total))
    print('%-18s %-14s %9s %9s %9s %9s' % ('name', 'shape', 'min', 'max', 'mean', 'std'))
    for name, shape, mn, mx, mean, std in stats:
        print('%-18s %-14s %9.4f %9.4f %9.4f %9.4f' % (name, str(shape), mn, mx, mean, std))

    # aggregate per-kernel statistics (for per-channel quantization planning)
    print('\nper-tensor absmax summary:')
    groups = {}
    for name, shape, mn, mx, mean, std in stats:
        key = name.split('/')[-1]
        groups.setdefault(key, []).append(max(abs(mn), abs(mx)))
    for k, v in groups.items():
        print('  %-10s absmax: min=%.4f  max=%.4f  mean=%.4f' % (k, min(v), max(v), sum(v) / len(v)))


if __name__ == '__main__':
    main()
