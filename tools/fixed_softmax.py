"""Bit-exact fixed-point softmax, mirroring rtl/kwt_softmax.v."""
import numpy as np

LUT_SIZE = 256
LUT = np.array([max(0, min(32767, int(round(np.exp(-i / 16.0) * 32767))))
                for i in range(LUT_SIZE)], dtype=np.int64)


def softmax_fixed(s_int16):
    """s_int16: (..., N) integer scores -> uint8 probabilities (0..127)."""
    s = np.asarray(s_int16, dtype=np.int64)
    mx = s.max(axis=-1, keepdims=True)
    delta = mx - s
    idx = np.minimum(LUT_SIZE - 1, delta >> 4)
    e = LUT[idx]
    total = e.sum(axis=-1, keepdims=True)
    safe = np.where(total == 0, 1, total)
    inv = (127 << 20) // safe
    p = (e * inv + (1 << 19)) >> 20
    p = np.minimum(p, 127)
    p = np.where(total == 0, 0, p)
    return p.astype(np.uint8)


def dequant(p_uint8):
    """Probability real value if the hardware scale is 1/127."""
    return p_uint8.astype(np.float32) / np.float32(127.0)
