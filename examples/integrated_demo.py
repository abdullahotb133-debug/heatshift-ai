"""Run from repository root: PYTHONPATH=src python examples/integrated_demo.py"""
from heatshift_ai import IntegratedSimulationEngine, EngineCommand

engine=IntegratedSimulationEngine()
engine.initialize()
worker=next(w for w in engine.get_state().simulation.workers if w.current_task_id)
engine.tick(10)
engine.execute(EngineCommand(action='start_rest',worker_id=worker.worker_id,zone_id='REST_ZONE',reason='explicit demo break'))
engine.tick(10)
print(engine.export_snapshot())
