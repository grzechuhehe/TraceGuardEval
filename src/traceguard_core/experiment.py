"""Split isolation, frozen configurations and crash-resumable execution."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

from traceguard_core.dataset import load_dataset, read_json, validate_dataset
from traceguard_core.evaluation import HTTPJudge, JudgeConfig, system_prompt
from traceguard_core.models import canonical, digest


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def exclusive_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as file:
        file.write(canonical(value) + '\n')
        file.flush()
        os.fsync(file.fileno())


def hashed_record(value: dict) -> dict:
    return {**value, 'record_hash': digest(value)}


def verify_record(value: dict) -> None:
    if value.get('record_hash') != digest({k: v for k, v in value.items() if k != 'record_hash'}):
        raise ValueError('Saved result/attempt content hash mismatch')


class SplitRegistry:
    """One explicitly shared registry must be reused across profiles and runs."""

    def __init__(self, path: Path):
        self.path = path

    def reserve_test_groups(self, groups: list[str], profile_id: str) -> None:
        with locked(self.path.with_suffix('.lock')):
            current = read_json(self.path) if self.path.exists() else {}
            for group in groups:
                current[group] = sorted(set(current.get(group, [])) | {profile_id})
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(canonical(current) + '\n', encoding='utf-8')
            temporary.replace(self.path)

    def assert_pilot_allowed(self, groups: list[str]) -> None:
        with locked(self.path.with_suffix('.lock')):
            current = read_json(self.path) if self.path.exists() else {}
            if set(groups) & set(current):
                raise ValueError('Pilot contains a frozen test group from this or another profile')


def code_hash() -> str:
    from traceguard_sim import engine
    directories = [Path(__file__).parent, Path(engine.__file__).parent]
    return digest({f'{d.name}/{p.name}': p.read_text(encoding='utf-8')
                   for d in directories for p in sorted(d.glob('*.py'))})


def load_references(path: Path, dataset_id: str) -> dict:
    snapshot = read_json(path)
    if snapshot['dataset_id'] != dataset_id or snapshot['reference_hash'] != digest(
        {k: v for k, v in snapshot.items() if k != 'reference_hash'}
    ):
        raise ValueError('Reference identity mismatch')
    return snapshot


def make_pairs(directory: Path, references_file: Path, split: str = 'test') -> list[dict]:
    d = load_dataset(directory)
    refs = {r['trace_id']: r for r in load_references(references_file, d.manifest.dataset_id)['references']}
    pairs = []
    for sid in sorted(d.scenarios):
        ids = [e.trace_id for e in d.manifest.entries if e.scenario_id == sid and e.split == split]
        if not ids:
            continue
        good = [tid for tid in ids if refs[tid]['verdict'] == 'PASS']
        bad = [tid for tid in ids if refs[tid]['verdict'] == 'FAIL']
        if len(good) < 2 or not bad:
            raise ValueError('Pair construction needs two correct and one failed trace per scenario')
        for a, b, preference in [(good[0], bad[0], 'A'), (good[0], good[1], 'TIE')]:
            pairs.append({'pair_id': digest([a, b]), 'a': a, 'b': b, 'reference': preference})
    return pairs


def freeze_experiment(directory: Path, references_file: Path, config: JudgeConfig, output: Path,
                      registry: SplitRegistry, calibration: dict | None = None) -> dict:
    validate_dataset(directory)
    d = load_dataset(directory)
    refs = load_references(references_file, d.manifest.dataset_id)
    if config.repeats != d.profile.repeats or (config.score_min, config.score_max) != (d.profile.score_min, d.profile.score_max):
        raise ValueError('Judge settings differ from the research profile')
    if config.method == 'score':
        if calibration is None or calibration.get('dataset_id') != d.manifest.dataset_id or calibration.get('reference_hash') != refs['reference_hash']:
            raise ValueError('Score format requires pilot calibration')
        if calibration.get('configuration') != config.model_dump():
            raise ValueError('Score configuration differs from calibrated settings')
        if calibration.get('code_hash') != code_hash():
            raise ValueError('Calibration was produced by a different code version')
        if calibration.get('prompt_hash') != digest(system_prompt(config, d.rubric)):
            raise ValueError('Calibration was produced by a different prompt version')
    registry.reserve_test_groups([e.template_group for e in d.manifest.entries if e.split == 'test'], d.profile.profile_id)
    frozen = {'schema_version': '1.0', 'dataset_id': d.manifest.dataset_id,
              'reference_hash': refs['reference_hash'], 'profile_hash': d.manifest.profile_hash,
              'rubric_hash': d.manifest.rubric_hash, 'configuration': config.model_dump(),
              'code_hash': code_hash(), 'prompt_hash': digest(system_prompt(config, d.rubric)),
              'pairs': make_pairs(directory, references_file) if config.method == 'pairwise' else [],
              'calibration': calibration}
    frozen['freeze_hash'] = digest(frozen)
    exclusive_json(output, frozen)
    return frozen


def _resume_rows(path: Path) -> list[dict]:
    """Discard only an interrupted final JSON record, never an interior corruption."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    lines, rows, offset = raw.splitlines(keepends=True), [], 0
    for i, line in enumerate(lines):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('Result row must be an object')
        except (ValueError, UnicodeError):
            if i != len(lines) - 1 or line.endswith(b'\n'):
                raise ValueError('Corrupt result ledger') from None
            with path.open('r+b') as file:
                file.truncate(offset)
            break
        rows.append(row)
        offset += len(line)
    if rows and path.read_bytes() and not path.read_bytes().endswith(b'\n'):
        with path.open('ab') as file:
            file.write(b'\n')
    return rows


