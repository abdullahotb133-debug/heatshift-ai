from dataclasses import replace
import json
import pytest
from heatshift_ai import (SimulationState, Task, Worker, WorkerStateManager, Zone, to_json)


def initial():
    return SimulationState(
        zones=tuple(Zone(zone_id=z, kind=k) for z,k in [('A','work'),('B','work'),('C','work'),('R','rest'),('R2','rest')]),
        workers=(Worker(worker_id='W', display_name='Fictional Worker', current_zone_id='A', qualifications=frozenset({'skill'})),),
        tasks=tuple(Task(task_id=t, task_name=t, workload_category='light',
                         required_qualifications=frozenset({q}), allowed_zone_ids=frozenset({'A','B'}))
                    for t,q in [('T1','skill'),('T2','skill'),('T3','missing')]))


def manager(working=False):
    m=WorkerStateManager(initial())
    m.assign_task(worker_id='W', task_id='T1')
    if working:
        m.start_work(worker_id='W', reason='shift start')
    return m


def test_one_worker_start_event():
    m=manager()
    before=m.state
    m.start_work(worker_id='W', reason='operator request')
    event=m.events[-1]
    assert event.old_state is before and event.new_state is m.state
    assert event.action == 'start_work' and event.reason == 'operator request'
    assert event.elapsed_seconds == 0 and event.worker_id == 'W'
    assert m.state.workers[0].work_status == 'working'
    assert m.state.tasks[0].task_status == 'in_progress'


def test_all_actions_history_and_events():
    m=manager(True)
    m.tick(10)
    for action,kwargs in [
        ('change_zone', {'zone_id':'B'}), ('change_task', {'task_id':'T2'}),
        ('stop_work', {}), ('start_rest', {'zone_id':'R'}),
        ('change_zone', {'zone_id':'R2'}), ('end_rest', {}),
        ('mark_unavailable', {}), ('mark_available', {}),
    ]:
        count=len(m.events)
        getattr(m,action)(worker_id='W', reason='test operation', **kwargs)
        assert len(m.events)==count+1 and m.events[-1].action==action
        assert m.events[-1].elapsed_seconds==m.state.time.elapsed_seconds
        assert m.state.workers[0].exposure_elapsed_seconds==10
        replace(m.state)  # all cross-entity invariants still enforced
        if action=='change_task':
            assert m.state.workers[0].current_work_period_seconds==10
            assert m.state.tasks[0].task_status=='pending'
            assert m.state.tasks[1].task_status=='in_progress'
        if action=='start_rest':
            m.tick(5)
    assert m.state.workers[0].rest_elapsed_seconds==5
    assert m.state.workers[0].current_rest_period_seconds==0
    assert m.state.workers[0].current_work_period_seconds==0
    data=json.loads(m.export_events_json())
    assert all(e['data_origin']=='simulated' for e in data)
    assert [e['event_id'] for e in data]==list(range(1,len(data)+1))


@pytest.mark.parametrize('action,kwargs', [
    ('start_work',{}), ('change_zone',{'zone_id':'R'}), ('change_zone',{'zone_id':'C'}),
    ('change_zone',{'zone_id':'UNKNOWN'}), ('change_zone',{'zone_id':'A'}),
    ('change_task',{'task_id':'T3'}), ('change_task',{'task_id':'UNKNOWN'}),
    ('change_task',{'task_id':'T1'}), ('start_rest',{'zone_id':'A'}),
    ('end_rest',{}), ('mark_available',{}),
])
def test_rejection_atomic_including_candidate_release(action,kwargs):
    m=manager(True)
    m.tick()
    before=m.state
    events=m.events
    text=to_json(before)
    with pytest.raises(ValueError):
        getattr(m,action)(worker_id='W',reason='invalid',**kwargs)
    assert m.state is before and to_json(m.state)==text
    assert m.events is events


