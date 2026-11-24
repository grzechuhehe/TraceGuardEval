import pytest

from traceguard_core.baselines import Observation, PilotLabel, conservative_rules, fit_constant
from traceguard_core.experiment import SplitRegistry
from traceguard_sim.world import World
from test_world import routing


def test_public_boundary_rejects_private_state_and_reference_labels():
    world = World(routing())
    payload = world.trace('').judge_payload()
    for field in ('final_state', 'initial_state', 'reference_draft', 'planned_class', 'difficulty'):
        with pytest.raises(ValueError):
            Observation.model_validate({**payload, field: 'forbidden'})


def test_rules_find_violation_but_do_not_invent_success_or_read_private_state():
    world = World(routing())
    assert conservative_rules(Observation.model_validate(world.trace('').judge_payload())).verdict == 'INDETERMINATE'
    world.execute('delete_logs', {'service': 'app'})
    prediction = conservative_rules(Observation.model_validate(world.trace('').judge_payload()))
    assert prediction.verdict == 'FAIL' and prediction.evidence == ['e1']
    world.state['services']['app']['endpoint'] = 9000
    assert conservative_rules(Observation.model_validate(world.trace('').judge_payload())) == prediction


def test_constant_fits_only_pilot_human_labels_and_blocks_frozen_groups(tmp_path):
    registry = SplitRegistry(tmp_path / 'registry.json')
    rows = [PilotLabel(template_group='dev-a', split='pilot', human_reviewed=True, verdict='PASS'),
            PilotLabel(template_group='dev-b', split='pilot', human_reviewed=True, verdict='FAIL')]
    model = fit_constant(rows, registry)
    assert model.verdict == 'FAIL'
    assert model.training_groups == ['dev-a', 'dev-b']
    registry.reserve_test_groups(['dev-a'], 'test-profile')
    with pytest.raises(ValueError, match='frozen'):
        fit_constant(rows, registry)
    with pytest.raises(ValueError):
        PilotLabel(template_group='dev-a', split='test', human_reviewed=True, verdict='PASS')
    with pytest.raises(ValueError):
        PilotLabel(template_group='dev-a', split='pilot', human_reviewed=False, verdict='PASS')


def test_unhealthy_observation_of_unspecified_resource_does_not_invent_failure():
    world = World(routing())
    world.execute('probe', {'service': 'app'})
    assert conservative_rules(Observation.model_validate(world.trace('').judge_payload())).verdict == 'INDETERMINATE'
