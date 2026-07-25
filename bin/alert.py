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

from lib.alerting import (  # noqa: E402
    AlertConfigError,
    AlertStatus,
    DRIFT_UNITS_CSV_SEPARATOR,
    DRIFT_UNITS_FLAG,
    check_deadman,
    send_alert,
    send_drift_alert,
)

logger = get_logger("itsup.alert")

DRIFT_UNITS_HELP = "comma-separated units drifted from their delivered templates"
MUTUALLY_EXCLUSIVE_MODES_ERROR = "exactly one of <unit>, --deadman, or --drift-units is required"


def parse_args(argv: list[str]) -> tuple[str | None, bool, list[str] | None]:
    parser = argparse.ArgumentParser(description="Compose and dispatch an itsUP failure alert.")
    parser.add_argument("unit", nargs="?", default=None, help="the failed unit's identity")
    parser.add_argument("--deadman", action="store_true", help="run the apply deadman assertion instead")
    parser.add_argument(
        DRIFT_UNITS_FLAG,
        default=None,
        help=DRIFT_UNITS_HELP,
    )
    args = parser.parse_args(argv)

    modes_selected = sum([bool(args.unit), args.deadman, bool(args.drift_units)])
    if modes_selected != 1:
        parser.error(MUTUALLY_EXCLUSIVE_MODES_ERROR)

    drift_units = args.drift_units.split(DRIFT_UNITS_CSV_SEPARATOR) if args.drift_units else None
    return args.unit, args.deadman, drift_units


def main(argv: list[str] | None = None) -> int:
    unit, deadman, drift_units = parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging("itsup", source="alert")

    try:
        if deadman:
            outcome = check_deadman()
        elif drift_units is not None:
            outcome = send_drift_alert(drift_units)
        else:
            assert unit is not None  # parse_args requires <unit> when --deadman/--drift-units absent
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
