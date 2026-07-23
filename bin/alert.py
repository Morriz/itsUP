"""Entry point for itsUP's failure-alert composer.

Invoked by the `itsup-alert@%i.service` template on a covered unit's
`OnFailure=` hook (%i = the failed unit's identity), or by
`bin/pi-healthcheck.sh` for the apply deadman assertion (`--deadman`).

`lib/alerting.py` never emits an operator-facing line — this entry layer owns
that split (`project/design/logging`): diagnostics route to the per-source log
file, and the supervisor-facing outcome is printed so it reaches the journal.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from instrukt_ai_logging import configure_logging, get_logger  # noqa: E402

from lib.alerting import AlertConfigError, AlertStatus, check_deadman, send_alert  # noqa: E402

logger = get_logger("itsup.alert")


def parse_args(argv: list[str]) -> tuple[str | None, bool]:
    parser = argparse.ArgumentParser(description="Compose and dispatch an itsUP failure alert.")
    parser.add_argument("unit", nargs="?", default=None, help="the failed unit's identity")
    parser.add_argument("--deadman", action="store_true", help="run the apply deadman assertion instead")
    args = parser.parse_args(argv)

    if args.deadman and args.unit:
        parser.error("<unit> and --deadman are mutually exclusive")
    if not args.deadman and not args.unit:
        parser.error("either <unit> or --deadman is required")

    return args.unit, args.deadman


def main(argv: list[str] | None = None) -> int:
    unit, deadman = parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging("itsup", source="alert")

    try:
        if deadman:
            outcome = check_deadman()
        else:
            assert unit is not None  # parse_args requires <unit> when --deadman is absent
            outcome = send_alert(unit)
    except AlertConfigError as exc:
        logger.error("alert: %s", exc)
        print(f"alert: {exc}", file=sys.stderr)
        return 1

    if outcome.status == AlertStatus.FAILED:
        logger.error("alert: %s", outcome.detail)
        print(f"alert: {outcome.detail}", file=sys.stderr)
        return 1

    print(f"alert: {outcome.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
