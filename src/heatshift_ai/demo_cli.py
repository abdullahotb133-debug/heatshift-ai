"""Engineering scenario CLI; all observations are synthetic, no B/C integration."""
import argparse
from dataclasses import replace
from pathlib import Path
import json
from .engineering_scenarios import EngineeringScenarioName, EngineeringScenarioRunner, load_scenario
from .serialization import to_json_value
from .integrated_engine import EngineConfig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',choices=[s.value for s in EngineeringScenarioName],default='NORMAL_OPERATION')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--ticks',type=int,default=12)
    parser.add_argument('--tick-seconds',type=int,default=10)
    parser.add_argument('--failure-mode',choices=('missing','stale','invalid'),default=None)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--events-output',type=Path)
    args=parser.parse_args()
    try:
        definition=load_scenario(args.scenario,seed=args.seed)
        if args.failure_mode:
            if definition.scenario_id!=EngineeringScenarioName.SENSOR_FAILURE:
                raise ValueError('--failure-mode requires SENSOR_FAILURE')
            definition=replace(definition,failure_mode=args.failure_mode)
        runner=EngineeringScenarioRunner(definition,config=EngineConfig(seed=args.seed,tick_seconds=args.tick_seconds))
        runner.start(); runner.run(args.ticks)
        output=runner.export_snapshot()
        if args.output: args.output.write_text(output+'\n')
        else: print(output)
        if args.events_output:
            args.events_output.write_text(json.dumps({'scenario_events':to_json_value(runner.events),
                'worker_events':to_json_value(runner.engine.get_state().events)},indent=2,allow_nan=False)+'\n')
    except (ValueError,OSError) as exc: parser.error(str(exc))


if __name__=='__main__': main()
