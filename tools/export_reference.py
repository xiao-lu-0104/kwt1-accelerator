"""Export float reference tensors from the official KWT-1 model.

Produces, for a set of Speech Commands V2 samples:
  mfcc      (B, 98, 40)   - output of the official SpeechFeatures layer
  x_in      (B, 99, 64)   - encoder input after patch_proj + class token + pos_emb
  x_out_i   (B, 99, 64)   - output of encoder layer i (i = 0..11)
  logits    (B, 12)       - classification head output
  label     (B,)          - ground truth index

Usage:
  python tools/export_reference.py --split validation --count 600
"""
import argparse
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
from kws_streaming.data import input_data  # noqa: E402


def build_reference_model(model):
    """Re-create the KWSTransformer call path with intermediate outputs exposed."""
    kwt = None
    head = None
    feats = None
    for layer in model.layers:
        name = layer.name
        if name.startswith('kws_transformer'):
            kwt = layer
        elif name.startswith('speech_features'):
            feats = layer
        elif name.startswith('sequential'):
            head = layer
    if kwt is None or feats is None or head is None:
        raise RuntimeError('unexpected model layout: %s' % [l.name for l in model.layers])

    inp = model.input
    f = feats(inp)
    x = kwt.patch_proj(f)
    b = tf.shape(x)[0]
    cls = tf.broadcast_to(kwt.class_emb, [b, 1, kwt.d_model])
    x = tf.concat([cls, x], axis=1) + kwt.pos_emb
    outs = [f, x]
    for blk in kwt.enc_layers:
        x, _ = blk(x, training=False)
        outs.append(x)
    logits = head(x[:, 0])
    outs.append(logits)
    return tf.keras.Model(inputs=inp, outputs=outs), f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', default='validation', choices=['training', 'validation', 'testing'])
    ap.add_argument('--count', type=int, default=600)
    ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    flags = km.load_flags(
        os.path.join(ROOT, 'external', 'keyword-transformer', 'models_data_v2_12_labels',
                     'kwt1', 'flags.json'),
        data_dir=os.path.join(ROOT, 'data', 'speech_commands_v0.02'),
        train_dir=os.path.join(ROOT, 'external', 'keyword-transformer', 'models_data_v2_12_labels', 'kwt1'),
        batch_size=None,
    )

    sess = tf1.Session()
    tf1.keras.backend.set_session(sess)

    model = km.load_model(flags)
    ref_model = build_reference_model(model)[0]

    ap_proc = input_data.AudioProcessor(flags)
    total = ap_proc.set_size(args.split)
    n = args.count if args.count > 0 else total
    n = max(0, min(n, total - args.offset))
    print('split=%s total=%d exporting=%d offset=%d' % (args.split, total, n, args.offset))

    data, labels = ap_proc.get_data(
        n, args.offset, flags, 0.0, 0.0, 0, args.split, 0.0, 0.0, sess)

    outs = ref_model.predict(data, batch_size=100)
    mfcc = outs[0]
    x_tensors = outs[1:-1]
    logits = outs[-1]

    os.makedirs(os.path.join(ROOT, 'models', 'ref'), exist_ok=True)
    out_path = args.out or os.path.join(
        ROOT, 'models', 'ref', 'ref_%s_%d_%d.npz' % (args.split, args.offset, n))
    np.savez_compressed(
        out_path,
        mfcc=mfcc.astype(np.float32),
        x_in=x_tensors[0].astype(np.float32),
        **{'x_out_%d' % i: t.astype(np.float32) for i, t in enumerate(x_tensors[1:])},
        logits=logits.astype(np.float32),
        label=labels.astype(np.int32),
        audio=data.astype(np.float32),
    )

    pred = np.argmax(logits, axis=1)
    acc = float((pred == labels).mean())
    print('saved %s' % out_path)
    print('accuracy on exported subset: %.4f' % acc)
    with open(out_path.replace('.npz', '_meta.json'), 'w', encoding='utf-8') as fh:
        json.dump({'split': args.split, 'offset': args.offset, 'count': n,
                   'total': total, 'accuracy': acc}, fh, indent=2)


if __name__ == '__main__':
    main()
