import copy
import fcntl
import json
import subprocess
import sys
from pathlib import Path

import pytest

from traceguard_core.annotation_cli import annotate
from traceguard_core.annotations import _checked, export_forms, freeze_references
from traceguard_core.dataset import build_dataset, load_dataset, read_jsonl, write_jsonl
from traceguard_core.models import CRITERIA
from test_annotations import completed_forms


@pytest.fixture(scope='module')
def dataset(tmp_path_factory):
    directory = tmp_path_factory.mktemp('annotation-dataset')
    build_dataset(directory)
    return directory


@pytest.fixture
def session(dataset, tmp_path):
    forms = tmp_path / 'blank.jsonl'
    rows = export_forms(dataset, 'author')[:2]
    write_jsonl(forms, rows)
    return dataset, forms, tmp_path / 'work.jsonl', rows


def answers(verdict='PASS', confirmed='t'):
    return [value for _ in CRITERIA for value in (verdict, 'e1, answer', 'Ocena na podstawie wskazanych zdarzeń.')] + [confirmed]


def respond(monkeypatch, values):
    iterator = iter(values)

    def read():
        try:
            value = next(iterator)
        except StopIteration:
            raise EOFError from None
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr('builtins.input', read)


def test_annotations_are_human_entered_validated_and_blind(session, monkeypatch, capsys):
    directory, forms, output, original = session
    before = forms.read_bytes()
    respond(monkeypatch, answers('FAIL') + answers())
    result = annotate(directory, forms, 'person-1', output)
    assert result == {'total': 2, 'reviewed': 2, 'remaining': 0, 'interrupted': False, 'output': str(output)}
    rows = read_jsonl(output)
    assert forms.read_bytes() == before
    assert all(r['annotator_id'] == 'person-1' and r['reviewed'] is True for r in rows)
    assert all(v['verdict'] == 'FAIL' for v in rows[0]['criteria'].values())
    assert all(v['evidence'] == ['e1', 'answer'] for row in rows for v in row['criteria'].values())
    traces = {t.trace_id: t for t in load_dataset(directory).traces}
    assert set(_checked(rows, traces)) == {r['trace_id'] for r in original}
    screen = capsys.readouterr().err
    assert original[0]['observation']['task'] in screen
    assert original[0]['observation']['final_answer'] in screen
    assert 'e1' in screen and 'Wykonanie zadania' in screen
    assert all(key not in screen for key in ('planned_class', 'mutation', 'initial_state', 'final_state', 'PENDING_HUMAN'))


@pytest.mark.parametrize('stop', ['q', EOFError(), KeyboardInterrupt()])
def test_stop_and_resume_preserve_completed_rows(session, monkeypatch, stop):
    directory, forms, output, _ = session
    respond(monkeypatch, answers() + ['FAIL', stop])
    result = annotate(directory, forms, 'person-1', output)
    assert result['interrupted'] is True and result['reviewed'] == result['remaining'] == 1
    saved = read_jsonl(output)
    assert saved[0]['reviewed'] is True and saved[1]['reviewed'] is False
    assert all(c['verdict'] == 'INDETERMINATE' for c in saved[1]['criteria'].values())
    respond(monkeypatch, answers('FAIL'))
    assert annotate(directory, forms, 'person-1', output)['remaining'] == 0
    assert read_jsonl(output)[0] == saved[0]
    assert all(v['verdict'] == 'FAIL' for v in read_jsonl(output)[1]['criteria'].values())
    respond(monkeypatch, [AssertionError('Completed rows must not be prompted again')])
    assert annotate(directory, forms, 'person-1', output)['reviewed'] == 2


def test_invalid_input_reprompts_without_inventing_values(session, monkeypatch, capsys):
    directory, forms, output, _ = session
    values = ['NA', '', 'pass', '', 'e999', 'e1 answer e1', '   ', 'Uzasadnienie.']
    values += answers()[3:-1] + ['', 'tak', 'q']
    respond(monkeypatch, values)
    result = annotate(directory, forms, 'person-1', output)
    assert result['reviewed'] == 1
    criterion = read_jsonl(output)[0]['criteria'][CRITERIA[0]]
    assert criterion == {'verdict': 'PASS', 'evidence': ['e1', 'answer'], 'reason': 'Uzasadnienie.'}
    assert 'Podaj PASS albo FAIL' in capsys.readouterr().err