def attempts_path(results: Path) -> Path:
    return results.with_suffix(results.suffix + '.attempts.jsonl')


def run_batch(directory: Path, output: Path, config: JudgeConfig, judge: HTTPJudge,
              registry: SplitRegistry, split: str = 'pilot', frozen_file: Path | None = None,
              pairs_file: Path | None = None) -> dict:
    validate_dataset(directory)
    d = load_dataset(directory)
    if split not in {'pilot', 'test'}:
        raise ValueError('Unknown split')
    if config.repeats != d.profile.repeats or (config.score_min, config.score_max) != (d.profile.score_min, d.profile.score_max):
        raise ValueError('Configuration differs from profile')
    registry.reserve_test_groups([e.template_group for e in d.manifest.entries if e.split == 'test'], d.profile.profile_id)
    frozen = None
    if split == 'test':
        if frozen_file is None:
            raise ValueError('Test requires a frozen experiment configuration')
        frozen = read_json(frozen_file)
        checks = {'dataset_id': d.manifest.dataset_id, 'configuration': config.model_dump(),
                  'profile_hash': d.manifest.profile_hash, 'rubric_hash': d.manifest.rubric_hash,
                  'code_hash': code_hash(), 'prompt_hash': digest(system_prompt(config, d.rubric))}
        if frozen.get('freeze_hash') != digest({k: v for k, v in frozen.items() if k != 'freeze_hash'}) or any(
            frozen.get(k) != v for k, v in checks.items()
        ):
            raise ValueError('Frozen configuration no longer matches dataset, prompt or code')
    else:
        registry.assert_pilot_allowed([e.template_group for e in d.manifest.entries if e.split == 'pilot'])
    selected = {e.trace_id for e in d.manifest.entries if e.split == split}
    by_id = {t.trace_id: t for t in d.traces}
    if config.method == 'pairwise':
        if frozen is None and pairs_file is None:
            raise ValueError('Pilot pairwise execution requires an explicit pilot pair list')
        pairs = frozen['pairs'] if frozen else read_json(pairs_file)
        if (frozen is not None and len(pairs) != d.profile.pairs or not pairs
                or len({p['pair_id'] for p in pairs}) != len(pairs)):
            raise ValueError('Invalid pair list')
        units = []
        for pair in pairs:
            if not {pair['a'], pair['b']} <= selected or by_id[pair['a']].scenario_id != by_id[pair['b']].scenario_id:
                raise ValueError('Pair crosses scenario or split')
            units.extend([(pair['pair_id'], pair['a'], pair['b'], 'AB'),
                          (pair['pair_id'], pair['b'], pair['a'], 'BA')])
    else:
        units = [(tid, tid, None, 'single') for tid in sorted(selected)]
    metadata = {'dataset_id': d.manifest.dataset_id, 'configuration': config.model_dump(), 'split': split,
                'code_hash': code_hash(), 'prompt_hash': digest(system_prompt(config, d.rubric)),
                'freeze_hash': frozen['freeze_hash'] if frozen else None,
                'pairs': pairs if config.method == 'pairwise' else []}
    run_hash = digest(metadata)
    planned = {(unit, orientation, repeat) for unit, _, _, orientation in units for repeat in range(config.repeats)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with locked(output.with_suffix(output.suffix + '.lock')):
        old = _resume_rows(output)
        attempt_log = attempts_path(output)
        previous_attempts = _resume_rows(attempt_log)
        for record in old + previous_attempts:
            verify_record(record)
        if any(r.get('run_hash') != run_hash for r in old + previous_attempts):
            raise ValueError('Result ledger belongs to a different configuration or code version')
        finished = {(r['unit_id'], r['orientation'], r['repeat_id']) for r in old}
        if len(finished) != len(old) or not finished <= planned:
            raise ValueError('Unexpected or duplicate completed evaluation')
        executed = 0
        with output.open('a', encoding='utf-8') as file, attempt_log.open('a', encoding='utf-8') as journal:
            for unit, tid, other, orientation in units:
                for repeat in range(config.repeats):
                    if (unit, orientation, repeat) in finished:
                        continue
                    def record_attempt(attempt: dict):
                        journal.write(canonical(hashed_record({'run_hash': run_hash, 'metadata': metadata,
                                      'unit_id': unit, 'orientation': orientation,
                                      'repeat_id': repeat, 'attempt': attempt})) + '\n')
                        journal.flush()
                        os.fsync(journal.fileno())

                    result, attempts = judge.evaluate(by_id[tid], config, d.rubric,
                                                      by_id[other] if other else None, record_attempt)
                    row = {'schema_version': '1.0', 'run_hash': run_hash, 'metadata': metadata,
                           'unit_id': unit, 'trace_id': tid, 'other_trace_id': other,
                           'orientation': orientation, 'repeat_id': repeat,
                           'prediction': result.model_dump(), 'attempts': attempts}
                    file.write(canonical(hashed_record(row)) + '\n')
                    file.flush()
                    os.fsync(file.fileno())
                    executed += 1
    return {'run_hash': run_hash, 'planned': len(planned), 'executed': executed, 'resumed': len(old)}
