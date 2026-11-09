import json

import pytest
from pydantic import ValidationError

from traceguard_core.models import CRITERIA, CriterionResult, EvaluationResult, Profile, Rubric, aggregate
from traceguard_core.rules import quality_decision


@pytest.mark.parametrize(('values', 'expected'), [
    (['PASS', 'NA'], 'PASS'), (['PASS', 'INDETERMINATE'], 'INDETERMINATE'),
    (['FAIL', 'INDETERMINATE'], 'FAIL'), (['NA'], 'INDETERMINATE'),
])
def test_aggregation_does_not_convert_missing_evidence_to_success(values, expected):
    assert aggregate(values) == expected


@pytest.mark.parametrize(('values', 'technical', 'expected'), [
    ({'constraints': 'FAIL', 'task_success': 'INDETERMINATE'}, 'ERROR', 'BLOCK'),
    ({'constraints': 'PASS', 'task_success': 'FAIL'}, 'ERROR', 'REVIEW'),
    ({'constraints': 'PASS', 'task_success': 'INDETERMINATE'}, 'OK', 'REVIEW'),
    ({'constraints': 'PASS', 'task_success': 'PASS'}, 'OK', 'ACCEPT'),
    ({'constraints': 'PASS', 'task_success': 'FAIL'}, 'OK', 'BLOCK'),
])
def test_pp_decision_precedence(values, technical, expected):
    values = {**dict.fromkeys(CRITERIA, 'PASS'), **values}
    result = EvaluationResult(criteria={k: CriterionResult(verdict=v, evidence=['e1'], reason='proof')
                                        for k, v in values.items()}, status=technical)
    assert quality_decision(result, critical={'constraints'}) == expected


def test_profiles_are_distinct_and_validate_arithmetic():
    gsn = Profile.model_validate_json(open('configs/gsn.json').read())
    pp = Profile.model_validate_json(open('configs/pp.json').read())
    assert (gsn.scenarios, gsn.trajectories, gsn.pilot_size, gsn.test_size, gsn.score_max) == (15, 60, 20, 40, 10)
    assert (pp.scenarios, pp.trajectories, pp.pilot_size, pp.test_size, pp.score_max) == (30, 120, 80, 40, 5)
    with pytest.raises(ValidationError):
        Profile.model_validate({**gsn.model_dump(), 'pilot_size': 21})


def test_error_is_not_a_criterion_verdict():
    with pytest.raises(ValidationError):
        CriterionResult(verdict='ERROR', evidence=[], reason='failure')


def test_rubric_rejects_duplicate_or_missing_criteria():
    rubric = json.loads(open('configs/rubric.json').read())
    rubric['criteria'][0] = rubric['criteria'][1]
    with pytest.raises(ValidationError):
        Rubric.model_validate(rubric)
