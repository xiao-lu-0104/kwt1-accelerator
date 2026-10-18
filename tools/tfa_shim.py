"""Minimal local stand-in for tensorflow_addons.

The official KWT repo imports `tensorflow_addons as tfa` only for
`tfa.layers.GELU(approximate=...)`. tensorflow-addons has no Windows
wheel compatible with TF 2.15, so we provide the same layer semantics
here. This does not modify the official source tree.

GELU exact:   0.5 * x * (1 + erf(x / sqrt(2)))
GELU approx:  0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
"""
import tensorflow as tf


class _GELU(tf.keras.layers.Layer):
    def __init__(self, approximate=False, **kwargs):
        super().__init__(**kwargs)
        self.approximate = approximate

    def call(self, x):
        if self.approximate:
            return 0.5 * x * (
                1.0 + tf.tanh(0.7978845608028654 * (x + 0.044715 * tf.pow(x, 3)))
            )
        return 0.5 * x * (1.0 + tf.math.erf(x / tf.sqrt(2.0)))

    def get_config(self):
        cfg = super().get_config()
        cfg['approximate'] = self.approximate
        return cfg


class _LayersNamespace:
    GELU = _GELU


class _Namespace:
    layers = _LayersNamespace()


def install():
    """Register this module under the name `tensorflow_addons`."""
    import sys
    sys.modules['tensorflow_addons'] = _Namespace()
    sys.modules['tensorflow_addons.layers'] = _LayersNamespace()
