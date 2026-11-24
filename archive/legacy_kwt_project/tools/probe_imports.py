import sys, os, types
ROOT = r'e:\chipdesign'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'external', 'keyword-transformer'))

import tfa_shim
tfa_shim.install()

import tensorflow as tf
print('TF', tf.__version__)

# TF>=2.9 moved Rescaling out of experimental; the official repo still uses the old path.
try:
    from tensorflow.keras.layers.experimental.preprocessing import Rescaling  # noqa
    print('experimental.preprocessing OK')
except Exception as e:
    print('experimental.preprocessing MISSING:', type(e).__name__, e)
    import tensorflow.keras.layers as kl
    exp = types.ModuleType('tensorflow.keras.layers.experimental')
    prep = types.ModuleType('tensorflow.keras.layers.experimental.preprocessing')
    prep.Rescaling = kl.Rescaling
    exp.preprocessing = prep
    sys.modules['tensorflow.keras.layers.experimental'] = exp
    sys.modules['tensorflow.keras.layers.experimental.preprocessing'] = prep
    tf.keras.layers.experimental = exp
    print('shim installed')

import kws_streaming.models.models as models
print('models import OK, has kwt:', 'kws_transformer' in models.MODELS)
import kws_streaming.models.model_flags as model_flags
print('model_flags OK')
