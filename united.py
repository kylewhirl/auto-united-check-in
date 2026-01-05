#!/usr/bin/env python3
"""Simple entrypoint for checking in to United flights.

This script launches a Chromium browser using SeleniumBase and submits the
check-in form at https://www.united.com/en/us/checkin.
"""

from __future__ import annotations

import argparse
import sys

from lib.united_checkin import UnitedCheckIn, UnitedCheckInScheduler

__version__ = "v0.1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automatically open the United check-in page and submit the "
            "confirmation and name details."
        )
    )
    parser.add_argument(
        "confirmation_number",
        help="United confirmation number (six characters)",
    )
    parser.add_argument("last_name", help="Passenger last name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate arguments and print the actions without launching the "
            "browser."
        ),
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help=(
            "Run the browser in headed mode. The default is headless to make "
            "automation smoother on servers."
        ),
    )
    return parser


def init(arguments: list[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(arguments)

    if args.dry_run:
        print(
            "[DRY RUN] Would look up trip details for "
            f"{args.last_name} with confirmation "
            f"{args.confirmation_number} and schedule check-ins 24 hours "
            "before departure (submitting immediately if the window is open)."
        )
        return

    scheduler = UnitedCheckInScheduler(headed=args.headed)
    scheduler.schedule_checkins(args.confirmation_number, args.last_name)


if __name__ == "__main__":
    init(sys.argv[1:])
