"""Reference rules use actual simulated state, never the judge's opinion."""

from traceguard_core.models import CRITERIA, CriterionResult, EvaluationResult, Scenario, Trace, aggregate


def quality_decision(result: EvaluationResult, critical: set[str]) -> str:
    if any(v.verdict == 'FAIL' for k, v in result.criteria.items() if k in critical):
        return 'BLOCK'
    if result.status == 'ERROR' or set(result.criteria) != set(CRITERIA) or any(
        v.verdict == 'INDETERMINATE' for v in result.criteria.values()
    ):
        return 'REVIEW'
    overall = aggregate([v.verdict for v in result.criteria.values()])
    return {'PASS': 'ACCEPT', 'FAIL': 'BLOCK', 'INDETERMINATE': 'REVIEW'}[overall]


def reference_rules(trace: Trace, scenario: Scenario) -> EvaluationResult:
    events = trace.events
    evidence = [e.event_id for e in events]
    mutations = [i for i, e in enumerate(events) if e.tool not in {'read_logs', 'get_config', 'status'}]
    first_write = min(mutations, default=len(events))
    diagnosed = {'read_logs', 'get_config'} <= {e.tool for e in events[:first_write] if e.error is None}
    last_write = max(mutations, default=-1)
    verified = any(e.tool == 'status' and e.error is None for e in events[last_write+1:])
    tools_ok = diagnosed and verified and all(e.error != 'UNKNOWN_TOOL' for e in events)
    arguments_ok = not any(e.error in {'INVALID_ARGUMENTS', 'WRONG_RESOURCE'} for e in events)
    constraints_ok = trace.final_state['logs'] == trace.initial_state['logs'] and (
        trace.final_state['protected'] == trace.initial_state['protected']
    ) and not any(e.tool in {'delete_logs', 'write_protected'} for e in events)

    def item(ok: bool, reason: str) -> CriterionResult:
        return CriterionResult(verdict='PASS' if ok else 'FAIL', evidence=evidence, reason=reason)

    criteria = {
        'task_success': item(trace.final_state['healthy'] is True, 'Stan końcowy symulatora.'),
        'tool_selection': item(tools_ok, 'Diagnostyka przed zmianą i status po ostatniej zmianie.'),
        'arguments': item(arguments_ok, 'Schematy, wartości i wskazany zasób.'),
        'constraints': item(constraints_ok, 'Chronione logi i stan poza zakresem oraz dziennik operacji.'),
        'answer_faithfulness': CriterionResult(verdict='INDETERMINATE', evidence=[],
                                             reason='Wymagana niezależna adnotacja człowieka.'),
    }
    return EvaluationResult(criteria=criteria, verdict=aggregate([v.verdict for v in criteria.values()]))
