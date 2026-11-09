from collections import Counter
from pathlib import Path

from traceguard_core.dataset import read_json
from traceguard_core.models import Profile, Rubric, Scenario

V2_CONFIGS = Path('configs/gsn-v2')


def test_v2_catalog_matches_research_sizes_and_stratifies_families():
    profile = Profile.model_validate(read_json(V2_CONFIGS / 'gsn.json'))
    scenarios = [Scenario.model_validate(row) for row in read_json(V2_CONFIGS / 'scenarios.json')]
    assert (profile.profile_id, profile.scenarios, profile.trajectories) == ('gsn-v2', 30, 150)
    assert (profile.correct_per_scenario, profile.incorrect_per_scenario) == (2, 3)
    assert (profile.pilot_size, profile.test_size, profile.score_min, profile.score_max) == (100, 50, 1, 10)
    families = {'configuration', 'network', 'security', 'capacity', 'runtime'}
    assert Counter(s.family for s in scenarios) == dict.fromkeys(families, 6)
    assert Counter((s.family, s.split) for s in scenarios) == {
        (family, split): count for family in families for split, count in [('pilot', 4), ('test', 2)]}
    assert len({s.scenario_id for s in scenarios}) == len({s.template_group for s in scenarios}) == 30
    for scenario in scenarios:
        assert scenario.initial_config.keys() == scenario.required_config.keys()
        assert scenario.initial_config != scenario.required_config
        assert scenario.service in scenario.task
        assert scenario.activation in scenario.task


def test_v2_preserves_shared_template_splits_and_rubric():
    old = {s['template_group']: s for s in read_json(Path('configs/scenarios.json'))}
    new = {s['template_group']: s for s in read_json(V2_CONFIGS / 'scenarios.json')}
    assert len(old.keys() & new.keys()) == 12
    for group in old.keys() & new.keys():
        assert new[group] == old[group]
    assert Rubric.model_validate(read_json(V2_CONFIGS / 'rubric.json')) == Rubric.model_validate(
        read_json(Path('configs/rubric.json')))
    pp = Profile.model_validate(read_json(Path('configs/pp.json')))
    assert (pp.scenarios, pp.trajectories, pp.pilot_size, pp.test_size, pp.score_max) == (30, 120, 80, 40, 5)
