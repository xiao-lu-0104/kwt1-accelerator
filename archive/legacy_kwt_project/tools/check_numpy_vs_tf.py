"""Verify the NumPy reference against the official TF outputs."""
import glob
import os
import sys

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)

import kwt_numpy as kn  # noqa: E402


def main():
    npz_files = sorted(glob.glob(os.path.join(ROOT, 'models', 'ref', 'ref_*.npz')))
    if not npz_files:
        raise SystemExit('no reference npz found; run tools/export_reference.py first')
    path = npz_files[-1]
    print('using', path)
    z = np.load(path)
    params = kn.load_params(os.path.join(ROOT, 'models', 'kwt1_weights.npz'))

    mfcc = z['mfcc']
    x_in_ref = z['x_in']
    logits_ref = z['logits']
    labels = z['label']

    n = mfcc.shape[0]
    x_in_np = np.stack([kn.embed(mfcc[i], params) for i in range(n)])
    err_in = np.abs(x_in_np - x_in_ref)
    denom = np.sqrt(np.mean(x_in_ref ** 2)) + 1e-12
    print('x_in   max_abs_err=%.3e  norm_rmse=%.3e' % (err_in.max(), np.sqrt(np.mean(err_in ** 2)) / denom))

    # full forward
    x = x_in_np.copy()
    for li in range(kn.N_LAYER):
        ref = z['x_out_%d' % li]
        new_x = np.empty_like(x)
        max_err = 0.0
        num = 0.0
        den = 0.0
        for i in range(n):
            new_x[i], _ = kn.block(x[i], params['layers'][li])
            max_err = max(max_err, np.abs(new_x[i] - ref[i]).max())
            num += np.sum((new_x[i] - ref[i]) ** 2)
            den += np.sum(ref[i] ** 2)
        x = new_x
        print('layer %2d  max_abs_err=%.3e  norm_rmse=%.3e' % (li, max_err, np.sqrt(num / den)))

    preds_ref = logits_ref.argmax(axis=1)
    logits_np = np.stack([
        kn.forward(mfcc[i], params) for i in range(n)])
    err = np.abs(logits_np - logits_ref)
    print('logits max_abs_err=%.3e' % err.max())
    print('TF acc=%.4f  NumPy acc=%.4f  agreement=%.4f' % (
        (preds_ref == labels).mean(),
        (logits_np.argmax(axis=1) == labels).mean(),
        (logits_np.argmax(axis=1) == preds_ref).mean()))


if __name__ == '__main__':
    main()