def test_full_review_requires_confirmation(session, monkeypatch):
    directory, forms, output, _ = session
    respond(monkeypatch, answers(confirmed='q'))
    assert annotate(directory, forms, 'person-1', output)['reviewed'] == 0
    assert not any(row['reviewed'] for row in read_jsonl(output))
    respond(monkeypatch, answers(confirmed='n') + answers('FAIL') + ['q'])
    assert annotate(directory, forms, 'person-1', output)['reviewed'] == 1
    assert all(c['verdict'] == 'FAIL' for c in read_jsonl(output)[0]['criteria'].values())


@pytest.mark.parametrize('change', ['annotator', 'selection', 'observation', 'evidence', 'truncated', 'dataset', 'duplicate', 'partial', 'criteria_type'])
def test_resume_rejects_mismatched_or_corrupt_data(session, monkeypatch, change):
    directory, forms, output, original = session
    respond(monkeypatch, answers() + ['q'])
    annotate(directory, forms, 'person-1', output)
    if change == 'selection':
        write_jsonl(forms, original[:1])
    elif change == 'truncated':
        with output.open('ab') as file:
            file.write(b'{"partial":')
    elif change == 'dataset':
        path = output.with_suffix(output.suffix + '.session.json')
        metadata = json.loads(path.read_text())
        metadata['dataset_id'] = 'another-dataset'
        path.write_text(json.dumps(metadata))
    elif change in {'duplicate', 'partial'}:
        rows = read_jsonl(output)
        if change == 'duplicate':
            rows[1] = rows[0]
        else:
            rows[1]['criteria']['arguments']['verdict'] = 'PASS'
        write_jsonl(output, rows)
    elif change == 'criteria_type':
        rows = read_jsonl(output)
        rows[0]['criteria'] = list(CRITERIA)
        write_jsonl(output, rows)
    elif change in {'observation', 'evidence'}:
        rows = read_jsonl(output)
        if change == 'observation':
            rows[0]['observation']['final_answer'] = 'Inna odpowiedź.'
        else:
            rows[0]['criteria']['arguments']['evidence'] = ['e999']
        write_jsonl(output, rows)
    before = output.read_bytes()
    respond(monkeypatch, [AssertionError('Invalid session must fail before input')])
    with pytest.raises(ValueError):
        annotate(directory, forms, 'person-2' if change == 'annotator' else 'person-1', output)
    assert output.read_bytes() == before


@pytest.mark.parametrize('change', ['duplicate', 'observation', 'metadata', 'reviewed', 'empty', 'criteria', 'split'])
def test_bad_sources_are_rejected_before_creating_output(session, monkeypatch, change):
    directory, forms, output, original = session
    rows = copy.deepcopy(original)
    if change == 'duplicate':
        rows.append(rows[0])
    elif change == 'observation':
        rows[0]['observation']['task'] = 'Nieprawidłowe zadanie.'
    elif change == 'metadata':
        rows[0]['mutation'] = 'delete_logs'
    elif change == 'reviewed':
        rows[0]['reviewed'] = True
    elif change == 'empty':
        rows = []
    elif change == 'criteria':
        rows[0]['criteria']['arguments']['verdict'] = 'PASS'
    else:
        rows[0]['split'] = 'test'
    write_jsonl(forms, rows)
    respond(monkeypatch, [AssertionError('Bad source must fail before input')])
    with pytest.raises(ValueError):
        annotate(directory, forms, 'person-1', output)
    assert not output.exists()


def test_output_cannot_overwrite_source_or_dataset(session, monkeypatch):
    directory, forms, output, _ = session
    respond(monkeypatch, ['q'])
    before = forms.read_bytes()
    with pytest.raises(ValueError):
        annotate(directory, forms, 'person-1', forms)
    assert forms.read_bytes() == before
    with pytest.raises(ValueError):
        annotate(directory, forms, 'person-1', directory / 'new.jsonl')
    assert not (directory / 'new.jsonl').exists()
    output.write_text('Do not overwrite\n')
    with pytest.raises(ValueError):
        annotate(directory, forms, 'person-1', output)
    assert output.read_text() == 'Do not overwrite\n'


