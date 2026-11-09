"""Offline-first command line. Network is used only by the explicit run command."""

import argparse
import csv
import html
import json
import os
import sys
from pathlib import Path

import httpx

from traceguard_core.analysis import calibrate_threshold, report
from traceguard_core.annotations import export_forms, freeze_references
from traceguard_core.dataset import CONFIGS, build_dataset, load_dataset, read_json, validate_dataset, write_json, write_jsonl
from traceguard_core.evaluation import HTTPJudge, JudgeConfig
from traceguard_core.experiment import SplitRegistry, exclusive_json, freeze_experiment, make_pairs, run_batch


def _new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f'Output already exists: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog='traceguard', description='TraceGuard GSN: symulator i ewaluacja offline')
    commands = cli.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build', help='Wygeneruj zbiór GSN bez API (domyślnie v2: 150 trajektorii)')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--configs', type=Path, default=CONFIGS)
    validate = commands.add_parser('validate', help='Sprawdź hashe, podział i replay')
    validate.add_argument('--dataset', type=Path, required=True)
    annotations = commands.add_parser('annotations', help='Eksport ślepych formularzy do adnotacji')
    annotations.add_argument('--dataset', type=Path, required=True)
    annotations.add_argument('--annotator', required=True)
    annotations.add_argument('--split', choices=['pilot', 'test'])
    annotations.add_argument('--output', type=Path, required=True)
    refs = commands.add_parser('freeze-references', help='Zamroź sprawdzone przez człowieka referencje')
    refs.add_argument('--dataset', type=Path, required=True)
    refs.add_argument('--author', type=Path, required=True)
    refs.add_argument('--secondary', type=Path)
    refs.add_argument('--adjudications', type=Path)
    refs.add_argument('--output', type=Path, required=True)
    pairs = commands.add_parser('pairs', help='Przygotuj pary na podstawie zamrożonych referencji')
    pairs.add_argument('--dataset', type=Path, required=True)
    pairs.add_argument('--references', type=Path, required=True)
    pairs.add_argument('--split', choices=['pilot', 'test'], default='test')
    pairs.add_argument('--output', type=Path, required=True)
    for name in ['run', 'calibrate', 'freeze']:
        command = commands.add_parser(name)
        command.add_argument('--dataset', type=Path, required=True)
        command.add_argument('--registry', type=Path, required=True,
                             help='Ten sam rejestr dla wszystkich uruchomień i profili')
        command.add_argument('--output', type=Path, required=True)
        if name in {'run', 'freeze'}:
            command.add_argument('--config', type=Path, required=True)
        if name in {'calibrate', 'freeze'}:
            command.add_argument('--references', type=Path, required=True)
        if name == 'run':
            command.add_argument('--split', choices=['pilot', 'test'], default='pilot')
            command.add_argument('--frozen', type=Path)
            command.add_argument('--pairs', type=Path, help='Lista par do pilotażu formatu pairwise')
            command.add_argument('--api-key-env', default='TRACEGUARD_API_KEY', help='Nazwa zmiennej, nigdy wartość klucza')
        if name == 'calibrate':
            command.add_argument('--results', type=Path, required=True)
        if name == 'freeze':
            command.add_argument('--calibration', type=Path)
    summary = commands.add_parser('report', help='Odtwórz metryki wyłącznie z lokalnych wyników')
    summary.add_argument('--dataset', type=Path, required=True)
    summary.add_argument('--references', type=Path, required=True)
    summary.add_argument('--results', type=Path, required=True)
    summary.add_argument('--frozen', type=Path)
    summary.add_argument('--output', type=Path, required=True, help='Nowy katalog raportu JSON/CSV/HTML')
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == 'build':
            build_dataset(args.output, args.configs)
            result = validate_dataset(args.output)
        elif args.command == 'validate':
            result = validate_dataset(args.dataset)
        elif args.command == 'annotations':
            _new_output(args.output)
            rows = export_forms(args.dataset, args.annotator, args.split)
            write_jsonl(args.output, rows)
            result = {'forms': len(rows), 'output': str(args.output)}
        elif args.command == 'freeze-references':
            snapshot = freeze_references(args.dataset, args.author, args.output, args.secondary, args.adjudications)
            result = {'reference_hash': snapshot['reference_hash'], 'references': len(snapshot['references'])}
        elif args.command == 'pairs':
            _new_output(args.output)
            rows = make_pairs(args.dataset, args.references, args.split)
            write_json(args.output, rows)
            result = {'pairs': len(rows)}
        elif args.command == 'calibrate':
            calibration = calibrate_threshold(args.dataset, args.references, args.results, SplitRegistry(args.registry))
            exclusive_json(args.output, calibration)
            result = {'threshold': calibration['configuration']['threshold'], 'pilot_f1_fail': calibration['pilot_f1_fail']}
        elif args.command == 'freeze':
            config = JudgeConfig.model_validate(read_json(args.config))
            frozen = freeze_experiment(args.dataset, args.references, config, args.output,
                                       SplitRegistry(args.registry), read_json(args.calibration) if args.calibration else None)
            result = {'freeze_hash': frozen['freeze_hash']}
        elif args.command == 'run':
            config = JudgeConfig.model_validate(read_json(args.config))
            key = os.environ.get(args.api_key_env)
            if not key:
                raise ValueError('Brak klucza w wskazanej zmiennej środowiskowej')
            with httpx.Client(headers={'Authorization': f'Bearer {key}'}, follow_redirects=False, trust_env=False) as client:
                result = run_batch(args.dataset, args.output, config, HTTPJudge(client), SplitRegistry(args.registry),
                                   args.split, args.frozen, args.pairs)
        elif args.command == 'report':
            _new_output(args.output)
            summary = report(args.dataset, args.references, args.results, args.frozen)
            args.output.mkdir()
            write_json(args.output / 'report.json', summary)
            with (args.output / 'metrics.csv').open('w', encoding='utf-8', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['metric', 'value'])
                for k, v in summary['metrics'].items():
                    writer.writerow([k, json.dumps(v, ensure_ascii=False)])
            body = html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
            (args.output / 'report.html').write_text(
                '<!doctype html><html lang="pl"><meta charset="utf-8"><title>TraceGuard: raport</title>'
                '<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:1rem}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>TraceGuard: raport zapisanych ocen</h1>'
                f'<pre>{body}</pre></html>', encoding='utf-8')
            result = {'output': str(args.output), 'metrics': summary['metrics']}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        # ValidationError includes rejected inputs. Do not print external values or credentials.
        if isinstance(exc, FileExistsError):
            message = 'Plik lub katalog wyjściowy już istnieje. Wybierz nową ścieżkę.'
        elif isinstance(exc, FileNotFoundError):
            message = 'Nie znaleziono wymaganego pliku lub katalogu.'
        elif type(exc).__name__ == 'ValidationError':
            message = 'Dane nie spełniają wymaganego schematu.'
        elif isinstance(exc, ValueError):
            message = str(exc)
        else:
            message = 'Nieprawidłowe dane albo błąd dostępu do pliku.'
        print(f'Błąd: {message}', file=sys.stderr)
        return 2
