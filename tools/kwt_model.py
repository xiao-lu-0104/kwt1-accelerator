"""Build the official KWT-1 model with the official TF checkpoint.

The official repo targets TF 2.4; this module provides the small
compatibility shims needed for TF 2.15 without editing the repo.
"""
import json
import os
import sys
import types

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
REPO = os.path.join(ROOT, 'external', 'keyword-transformer')

if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import tfa_shim  # noqa: E402

tfa_shim.install()

import tensorflow as tf  # noqa: E402

if not hasattr(tf.keras.layers, 'experimental'):
    exp = types.ModuleType('tensorflow.keras.layers.experimental')
    prep = types.ModuleType('tensorflow.keras.layers.experimental.preprocessing')
    prep.Rescaling = tf.keras.layers.Rescaling
    exp.preprocessing = prep
    sys.modules['tensorflow.keras.layers.experimental'] = exp
    sys.modules['tensorflow.keras.layers.experimental.preprocessing'] = prep
    tf.keras.layers.experimental = exp

from kws_streaming.models import models as kws_models  # noqa: E402
from kws_streaming.models import model_flags  # noqa: E402
from kws_streaming.train import base_parser  # noqa: E402
import kws_streaming.models.kws_transformer as kws_transformer  # noqa: E402


def load_flags(flags_json_path, data_dir=None, train_dir=None, batch_size=1):
    with open(flags_json_path, 'r', encoding='utf-8') as f:
        d = json.load(f)

    args = []
    skip = {'verbosity', 'data_url'}  # verbosity expects a name, data_url is empty in the dump
    for k, v in d.items():
        if v is None or k in skip:
            continue
        if isinstance(v, bool):
            v = int(v)
        args += ['--%s' % k, str(v)]

    parser = base_parser.base_parser()
    kws_transformer.model_parameters(parser)
    flags, _ = parser.parse_known_args(args)

    flags.train = 0
    flags.training = False
    flags.batch_size = batch_size
    flags.model_name = 'kws_transformer'
    if data_dir:
        flags.data_dir = data_dir
    if train_dir:
        flags.train_dir = train_dir

    return model_flags.update_flags(flags)


def build_model(flags):
    model = kws_models.MODELS[flags.model_name](flags)
    # Build the graph with a dummy batch so weights are created.
    dummy = tf.zeros([1, flags.desired_samples], dtype=tf.float32)
    _ = model(dummy, training=False)
    return model


def load_model(flags, weights_name='best_weights'):
    model = build_model(flags)
    path = os.path.join(flags.train_dir, weights_name)
    status = model.load_weights(path)
    status.expect_partial()
    return model


def dump_variables(model, out_path):
    rows = []
    for v in model.weights:
        name = v.name
        rows.append('%s\t%s\t%s' % (name, list(v.shape), v.dtype.name))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows))
    return rows


if __name__ == '__main__':
    ROOT = os.path.dirname(THIS_DIR)
    flags = load_flags(
        os.path.join(REPO, 'models_data_v2_12_labels', 'kwt1', 'flags.json'),
        data_dir=os.path.join(ROOT, 'data', 'speech_commands_v0.02'),
        train_dir=os.path.join(REPO, 'models_data_v2_12_labels', 'kwt1'),
        batch_size=1,
    )
    model = load_model(flags)
    print('model built, params:', model.count_params())
    rows = dump_variables(model, os.path.join(ROOT, 'models', 'kwt1_variables.txt'))
    for r in rows:
        print(r)