def test_session_lock_prevents_concurrent_writers(session, monkeypatch):
    directory, forms, output, _ = session
    lock_path = output.with_suffix(output.suffix + '.lock')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        respond(monkeypatch, [AssertionError('Locked session must not prompt')])
        with pytest.raises(ValueError, match='sesja'):
            annotate(directory, forms, 'person-1', output)
    assert not output.exists()


@pytest.mark.parametrize('error', [OSError('disk error'), KeyboardInterrupt()])
def test_failed_checkpoint_preserves_previous_file(session, monkeypatch, error):
    import traceguard_core.annotation_cli as ui

    directory, forms, output, _ = session
    respond(monkeypatch, answers() + ['q'])
    annotate(directory, forms, 'person-1', output)
    before = output.read_bytes()

    def fail_replace(*_):
        raise error

    monkeypatch.setattr(ui.os, 'replace', fail_replace)
    respond(monkeypatch, answers('FAIL'))
    if isinstance(error, KeyboardInterrupt):
        result = annotate(directory, forms, 'person-1', output)
        assert result['reviewed'] == 1 and result['interrupted'] is True
    else:
        with pytest.raises(OSError):
            annotate(directory, forms, 'person-1', output)
    assert output.read_bytes() == before
    assert not list(output.parent.glob(f'.{output.name}.*.tmp'))


def test_interactive_output_can_be_used_to_freeze_references(session, monkeypatch):
    directory, forms, output, _ = session
    respond(monkeypatch, answers() + answers())
    annotate(directory, forms, 'person-1', output)
    rows = completed_forms(directory, 'person-1')
    interactive = {row['trace_id']: row for row in read_jsonl(output)}
    combined = [interactive.get(row['trace_id'], row) for row in rows]
    author = output.parent / 'all.jsonl'
    write_jsonl(author, combined)
    frozen = freeze_references(directory, author, output.parent / 'references.json')
    assert len(frozen['references']) == 150
    assert all(r['verdict'] == 'PASS' for r in frozen['references'] if r['trace_id'] in interactive)


def test_secondary_session_uses_only_the_preselected_twenty_forms(dataset, tmp_path, monkeypatch):
    forms = Path('data/annotation_tasks/gsn-v2/secondary.jsonl')
    original = forms.read_bytes()
    output = tmp_path / 'secondary.jsonl'
    respond(monkeypatch, ['q'])
    result = annotate(dataset, forms, 'person-2', output)
    rows = read_jsonl(output)
    assert result['total'] == result['remaining'] == 20 and result['reviewed'] == 0
    assert [r['trace_id'] for r in rows] == [r['trace_id'] for r in read_jsonl(forms)]
    assert all(r['split'] == 'test' and r['annotator_id'] == 'person-2' for r in rows)
    assert forms.read_bytes() == original


def test_resume_rejects_another_dataset_even_with_the_same_selected_traces(session, monkeypatch):
    directory, forms, output, _ = session
    respond(monkeypatch, ['q'])
    annotate(directory, forms, 'person-1', output)
    legacy = output.parent / 'legacy'
    build_dataset(legacy, Path('configs'))
    before = output.read_bytes()
    with pytest.raises(ValueError, match='innego zbioru'):
        annotate(legacy, forms, 'person-1', output)
    assert output.read_bytes() == before


def test_empty_annotator_is_rejected(session, monkeypatch):
    directory, forms, output, _ = session
    respond(monkeypatch, [AssertionError('Missing person must fail before input')])
    with pytest.raises(ValueError, match='annotatora'):
        annotate(directory, forms, '   ', output)
    assert not output.exists()


def test_cli_annotate_in_subprocess_and_resume(session):
    directory, forms, output, _ = session
    command = [sys.executable, '-m', 'traceguard_core', 'annotate', '--dataset', str(directory),
               '--forms', str(forms), '--annotator', 'person-1', '--output', str(output)]
    result = subprocess.run(command, input='\n'.join(answers() + ['q']) + '\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['reviewed'] == 1
    result = subprocess.run(command, input='\n'.join(answers('FAIL')) + '\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['remaining'] == 0
    rows = read_jsonl(output)
    assert all(row['reviewed'] for row in rows)
    assert rows[0]['criteria']['arguments']['verdict'] == 'PASS'
    assert rows[1]['criteria']['arguments']['verdict'] == 'FAIL'
