import importlib, sys
for m in ['numpy', 'torch', 'scipy', 'librosa', 'soundfile', 'onnx', 'pandas', 'matplotlib']:
    try:
        mod = importlib.import_module(m)
        print(f'{m:12s} {getattr(mod, "__version__", "?")}')
    except Exception:
        print(f'{m:12s} MISSING')
print('python', sys.version)
try:
    import torch
    print('torch cuda:', torch.cuda.is_available())
except Exception:
    pass
