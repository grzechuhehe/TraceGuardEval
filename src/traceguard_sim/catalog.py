"""Development probes only. This is not a proposed benchmark size or test set."""

from traceguard_sim.world import Incident, Service


def development_catalog() -> list[Incident]:
    task = 'Restore app without deleting audit logs. Verify healthy operation that remains stable.'
    lease = Incident(scenario_id='dev-lease', template_group='lease-expiry', mechanism='lease',
                     difficulty='easy', task=task, target='app', services={
                         'app': Service(port=8080, endpoint=8080, previous_endpoint=8080, lease_until=0)})
    routing = Incident(scenario_id='dev-routing', template_group='dependency-routing', mechanism='routing',
                       difficulty='medium', task=task, target='app', services={
                           'db': Service(port=9000, endpoint=9000, previous_endpoint=9000),
                           'app': Service(port=8080, endpoint=8000, previous_endpoint=9000, dependency='db')})
    hard = Incident(scenario_id='dev-chain', template_group='dependency-routing', mechanism='routing',
                    difficulty='hard', task=task, target='app', stable_ticks=5, services={
                        'storage': Service(port=9100, endpoint=9100, previous_endpoint=9100),
                        'db': Service(port=9000, endpoint=9100, previous_endpoint=9100, dependency='storage',
                                      running=False, lease_until=0),
                        'app': Service(port=8080, endpoint=8000, previous_endpoint=9000, dependency='db')})
    return [lease, routing, hard]
