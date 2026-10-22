"""Run an explicitly synthetic demo; never connects to a real environment simulator."""
import argparse
from heatshift_ai import ScenarioController, ScenarioName, SyntheticScenarioAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=[s.value for s in ScenarioName])
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--ticks', type=int, default=5)
    parser.add_argument('--tick-seconds', type=int, default=10)
    args = parser.parse_args()
    try:
        controller = ScenarioController(args.scenario, seed=args.seed, tick_seconds=args.tick_seconds,
                                        adapter_factory=SyntheticScenarioAdapter)
        controller.run(args.ticks)
    except ValueError as exc:
        parser.error(str(exc))
    print(controller.export_json())


if __name__ == '__main__':
    main()
