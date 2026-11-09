import pytest

from traceguard_core.analysis import classification_metrics, agreement, pairwise_metrics, stability


def test_fail_is_positive_and_unresolved_does_not_disappear():
    refs = {'a': {'verdict': 'FAIL', 'critical_fail': True}, 'b': {'verdict': 'FAIL', 'critical_fail': True},
            'c': {'verdict': 'PASS'}, 'd': {'verdict': 'PASS'}, 'e': {'verdict': 'FAIL'}}
    predictions = [
        {'trace_id': k, 'prediction': {'verdict': v, 'status': s}}
        for k, v, s in [('a', 'FAIL', 'OK'), ('b', 'PASS', 'OK'), ('c', 'FAIL', 'OK'),
                         ('d', 'PASS', 'OK'), ('e', 'INDETERMINATE', 'ERROR')]]
    m = classification_metrics(predictions, refs, expected=6)
    assert m['confusion_fail_positive'] == {'tp': 1, 'fp': 1, 'fn': 1, 'tn': 1}
    assert m['precision_fail'] == m['recall_fail'] == m['f1_fail'] == m['accuracy'] == 0.5
    assert m['coverage'] == pytest.approx(4 / 6)
    assert m['error'] == 1 and m['missing'] == 1 and m['missed_critical'] == 1


def test_undefined_metrics_are_not_invented():
    m = classification_metrics([], {}, expected=0)
    assert m['accuracy'] is None and m['f1_fail'] is None and m['coverage'] is None


def test_agreement_preserves_sample_size_and_undefined_kappa():
    assert agreement(['PASS', 'FAIL'], ['PASS', 'PASS']) == {'n': 2, 'agreement': 0.5, 'kappa': 0.0}
    assert agreement(['PASS'], ['PASS'])['kappa'] is None


def test_stability_requires_all_three_repeats():
    rows = [{'unit_id': 'a', 'orientation': 'single', 'repeat_id': i,
             'prediction': {'status': 'OK', 'verdict': 'PASS'}} for i in range(3)]
    rows.append({'unit_id': 'b', 'orientation': 'single', 'repeat_id': 0,
                 'prediction': {'status': 'OK', 'verdict': 'FAIL'}})
    assert stability(rows, 3) == {'groups': 2, 'complete_groups': 1, 'incomplete_groups': 1,
                                  'stable_groups': 1, 'stability': 1.0}


def test_pairwise_normalizes_swapped_order_and_counts_missing():
    pairs = [{'pair_id': 'p', 'reference': 'A'}]
    rows = [{'unit_id': 'p', 'orientation': orientation, 'repeat_id': 0,
             'prediction': {'status': 'OK', 'preference': preference}}
            for orientation, preference in [('AB', 'A'), ('BA', 'A')]]
    metrics = pairwise_metrics(rows, pairs, repeats=3)
    assert metrics['agreement'] == 0.5
    assert metrics['position_flips'] == 1 and metrics['complete_swaps'] == 1
    assert metrics['missing'] == 4
