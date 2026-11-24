"""Speech Commands WAV -> frozen FF1 vectors -> RTL/SoC adapter -> results.

No training, calibration or parameter search is performed. prepare/reference are
offline stages and never publish hardware performance. A new System Bus adapter
must be bound after the frontend commit is available.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import types
import wave

PINNED_MODEL = '237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'
HERE = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def git_revision(repo):
    # Offline release snapshots carry a complete tracked-file ledger instead of
    # a Git database. Validate every listed byte before using the recorded ID.
    frozen=Path(repo)/'FrozenSource.json'
    if not (Path(repo)/'.git').exists() and frozen.is_file():
        record=load(frozen)
        for name,digest in record['files_sha256'].items():
            if sha(Path(repo)/name)!=digest:raise ValueError('Offline source changed: '+name)
        return record['source_commit']
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                   universal_newlines=True).strip()


def modules(frontend):
    sys.path.insert(0, str(Path(frontend) / 'Model'))
    import numpy as np
    from Reference import Encoder, Quantize, QuantizeParameters, Linear, Scale
    from Checkpoint import Checkpoint
    return np, Encoder, Quantize, QuantizeParameters, Linear, Scale, Checkpoint


def select(args):
    """Select validation-only smoke samples; official selection is an input."""
    root = args.dataset.resolve()
    lines = (root / 'validation_list.txt').read_text().splitlines()
    wanted = ['yes', 'no', 'up', 'down', 'left', 'right', 'on', 'off', 'stop', 'go']
    chosen = []
    for word in wanted:
        paths = sorted(x for x in lines if x.split('/')[0] == word)
        if not paths:
            raise ValueError('Missing validation class ' + word)
        chosen.append({'path': paths[0], 'label': word, 'split': 'validation'})
    unknown = sorted(x for x in lines if x.split('/')[0] not in wanted
                     and not x.startswith('_background_noise_/'))
    if not unknown:
        raise ValueError('Missing unknown validation audio')
    chosen += [{'path': unknown[0], 'label': '_unknown_', 'split': 'validation'},
               {'silence': True, 'label': '_silence_', 'split': 'validation'}]
    save(args.output, {'purpose': 'local_smoke_only_not_official_selection', 'samples': chosen})
    print('SMOKE_SELECTION_READY', args.output)


def prepare(args):
    np, Encoder, Quantize, QuantizeParameters, Linear, Scale, Checkpoint = modules(args.frontend)
    source = args.frontend.resolve()
    model = args.model.resolve()
    if git_revision(model) != PINNED_MODEL:
        raise ValueError('Use the exact official model commit, not another checkpoint')
    revision = git_revision(source)
    # Fixing an accidental local RTL edit must precede an evaluation freeze.
    if (source/'.git').exists() and subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']).strip():
        raise ValueError('Frontend has tracked modifications; use a clean fixed worktree')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = load(args.samples)
    samples = spec['samples'] if isinstance(spec, dict) else spec
    if not samples:
        raise ValueError('Empty sample list')
    flags_path = model / 'models_data_v2_12_labels/kwt1/flags.json'
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    sys.path.insert(0, str(model))
    from kws_streaming.layers.speech_features import SpeechFeatures
    from kws_streaming.layers.modes import Modes
    flags = types.SimpleNamespace(**load(flags_path))
    feature_model = SpeechFeatures(SpeechFeatures.get_params(flags), mode=Modes.NON_STREAM_INFERENCE)
    def features_of(audio):return feature_model(audio[None, :]).numpy()[0]
    feature_backend='pinned_official_TensorFlow_SpeechFeatures_inference'
    prefix = model / 'models_data_v2_12_labels/kwt1/best_weights'
    reader = Checkpoint(prefix)
    def read(name):
        return reader.Read('layer_with_weights-0/' + name + '/.ATTRIBUTES/VARIABLE_VALUE').astype(np.float64)
    mapping = {
        'QueryWeight': 'att/query_dense/kernel', 'KeyWeight': 'att/key_dense/kernel',
        'ValueWeight': 'att/value_dense/kernel', 'OutputWeight': 'att/combine_heads/kernel',
        'OutputBias': 'att/combine_heads/bias', 'Ff1Weight': 'ffn/layer_with_weights-0/kernel',
        'Ff1Bias': 'ffn/layer_with_weights-0/bias', 'Ff2Weight': 'ffn/layer_with_weights-1/kernel',
        'Ff2Bias': 'ffn/layer_with_weights-1/bias', 'Norm1Gamma': 'layernorm1/gamma',
        'Norm1Beta': 'layernorm1/beta', 'Norm2Gamma': 'layernorm2/gamma', 'Norm2Beta': 'layernorm2/beta'}
    parameters = [{n: read('enc_layers/{}/{}'.format(i, p)) for n, p in mapping.items()} for i in range(12)]
    tasks = []
    totals = [{'error_squared': 0., 'reference_squared': 0., 'elements': 0} for _ in range(12)]
    audio_records = []
    # Every supplied sample is processed; --performance chooses exactly one task
    # per layer. --all-layers supports the 600 x 12 software precision evaluation.
    for sample_no, item in enumerate(samples):
        audio_record = dict(item)
        if item.get('silence'):
            audio = np.zeros(16000, dtype=np.float32)
            audio_record['normalization'] = 'official silence: one second zeros'
        else:
            path = Path(item['path'])
            if not path.is_absolute():
                path = args.dataset.resolve() / path
            with wave.open(str(path), 'rb') as f:
                if (f.getnchannels(), f.getframerate(), f.getsampwidth()) != (1, 16000, 2):
                    raise ValueError('Expected mono 16 kHz signed PCM16 WAV: ' + str(path))
                pcm = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').astype(np.float32)
            audio = np.zeros(16000, dtype=np.float32)
            audio[:min(len(pcm), 16000)] = pcm[:16000] / 32768.
            audio_record.update(sha256=sha(path), original_frames=len(pcm),
                                normalization='PCM16 / 32768; first 16000 samples; right zero pad')
        features = features_of(audio)
        if features.shape != (98, 40) or not np.isfinite(features).all():
            raise ValueError('Invalid official MFCC output')
        value = np.concatenate([read('class_emb').reshape(1, 64),
                                features @ read('patch_proj/kernel') + read('patch_proj/bias')])
        value += read('pos_emb').reshape(99, 64)
        audio_records.append(audio_record)
        for layer, params in enumerate(parameters):
            stages = Encoder(value, params)
            # Mandatory FF1 input is the corresponding FLOAT reference Norm1.
            # It is not the fixed encoder trace, and labels are not used as input.
            floating_input = stages['Norm1']
            fixed_input = Quantize(floating_input)
            fixed_params, fractions = QuantizeParameters(params)
            expected = Linear(fixed_input, fixed_params['Ff1Weight'], fixed_params['Ff1Bias'],
                              Shift=fractions['Ff1Weight'])
            floating = stages['Ff1']
            err = float(np.sum((expected / Scale - floating) ** 2))
            energy = float(np.sum(floating ** 2))
            totals[layer]['error_squared'] += err
            totals[layer]['reference_squared'] += energy
            totals[layer]['elements'] += expected.size
            chosen = args.all_layers or layer % len(samples) == sample_no
            if chosen:
                task = out / ('task_{:04d}_layer_{:02d}'.format(len(tasks), layer))
                task.mkdir()
                np.save(task / 'FloatInput.npy', floating_input)
                np.save(task / 'FloatOutput.npy', floating)
                fixed_input.astype('<i2').tofile(task / 'Input.bin')
                packed = np.concatenate([fixed_params['Ff1Weight'].T.reshape(-1), fixed_params['Ff1Bias']])
                packed.astype('<i2').tofile(task / 'Parameters.bin')
                expected.astype('<i2').tofile(task / 'Expected.bin')
                lines = ['L 0 0 0 Input.bin', 'L 3 6 16384 Parameters.bin']
                row = 0
                for block_index, count in enumerate([32, 32, 28, 7]):
                    filename = 'ExpectedRows{}.bin'.format(row)
                    expected[row:row+count].astype('<i2').tofile(task / filename)
                    block = row | (count << 8) | (int(block_index == 3) << 14)
                    slot = 1 if block_index % 2 == 0 else 5
                    lines.append('E 10 0 6 0 {} 1 {} 256 256 {} {} 10 {}'.format(
                        slot, count, filename, fractions['Ff1Weight'], block))
                    row += count
                (task / 'CoreProgram.txt').write_text('\n'.join(lines)+'\n')
                entry = {'id': task.name, 'layer': layer, 'sample': sample_no,
                         'activation_fraction': 11, 'weight_fraction': fractions['Ff1Weight'],
                         'input_bytes': 12672, 'parameter_bytes': 33280, 'output_bytes': 50688,
                         'shape': [99, 256], 'dtype': '<i2', 'nrmse': math.sqrt(err / max(energy, 1e-16)),
                         'files': {p.name: sha(p) for p in task.iterdir() if p.is_file()}}
                save(task / 'Task.json', entry)
                tasks.append(entry)
            value = stages['Output']
    nrmse = [math.sqrt(t['error_squared']/max(t['reference_squared'], 1e-16)) for t in totals]
    manifest = {'schema': 1, 'source_commit': revision, 'model_commit': PINNED_MODEL,
                'weights_sha256': {s: sha(str(prefix)+s) for s in ['.index', '.data-00000-of-00001']},
                'flags_sha256': sha(flags_path), 'samples_sha256': sha(args.samples),
                'feature_backend': feature_backend,
                'selection_purpose': spec.get('purpose', 'supplied_selection') if isinstance(spec, dict) else 'supplied_selection',
                'audio': audio_records, 'tasks': tasks,
                'numeric_configuration': 'Q11 activations, tensor weight fractions from frozen Reference.py; no fitting',
                'reference_sha256': sha(source / 'Model/Reference.py'),
                'precision_layers': totals, 'layer_nrmse': nrmse, 'worst_nrmse': max(nrmse),
                'software_precision_pass': max(nrmse) <= .03,
                'hardware_status': 'NOT_RUN', 'performance_status': 'NOT_MEASURED',
                'timing_scope': 'PC audio/features/packing excluded; physical SysBus load through final write response included'}
    save(out / 'Evaluation.json', manifest)
    print('VECTORS_READY samples={} tasks={} software_worst_nrmse={:.8f}'.format(len(samples), len(tasks), max(nrmse)))


def verify_vectors(root, manifest):
    for task in manifest['tasks']:
        for name, digest in task['files'].items():
            if sha(root / task['id'] / name) != digest:
                raise ValueError('Frozen vector changed: ' + task['id'] + '/' + name)


def run_core(args):
    root = args.out.resolve()
    manifest = load(root / 'Evaluation.json')
    verify_vectors(root, manifest)
    binary = args.binary.resolve()
    results = []
    for task in manifest['tasks']:
        directory = root / task['id']
        result = subprocess.run([str(binary), 'CoreProgram.txt'], cwd=str(directory),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        (directory / 'Core.log').write_text(result.stdout, encoding='utf-8')
        if result.returncode or result.stdout.count('PASS stage ') != 4 or 'PASS FF1 blocks: 4 stages' not in result.stdout:
            raise ValueError('Core comparison failed: ' + str(directory / 'Core.log'))
        results.append(task['id'])
    save(root / 'CoreResults.json', {'status': 'CORE_RTL_COMPARISON_PASS', 'tasks': results,
         'binary_sha256': sha(binary), 'performance_status': 'NOT_OFFICIAL_SYSTEM_PERFORMANCE',
         'scope': 'Legacy core harness only; not System Bus integration or timed external parameter loading'})
    print('CORE_RTL_COMPARISON_PASS tasks={}; NOT an official system performance result'.format(len(results)))


def validate_evidence(root, manifest, evidence, source_commit):
    """Adapter output is backed by raw SoC signal trace, not wall-clock timing."""
    import numpy as np
    if evidence['source_commit'] != source_commit or manifest['source_commit'] != source_commit:
        raise ValueError('Source commit mismatch')
    if evidence.get('system_bus_width') != 32 or evidence.get('shared_sram_bytes') != 524288:
        raise ValueError('Wrong platform interface or capacity')
    if evidence.get('mode') != 'soc_sysbus32' or evidence.get('preload_task_weights') is not False:
        raise ValueError('Only cold tasks on the real System Bus qualify')
    results = evidence['tasks']
    if len(results) != len(manifest['tasks']):
        raise ValueError('Missing or extra hardware tasks')
    trace_path = root / evidence['bus_trace']
    if sha(trace_path) != evidence['bus_trace_sha256']:
        raise ValueError('Raw bus trace changed')
    events = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    total = 0;task_windows=[]
    output_ids = set()
    for task, actual in zip(manifest['tasks'], results):
        if actual['id'] != task['id'] or actual['id'] in output_ids:
            raise ValueError('Task order/identity mismatch')
        output_ids.add(actual['id'])
        ev = [e for e in events if e.get('task') == task['id']]
        for a,b in zip(ev,ev[1:]):
            if b['cycle'] < a['cycle']:
                raise ValueError('Nonmonotonic bus trace')
        starts = [e for e in ev if e['event'] == 'load_begin']
        ends = [e for e in ev if e['event'] == 'final_write_response']
        clear = [e for e in ev if e['event'] == 'task_caches_cleared']
        loads = [e for e in ev if e['event'] == 'accepted_load_write']
        stores = [e for e in ev if e['event'] == 'accepted_result_write']
        if len(starts)!=1 or len(ends)!=1 or len(clear)!=1 or not loads or not stores:
            raise ValueError('Incomplete cold-load/writeback trace for ' + task['id'])
        first,last=starts[0]['cycle'],ends[0]['cycle']
        if not clear[0]['cycle'] <= first <= loads[0]['cycle'] <= last:
            raise ValueError('Timer starts after loading or cache clear missing')
        for e in loads+stores:
            if e.get('interface')!='platform_sysbus' or e.get('width_bits')!=32 or not first<=e['cycle']<=last:
                raise ValueError('Bypass interface, wrong width or transaction outside timer')
            if not 0 < e.get('bytes', 0) <= 4:
                raise ValueError('Invalid accepted-byte accounting')
        if sum(e['bytes'] for e in loads) != task['input_bytes']+task['parameter_bytes']:
            raise ValueError('Input/parameter transfers omitted or duplicated')
        if sum(e['bytes'] for e in stores) != task['output_bytes']:
            raise ValueError('Full output writeback missing/compressed')
        def bus_bytes(transfers):
            memory={}
            for e in transfers:
                if e['address']%4 or not 0<e['mask']<16 or e['bytes']!=bin(e['mask']).count('1'):
                    raise ValueError('Invalid aligned ICB byte mask')
                for lane in range(4):
                    if e['mask']&(1<<lane):
                        address=e['address']+lane
                        if address in memory:raise ValueError('Duplicate task-byte transfer')
                        memory[address]=(e['data']>>(8*lane))&255
            return memory
        loaded=bus_bytes(loads);stored=bus_bytes(stores)
        def check_region(memory,base,payload):
            if bytes(memory.get(base+i,-1) for i in range(len(payload)))!=payload:
                raise ValueError('Raw bus data/address do not match task payload')
        inp=(root/task['id']/'Input.bin').read_bytes();par=(root/task['id']/'Parameters.bin').read_bytes()
        expected_bytes=(root/task['id']/'Expected.bin').read_bytes()
        check_region(loaded,actual['input_address'],inp)
        check_region(loaded,actual['parameter_address'],par)
        check_region(stored,actual['output_address'],expected_bytes)
        data=np.fromfile(root/actual['output'],dtype='<i2')
        expected=np.fromfile(root/task['id']/'Expected.bin',dtype='<i2')
        if data.size!=99*256 or not np.array_equal(data,expected):
            raise ValueError('RTL/software output mismatch')
        cycles=last-first+1
        if actual['cycles']!=cycles or not actual.get('protocol_checks_pass'):
            raise ValueError('Cycle count or handshake guard failure')
        if task['nrmse']>.03:
            raise ValueError('A performance task exceeds 3% NRMSE')
        total+=cycles
        task_windows.append({'id':task['id'],'cycles':cycles,'duration_seconds':cycles/150000000.})
    if not results or evidence.get('clock_hz')!=150000000:
        raise ValueError('Empty batch or wrong frequency')
    return {'status':'SOC_PERFORMANCE_TRACE_VALIDATED', 'tasks':len(results), 'cycles':total,
            'duration_seconds':total/150000000., 'throughput_task_s':len(results)*150000000./total,
            'source_commit':source_commit, 'evidence_sha256':sha(root/'RunEvidence.json'),
            'task_windows':task_windows,
            'qualification':'Requires topology review and raw trace producer bound to actual DUT; no software timing substitution'}


def run_soc(args):
    root=args.out.resolve();manifest=load(root/'Evaluation.json');verify_vectors(root,manifest)
    config=load(args.config)
    if not config.get('frontend_bound'):
        raise ValueError('FRONTEND_PENDING: new SysBus32 adapter not bound; old adapters prohibited')
    from flow import check
    check(config)
    if len(manifest['tasks'])!=12 or sorted(t['layer'] for t in manifest['tasks'])!=list(range(12)):
        raise ValueError('Formal FF1 performance requires exactly 12 tasks covering all 12 layer parameter sets')
    cmd=config['evaluation_command']
    if not cmd or any('PENDING' in str(x) for x in cmd):
        raise ValueError('Missing new SoC simulator command')
    env=dict(os.environ, EVAL_VECTOR_ROOT=str(root), EVAL_SOURCE_COMMIT=config['source_commit'])
    subprocess.check_call(cmd,env=env)
    result=validate_evidence(root,manifest,load(root/'RunEvidence.json'),config['source_commit'])
    save(root/'Performance.json',result);print(json.dumps(result,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command')
    q=s.add_parser('select-smoke');q.add_argument('--dataset',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q=s.add_parser('prepare');q.add_argument('--frontend',type=Path,required=True);q.add_argument('--model',type=Path,required=True)
    q.add_argument('--dataset',type=Path,required=True);q.add_argument('--samples',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
    q.add_argument('--all-layers',action='store_true')
    q=s.add_parser('run-core');q.add_argument('--out',type=Path,required=True);q.add_argument('--binary',type=Path,required=True)
    q=s.add_parser('run-soc');q.add_argument('--out',type=Path,required=True);q.add_argument('--config',type=Path,required=True)
    a=p.parse_args()
    {'select-smoke':select,'prepare':prepare,'run-core':run_core,'run-soc':run_soc}[a.command](a)


if __name__=='__main__':
    main()