@pytest.mark.parametrize('active', [False, True])
def test_unavailable_and_rest_release_reserved_or_working(active):
    for action,kwargs in [('mark_unavailable',{}),('start_rest',{'zone_id':'R'})]:
        m=manager(active)
        m.tick()
        count=len(m.events)
        getattr(m,action)(worker_id='W',reason='explicit request',**kwargs)
        assert len(m.events)==count+1
        assert m.state.assignments==()
        assert m.state.tasks[0].task_status=='pending'
        assert m.state.tasks[0].assigned_worker_id is None
        assert m.state.workers[0].current_task_id is None
        assert m.state.workers[0].availability_status=='unavailable'
        assert m.state.workers[0].exposure_elapsed_seconds==(10 if active else 0)


def test_rest_restrictions_and_history():
    m=manager(True)
    m.tick(7)
    m.start_rest(worker_id='W',zone_id='R',reason='break')
    m.tick(3)
    for action,kwargs in [('start_work',{}),('mark_available',{}),('start_rest',{'zone_id':'R'}),
                         ('change_zone',{'zone_id':'A'}),('change_task',{'task_id':'T2'})]:
        before=m.state
        events=m.events
        with pytest.raises(ValueError):
            getattr(m,action)(worker_id='W',reason='invalid',**kwargs)
        assert m.state is before and m.events is events
    m.change_zone(worker_id='W',zone_id='R2',reason='move rest area')
    assert m.state.workers[0].current_rest_period_seconds==3
    m.end_rest(worker_id='W',reason='return')
    m.assign_task(worker_id='W',task_id='T2',zone_id='B')
    m.start_work(worker_id='W',reason='resume')
    m.tick(2)
    w=m.state.workers[0]
    assert (w.work_elapsed_seconds,w.rest_elapsed_seconds,w.current_work_period_seconds)==(9,3,2)


def test_no_assignment_unavailable_and_reason_rejections():
    m=WorkerStateManager(initial())
    for action in ('start_work','stop_work','change_task'):
        with pytest.raises(ValueError):
            getattr(m,action)(worker_id='W',reason='invalid',**({'task_id':'T2'} if action=='change_task' else {}))
    before=m.state
    with pytest.raises(ValueError,match='reason'):
        m.mark_unavailable(worker_id='W',reason=' ')
    with pytest.raises(ValueError,match='unknown worker'):
        m.mark_unavailable(worker_id='MISSING',reason='request')
    assert m.state is before and m.events==()
    m.mark_unavailable(worker_id='W',reason='off duty')
    for action,kwargs in [('assign_task',{'task_id':'T1'}),('mark_unavailable',{})]:
        before=m.state
        events=m.events
        with pytest.raises(ValueError):
            getattr(m,action)(worker_id='W',reason='request',**kwargs)
        assert m.state is before and m.events is events


def test_legacy_entry_points_emit_events_reset_and_determinism():
    def run():
        m=manager()
        m.start_task(task_id='T1')
        m.tick(10)
        m.unassign_task(task_id='T1')
        return m
    a,b=run(),run()
    assert a.export_events_json()==b.export_events_json()
    assert a.events[-1].action=='unassign_task'
    a.pause()
    a.reset()
    assert a.events==() and not a.paused and a.state==initial()


def test_reserved_task_switch_remains_reserved_and_zone_history():
    m=manager()
    m.change_task(worker_id='W',task_id='T2',zone_id='B',reason='setup')
    assert m.state.workers[0].work_status=='idle'
    assert m.state.tasks[1].task_status=='assigned'
    m.start_work(worker_id='W',reason='start')
    m.tick(10)
    m.change_zone(worker_id='W',zone_id='A',reason='move')
    m.tick(5)
    assert m.state.workers[0].current_work_period_seconds==15
    assert m.state.assignments[0].zone_id=='A'


def test_event_build_failure_does_not_publish(monkeypatch):
    import heatshift_ai.transitions as module
    m=manager()
    before,events=m.state,m.events
    def fail(**kwargs):
        raise ValueError('event creation failed')
    monkeypatch.setattr(module,'TransitionEvent',fail)
    with pytest.raises(ValueError,match='event creation'):
        m.start_work(worker_id='W',reason='start')
    assert m.state is before and m.events is events
