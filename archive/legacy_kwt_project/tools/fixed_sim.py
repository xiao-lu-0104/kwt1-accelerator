"""Bit-exact fixed-point model.

Every arithmetic rule here mirrors rtl/ exactly:
  - int4 weight, symmetric, per-output-channel scale, range [-7, 7]
  - int8 activation, symmetric, per-tensor scale, range [-127, 127]
  - int32 accumulation (Python int is arbitrary precision, values stay in range)
  - requant: sat8((acc * m_int + 2^30) >>> 31), m_int is Q1.31
  - bias pre-scaled by 1/(Sx*Sw[c])

Do not change the rounding/saturation semantics without changing the RTL.
"""
import numpy as np

QMAX_W4 = 7
QMAX_A8 = 127
FRAC_BITS = 31
ROUND = 1 << (FRAC_BITS - 1)


def sat8(v):
    if v > QMAX_A8:
        return QMAX_A8
    if v < -QMAX_A8:
        return -QMAX_A8
    return int(v)


def requant_i32_to_i8(acc, m_int):
    """Must match rtl/kwt_requant.v exactly."""
    prod = int(acc) * int(m_int)
    shifted = (prod + ROUND) >> FRAC_BITS
    return sat8(shifted)


def quant_weight_per_channel(w):
    """w: (in, out) float -> (int4 codes (in, out), scale per out channel)."""
    am = np.abs(w).max(axis=0)
    s = np.where(am > 0, am / QMAX_W4, 1.0).astype(np.float32)
    q = np.clip(np.round(w / s), -QMAX_W4, QMAX_W4).astype(np.int32)
    return q, s


def quant_act_per_tensor(x, absmax):
    s = np.float32(absmax / QMAX_A8) if absmax > 0 else np.float32(1.0)
    q = np.clip(np.round(x / s), -QMAX_A8, QMAX_A8).astype(np.int32)
    return q, s


class FixedLinear:
    """y[token, c] = sat8(((x[token] . qw[:, c]) + bq[c]) * m_int[c] >> 31)."""

    def __init__(self, w, b, sx, sy):
        self.qw, self.sw = quant_weight_per_channel(w)      # (in, out), (out,)
        self.in_dim, self.out_dim = self.qw.shape
        self.sx = np.float32(sx)
        self.sy = np.float32(sy)
        denom = self.sx * self.sw
        self.bq = np.round(b / denom).astype(np.int64)
        m = denom / self.sy
        self.m_int = np.round(m * float(1 << FRAC_BITS)).astype(np.int64)
        bad = np.where((self.m_int < -(1 << 31)) | (self.m_int > (1 << 31) - 1))[0]
        if bad.size:
            raise ValueError('m_int out of int32 range at channels %s' % bad[:8])

    def __call__(self, x_q):
        """x_q: (T, in) int values -> (T, out) int8. Vectorized, same semantics."""
        t_n = x_q.shape[0]
        qw = self.qw.astype(np.int64)
        out = np.empty((t_n, self.out_dim), np.int8)
        for t in range(t_n):
            acc = x_q[t].astype(np.int64) @ qw + self.bq
            prod = acc * self.m_int
            shifted = (prod + ROUND) >> FRAC_BITS
            shifted = np.clip(shifted, -QMAX_A8, QMAX_A8)
            out[t] = shifted.astype(np.int8)
        return out

    def ref_float(self, x_q):
        """Real-valued product for sanity checks (not used by RTL comparison)."""
        return (x_q.astype(np.float32) * self.sx) @ (self.qw * self.sw).astype(np.float32) \
            + self.bq.astype(np.float32) * (self.sx * self.sw).astype(np.float32)
