"""Generate bit-exact test vectors for rtl/kwt_linear.v.

Uses the real layer-0 FFN1 weights and a real validation sample, so the RTL is
checked against the same numbers the chip will actually see.
"""
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn          # noqa: E402
import fixed_sim as fs          # noqa: E402

OUT_DIR = os.path.join(ROOT, 'sim', 'vectors', 'linear')
TOKENS = 99
IN_DIM = 64
OUT_DIM = 256


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))
    w = params['layers'][0]['ff1_w']       # (64, 256)
    b = params['layers'][0]['ff1_b']       # (256,)
    assert w.shape == (IN_DIM, OUT_DIM)

    z = np.load(os.path.join(ROOT, 'models', 'ref', 'ref_validation_600.npz'))
    x_in = z['x_in']                       # (600, 99, 64)
    x_absmax = float(np.abs(x_in).max())
    # output range from the float model, used only to pick a sensible Sy
    ref_out = z['x_out_0']                 # not the FFN output; used for scale guess only

    sx = np.float32(x_absmax / fs.QMAX_A8)
    # quantize activation of sample 0
    x_q, _ = fs.quant_act_per_tensor(x_in[0], x_absmax)

    # choose Sy from the float pre-activation statistics of this layer
    y_float = x_in[0].astype(np.float32) @ w + b
    y_absmax = float(np.abs(y_float).max())
    sy = np.float32(y_absmax / fs.QMAX_A8)

    lin = fs.FixedLinear(w, b, float(sx), float(sy))
    y_q = lin(x_q)

    nz = (y_q != 0).mean()
    print('activation absmax %.4f  sx %.6f' % (x_absmax, sx))
    print('output   absmax %.4f  sy %.6f' % (y_absmax, sy))
    print('quantized output: nonzero %.3f  min %d max %d' % (nz, y_q.min(), y_q.max()))

    # ---- dump memories (one value per line, $readmemh compatible) ----
    def dump(path, values, fmt):
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write('\n'.join(fmt % v for v in values) + '\n')

    dump(os.path.join(OUT_DIR, 'act.mem'), np.asarray(x_q.reshape(-1)) & 0xFF, '%02x')
    # RTL expects wgt_buf[out_ch*IN_DIM + i], i.e. output-channel major
    dump(os.path.join(OUT_DIR, 'wgt.mem'), np.asarray(lin.qw.T.reshape(-1)) & 0xF, '%x')
    dump(os.path.join(OUT_DIR, 'bias.mem'), (lin.bq & 0xFFFFFFFF), '%08x')
    dump(os.path.join(OUT_DIR, 'm.mem'), (lin.m_int & 0xFFFFFFFF), '%08x')

    yy = (y_q.astype(np.int32) & 0xFF).astype(np.uint32)
    packed = (yy[:, 0::4]
              | (yy[:, 1::4] << 8)
              | (yy[:, 2::4] << 16)
              | (yy[:, 3::4] << 24))
    dump(os.path.join(OUT_DIR, 'expect.mem'), packed.reshape(-1), '%08x')

    print('dumped to %s' % OUT_DIR)
    print('  act.mem     %d lines' % (TOKENS * IN_DIM))
    print('  wgt.mem     %d lines' % (OUT_DIM * IN_DIM))
    print('  bias.mem    %d lines' % OUT_DIM)
    print('  m.mem       %d lines' % OUT_DIM)
    print('  expect.mem  %d lines' % (TOKENS * OUT_DIM // 4))


if __name__ == '__main__':
    main()
