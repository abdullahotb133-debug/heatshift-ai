"""Offline synthetic snapshot CLI. Real environment integration is not available."""
import argparse
from pathlib import Path
from .scenarios import ScenarioController, ScenarioName, SyntheticScenarioAdapter
from .snapshots import build_snapshot, export_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=[x.value for x in ScenarioName], default='NORMAL')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--ticks', type=int, default=5)
    parser.add_argument('--tick-seconds', type=int, default=10)
    parser.add_argument('--simulation-id', default='SIM-001')
    parser.add_argument('--output', type=Path, help='Final JSON snapshot file; omit for stdout')
    args = parser.parse_args()
    try:
        controller = ScenarioController(args.scenario, seed=args.seed, tick_seconds=args.tick_seconds,
                                        adapter_factory=SyntheticScenarioAdapter)
        controller.run(args.ticks)
        text = export_snapshot(build_snapshot(controller, simulation_id=args.simulation_id))
        if args.output:
            args.output.write_text(text + '\n', encoding='utf-8')
        else:
            print(text)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
