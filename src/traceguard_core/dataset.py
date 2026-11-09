"""JSONL dataset creation and integrity/replay verification."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from traceguard_core.models import Manifest, ManifestEntry, Profile, Rubric, Scenario, Trace, digest
from traceguard_core.rules import reference_rules
from traceguard_sim.engine import replay, variants

CONFIGS = Path(__file__).resolve().parent / 'configs'
if not CONFIGS.is_dir():
    CONFIGS = Path(__file__).resolve().parents[2] / 'configs'


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(f'{path.name}:{line_number}: invalid JSON') from exc
    return rows


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text(''.join(json.dumps(v, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n' for v in values), encoding='utf-8')


@dataclass
class Dataset:
    manifest: Manifest
    traces: list[Trace]
    scenarios: dict[str, Scenario]
    profile: Profile
    rubric: dict
    drafts: list[dict]


def build_dataset(directory: Path, configs: Path = CONFIGS) -> None:
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f'Dataset directory already exists: {directory}')
    profile = Profile.model_validate(read_json(configs / 'gsn.json'))
    scenarios_raw = read_json(configs / 'scenarios.json')
    scenarios = [Scenario.model_validate(s) for s in scenarios_raw]
    rubric = Rubric.model_validate(read_json(configs / 'rubric.json')).model_dump()
    traces, entries, drafts = [], [], []
    for i, scenario in enumerate(scenarios):
        for mutation, planned, trace in variants(scenario, i, correct_count=profile.correct_per_scenario,
                                                 incorrect_count=profile.incorrect_per_scenario):
            traces.append(trace)
            entries.append(ManifestEntry(trace_id=trace.trace_id, scenario_id=scenario.scenario_id,
                                         template_group=scenario.template_group, split=scenario.split))
            drafts.append({'trace_id': trace.trace_id, 'mutation': mutation, 'planned_class': planned,
                           'review_status': 'PENDING_HUMAN',
                           **reference_rules(trace, scenario).model_dump()})
    identity = {'entries': [e.model_dump() for e in entries], 'profile': profile.model_dump(),
                'rubric': rubric, 'scenarios': scenarios_raw}
    manifest = Manifest(dataset_id=digest(identity), profile_id=profile.profile_id,
                        profile_hash=digest(profile.model_dump()), rubric_id=profile.rubric_id,
                        rubric_version=profile.rubric_version, rubric_hash=digest(rubric),
                        scenarios_hash=digest(scenarios_raw), entries=entries)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'profile.json', profile.model_dump())
    write_json(directory / 'rubric.json', rubric)
    write_json(directory / 'scenarios.json', scenarios_raw)
    write_json(directory / 'manifest.json', manifest.model_dump())
    write_jsonl(directory / 'traces.jsonl', [t.model_dump() for t in traces])
    write_jsonl(directory / 'reference_drafts.jsonl', drafts)
    validate_dataset(directory)


def load_dataset(directory: Path) -> Dataset:
    scenarios = [Scenario.model_validate(s) for s in read_json(directory / 'scenarios.json')]
    return Dataset(Manifest.model_validate(read_json(directory / 'manifest.json')),
                   [Trace.model_validate(t) for t in read_jsonl(directory / 'traces.jsonl')],
                   {s.scenario_id: s for s in scenarios}, Profile.model_validate(read_json(directory / 'profile.json')),
                   Rubric.model_validate(read_json(directory / 'rubric.json')).model_dump(),
                   read_jsonl(directory / 'reference_drafts.jsonl'))


def validate_dataset(directory: Path) -> dict:
    d = load_dataset(directory)
    m, p = d.manifest, d.profile
    if (d.rubric['rubric_id'], d.rubric['version']) != (m.rubric_id, m.rubric_version):
        raise ValueError('Rubric identity differs from manifest')
    scenarios_raw = read_json(directory / 'scenarios.json')
    if m.profile_hash != digest(p.model_dump()) or m.rubric_hash != digest(d.rubric) or m.scenarios_hash != digest(scenarios_raw):
        raise ValueError('Profile, rubric or scenario hash mismatch')
    identity = {'entries': [e.model_dump() for e in m.entries], 'profile': p.model_dump(),
                'rubric': d.rubric, 'scenarios': scenarios_raw}
    if m.dataset_id != digest(identity) or (m.profile_id, m.rubric_id, m.rubric_version) != (p.profile_id, p.rubric_id, p.rubric_version):
        raise ValueError('Manifest identity mismatch')
    ids = [t.trace_id for t in d.traces]
    if len(ids) != len(set(ids)) or set(ids) != {e.trace_id for e in m.entries} or len(m.entries) != len(ids):
        raise ValueError('Duplicate or missing trajectories')
    if len(ids) != p.trajectories or len(d.scenarios) != p.scenarios:
        raise ValueError('Dataset size differs from profile')
    if Counter(e.split for e in m.entries) != {'pilot': p.pilot_size, 'test': p.test_size}:
        raise ValueError('Invalid split sizes')
    grouped = {}
    by_scenario = Counter()
    entries = {e.trace_id: e for e in m.entries}
    for t in d.traces:
        s = d.scenarios[t.scenario_id]
        e = entries[t.trace_id]
        if (e.scenario_id, e.template_group, e.split) != (s.scenario_id, s.template_group, s.split):
            raise ValueError('Scenario/manifest mismatch')
        grouped.setdefault(e.template_group, set()).add(e.split)
        by_scenario[e.scenario_id] += 1
        if t.trace_id != t.content_hash():
            raise ValueError('Trace content hash mismatch')
        replay(t, s)
    if set(by_scenario) != set(d.scenarios) or any(len(parts) != 1 for parts in grouped.values()) or any(
        n != p.correct_per_scenario + p.incorrect_per_scenario for n in by_scenario.values()
    ):
        raise ValueError('Template leakage or incomplete scenario')
    if len(d.drafts) != len(ids) or {r['trace_id'] for r in d.drafts} != set(ids):
        raise ValueError('Missing reference drafts')
    drafts = {r['trace_id']: r for r in d.drafts}
    for scenario_id in d.scenarios:
        rows = [drafts[t.trace_id] for t in d.traces if t.scenario_id == scenario_id]
        if Counter(r.get('planned_class') for r in rows) != {
            'PASS': p.correct_per_scenario, 'FAIL': p.incorrect_per_scenario
        }:
            raise ValueError('Planned class counts differ from profile')
        mutations = [r.get('mutation') for r in rows if r.get('planned_class') == 'FAIL']
        if len(set(mutations)) != len(mutations) or any(m in {None, 'none'} for m in mutations):
            raise ValueError('Missing or duplicate fault mutations')
        if any(r.get('mutation') != 'none' for r in rows if r.get('planned_class') == 'PASS'):
            raise ValueError('Correct trajectory marked as mutated')
    for trace in d.traces:
        draft = drafts[trace.trace_id]
        if any(draft[k] != v for k, v in reference_rules(trace, d.scenarios[trace.scenario_id]).model_dump().items()):
            raise ValueError('Reference rules differ from replayed trace')
    return {'dataset_id': m.dataset_id, 'scenarios': len(d.scenarios), 'trajectories': len(ids),
            'pilot': p.pilot_size, 'test': p.test_size, 'human_references': 'PENDING'}
