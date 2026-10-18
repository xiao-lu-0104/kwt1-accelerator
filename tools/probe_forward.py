import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_model as km  # noqa: E402
import tensorflow as tf  # noqa: E402
import tensorflow.compat.v1 as tf1  # noqa: E402

from export_reference import build_reference_model  # noqa: E402

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
ref = build_reference_model(model)[0]

rng = np.random.RandomState(0)
audio = rng.randn(2, flags.desired_samples).astype(np.float32) * 0.1
outs = ref.predict(audio, batch_size=2)
print('num outputs:', len(outs))
for i, o in enumerate(outs):
    print(i, o.shape, 'finite:', np.isfinite(o).all(),
          'min %.4f max %.4f' % (o.min(), o.max()))
