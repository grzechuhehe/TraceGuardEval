"""Versioned data contracts. References live outside observable traces."""

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Verdict = Literal['PASS', 'FAIL', 'NA', 'INDETERMINATE']
CRITERIA = ('task_success', 'tool_selection', 'arguments', 'constraints', 'answer_faithfulness')


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, allow_inf_nan=False)


class Profile(Model):
    schema_version: Literal['1.0'] = '1.0'
    profile_id: str
    scenarios: int = Field(gt=0)
    trajectories: int = Field(gt=0)
    correct_per_scenario: int = Field(gt=0)
    incorrect_per_scenario: int = Field(gt=0)
    pilot_size: int = Field(gt=0)
    test_size: int = Field(gt=0)
    score_min: int = 1
    score_max: int = Field(gt=1)
    repeats: int = Field(gt=0)
    pairs: int = Field(ge=0)
    rubric_id: str
    rubric_version: str

    @model_validator(mode='after')
    def check_sizes(self) -> Self:
        per = self.correct_per_scenario + self.incorrect_per_scenario
        if self.trajectories != self.scenarios * per or self.pilot_size + self.test_size != self.trajectories:
            raise ValueError('Inconsistent dataset sizes')
        if self.pilot_size % per or self.test_size % per or self.score_min >= self.score_max:
            raise ValueError('Split must contain whole scenarios; score range must increase')
        return self


class CriterionResult(Model):
    verdict: Verdict
    evidence: list[str]
    reason: str = Field(min_length=1)


class CriterionDefinition(Model):
    criterion_id: Literal['task_success', 'tool_selection', 'arguments', 'constraints', 'answer_faithfulness']
    name: str = Field(min_length=1)
    pass_condition: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    critical: bool


class Rubric(Model):
    schema_version: Literal['1.0'] = '1.0'
    rubric_id: str
    version: str
    criteria: list[CriterionDefinition]
    aggregation: str
    na_policy: str

    @model_validator(mode='after')
    def complete_criteria(self) -> Self:
        keys = [c.criterion_id for c in self.criteria]
        if len(keys) != len(CRITERIA) or set(keys) != set(CRITERIA):
            raise ValueError('Rubric requires exactly five distinct incident criteria')
        return self


def aggregate(values: list[Verdict]) -> Verdict:
    applicable = [v for v in values if v != 'NA']
    if 'FAIL' in applicable:
        return 'FAIL'
    if not applicable or 'INDETERMINATE' in applicable:
        return 'INDETERMINATE'
    return 'PASS'


class EvaluationResult(Model):
    schema_version: Literal['1.0'] = '1.0'
    status: Literal['OK', 'ERROR'] = 'OK'
    criteria: dict[str, CriterionResult] = Field(default_factory=dict)
    verdict: Verdict = 'INDETERMINATE'
    score: float | None = None
    preference: Literal['A', 'B', 'TIE'] | None = None
    reason: str = ''
    evidence: list[str] = Field(default_factory=list)


class Event(Model):
    event_id: str
    tool: str
    arguments: dict[str, JsonValue]
    response: dict[str, JsonValue]
    error: str | None = None
    elapsed_ms: int = Field(ge=0)


class Trace(Model):
    schema_version: Literal['1.0'] = '1.0'
    trace_id: str
    scenario_id: str
    task: str
    initial_state: dict[str, JsonValue]
    events: list[Event]
    final_state: dict[str, JsonValue]
    final_answer: str
    elapsed_ms: int = Field(ge=0)
    agent_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def sequential_events(self) -> Self:
        if [e.event_id for e in self.events] != [f'e{i+1}' for i in range(len(self.events))]:
            raise ValueError('Event IDs must be sequential and unique')
        if self.elapsed_ms != sum(e.elapsed_ms for e in self.events):
            raise ValueError('Trace timing differs from event timing')
        return self

    def content_hash(self) -> str:
        return digest(self.model_dump(exclude={'trace_id'}))

    def judge_payload(self, final_only: bool = False) -> dict:
        payload = {'task': self.task, 'final_answer': self.final_answer}
        if not final_only:
            payload['events'] = [e.model_dump() for e in self.events]
        return payload


class Scenario(Model):
    scenario_id: str
    template_group: str
    family: str
    split: Literal['pilot', 'test']
    service: str
    title: str
    task: str
    initial_config: dict[str, JsonValue]
    required_config: dict[str, JsonValue]
    activation: Literal['restart', 'reload', 'start', 'reconnect', 'resume']
    log_message: str


class ManifestEntry(Model):
    trace_id: str
    scenario_id: str
    template_group: str
    split: Literal['pilot', 'test']


class Manifest(Model):
    schema_version: Literal['1.0'] = '1.0'
    dataset_id: str
    profile_id: str
    profile_hash: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    scenarios_hash: str
    entries: list[ManifestEntry]
