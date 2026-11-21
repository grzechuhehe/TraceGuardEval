"""Blind terminal review with validated, resumable JSONL checkpoints."""

import fcntl
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from traceguard_core.annotations import _checked, export_forms
from traceguard_core.dataset import load_dataset, read_json, read_jsonl
from traceguard_core.experiment import exclusive_json
from traceguard_core.models import CRITERIA, Rubric, Trace, canonical, digest


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _ask(prompt: str) -> str:
    print(prompt, end='', file=sys.stderr, flush=True)
    answer = input().strip()
    if answer.casefold() == 'q':
        raise EOFError
    return answer


def _validate_rows(rows: list[dict], expected: dict[str, dict], traces: dict[str, Trace],
                   *, source: bool) -> list[dict]:
    if not rows:
        raise ValueError('Formularze nie mogą być puste.')
    checked, seen, reviewed = [], set(), []
    for row in rows:
        if not isinstance(row, dict) or row.get('trace_id') not in expected or row['trace_id'] in seen:
            raise ValueError('Nieznany lub powtórzony formularz.')
        seen.add(row['trace_id'])
        blank = expected[row['trace_id']]
        if source:
            identity = row.get('annotator_id')
            if not isinstance(identity, str) or not identity.strip() or row.get('reviewed') is not False:
                raise ValueError('Źródło musi zawierać puste, nieocenione formularze.')
            if canonical(row) != canonical({**blank, 'annotator_id': identity}):
                raise ValueError('Formularz źródłowy różni się od ślepego eksportu zbioru.')
            checked.append(deepcopy(blank))
        else:
            if row.get('reviewed') is False:
                wanted = blank
            elif row.get('reviewed') is True:
                wanted = {**blank, 'reviewed': True, 'criteria': row.get('criteria')}
                reviewed.append(row)
            else:
                raise ValueError('Nieprawidłowy status sprawdzenia formularza.')
            if canonical(row) != canonical(wanted):
                raise ValueError('Zapisane adnotacje różnią się od formularzy sesji.')
            checked.append(row)
    if not source and [r['trace_id'] for r in rows] != list(expected):
        raise ValueError('Zmieniono zestaw lub kolejność formularzy sesji.')
    if reviewed:
        _checked(reviewed, traces)
    return checked


def _checkpoint(output: Path, rows: list[dict]) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         prefix=f'.{output.name}.', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(''.join(canonical(row) + '\n' for row in rows))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _review(row: dict, rubric: Rubric) -> dict:
    observation = row['observation']
    _say(json.dumps(observation, ensure_ascii=False, indent=2))
    allowed = {'answer'} | {event['event_id'] for event in observation['events']}
    definitions = {criterion.criterion_id: criterion for criterion in rubric.criteria}
    while True:
        criteria = {}
        for key in CRITERIA:
            definition = definitions[key]
            _say(f'\n{definition.name}: {definition.pass_condition}')
            _say(f'Dowody: {definition.evidence}')
            while True:
                verdict = _ask('Ocena [PASS/FAIL]: ').upper()
                if verdict in {'PASS', 'FAIL'}:
                    break
                _say('Podaj PASS albo FAIL. Brak oceny nie oznacza poprawności.')
            while True:
                evidence = list(dict.fromkeys(filter(None, re.split(r'[,\s]+', _ask('Dowody [e1, e2, answer]: ')))))
                if evidence and set(evidence) <= allowed:
                    break
                _say('Podaj co najmniej jeden istniejący identyfikator zdarzenia albo answer.')
            while True:
                reason = _ask('Uzasadnienie: ')
                if reason:
                    break
                _say('Uzasadnienie nie może być puste.')
            criteria[key] = {'verdict': verdict, 'evidence': evidence, 'reason': reason}
        _say(json.dumps(criteria, ensure_ascii=False, indent=2))
        while True:
            confirm = _ask('Potwierdzasz osobiste sprawdzenie całej trajektorii i zapis ocen? [t/n]: ').casefold()
            if confirm in {'t', 'tak'}:
                return {**row, 'criteria': criteria, 'reviewed': True}
            if confirm in {'n', 'nie'}:
                _say('Nie zapisano ocen. Oceń tę trajektorię ponownie.')
                break
            _say('Podaj t albo n; q kończy sesję bez zapisu bieżącej trajektorii.')


def annotate(directory: Path, forms_file: Path, annotator: str, output: Path) -> dict:
    """Review blank source forms; resume only the same dataset, selection and person."""
    annotator = annotator.strip()
    if not annotator:
        raise ValueError('Identyfikator annotatora nie może być pusty.')
    metadata_path = output.with_suffix(output.suffix + '.session.json')
    lock_path = output.with_suffix(output.suffix + '.lock')
    for path in (output, metadata_path, lock_path):
        if path.is_symlink() or path.resolve() == forms_file.resolve() or path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Sesja nie może nadpisywać źródłowych formularzy ani plików zbioru.')
    dataset = load_dataset(directory)
    blanks = {row['trace_id']: row for row in export_forms(directory, annotator)}
    traces = {trace.trace_id: trace for trace in dataset.traces}
    rows = _validate_rows(read_jsonl(forms_file), blanks, traces, source=True)
    expected = {row['trace_id']: row for row in rows}
    metadata = {'schema_version': '1.0', 'dataset_id': dataset.manifest.dataset_id,
                'annotator_id': annotator, 'forms_hash': digest(rows)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Inna sesja edytuje ten plik adnotacji.') from None
        if metadata_path.exists():
            if read_json(metadata_path) != metadata:
                raise ValueError('Sesja dotyczy innego zbioru, annotatora lub zestawu formularzy.')
            if output.exists():
                rows = _validate_rows(read_jsonl(output), expected, traces, source=False)
        elif output.exists():
            raise ValueError('Istniejący plik nie ma metadanych sesji. Wybierz nową ścieżkę wyjściową.')
        else:
            exclusive_json(metadata_path, metadata)
        if not output.exists():
            _checkpoint(output, rows)
        rubric = Rubric.model_validate(dataset.rubric)
        interrupted = False
        _say('q, Ctrl+C lub koniec wejścia kończy sesję. Niepotwierdzone oceny nie są zapisywane.')
        try:
            for index, row in enumerate(rows):
                if row['reviewed']:
                    continue
                _say(f'\nTrajektoria {index + 1}/{len(rows)}: {row["trace_id"]}')
                candidate = _review(row, rubric)
                _checked([candidate], traces)
                updated = rows.copy()
                updated[index] = candidate
                _checkpoint(output, updated)
                rows = updated
                _say('Zapisano trajektorię.')
        except (EOFError, KeyboardInterrupt):
            rows = _validate_rows(read_jsonl(output), expected, traces, source=False)
            interrupted = True
            _say('\nPrzerwano sesję. Wcześniej zapisane oceny pozostają zachowane.')
        reviewed = sum(row['reviewed'] for row in rows)
        return {'total': len(rows), 'reviewed': reviewed, 'remaining': len(rows) - reviewed,
                'interrupted': interrupted, 'output': str(output)}
