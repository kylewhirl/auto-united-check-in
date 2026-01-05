from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Sequence

from seleniumbase import Driver

from .log import LOGS_DIRECTORY, get_logger
from .utils import get_current_time

CHECKIN_URL = "https://www.united.com/en/us/checkin"
MANAGE_TRIP_URL = "https://www.united.com/en/us/manageres/mytrips"

logger = get_logger(__name__)


@dataclass
class FlightSegment:
    departure_time: datetime
    departure_airport: str
    arrival_airport: str

    def checkin_time(self) -> datetime:
        return self.departure_time - timedelta(days=1)

    def display_time(self) -> str:
        return self.departure_time.strftime("%Y-%m-%d %I:%M %p %Z")


@dataclass
class UnitedCheckIn:
    """Automates the United check-in form using SeleniumBase."""

    headed: bool = False

    def submit(self, confirmation_number: str, last_name: str) -> None:
        """Launch the check-in page and fill out the form."""
        logger.info("Starting United check-in for %s", last_name)
        driver = Driver(
            uc=True,
            headless2=not self.headed,
            headed=self.headed,
            incognito=True,
        )

        try:
            driver.get(CHECKIN_URL)
            self._fill_field(
                driver,
                ["#flightCheckInConfNumber", "input[name='confirmationNumberModel.number']"],
                confirmation_number,
            )
            self._fill_field(
                driver,
                ["#flightCheckInLastName", "input[name='confirmationNumberModel.lastName']"],
                last_name,
            )

            logger.debug("Submitting United check-in form")
            with contextlib.suppress(Exception):
                driver.click('button[type="submit"]')

            # Give the site a moment to respond; a screenshot can help debug issues
            time.sleep(5)
            Path(LOGS_DIRECTORY).mkdir(exist_ok=True)
            driver.save_screenshot(Path(LOGS_DIRECTORY) / "united-checkin.png")
            logger.info("Check-in attempt submitted; screenshot saved to logs directory")
        finally:
            driver.quit()

    def _fill_field(
        self, driver: Driver, selector: str | Sequence[str], value: str | None
    ) -> None:
        if not value:
            return

        selectors = (selector,) if isinstance(selector, str) else selector

        for candidate in selectors:
            try:
                driver.wait_for_element_visible(candidate, timeout=15)
                driver.type(candidate, value)
                return
            except Exception:
                logger.debug(
                    "Could not locate field %s on the United check-in page", candidate
                )

        logger.warning(
            "Unable to locate any check-in field from selectors: %s", selectors
        )


class UnitedTripScraper:
    """Pulls flight information from United's "Manage Trip" flow."""

    def __init__(self, headed: bool = False) -> None:
        self.headed = headed
        self._timezone = datetime.now().astimezone().tzinfo

    def fetch_segments(self, confirmation_number: str, last_name: str) -> list[FlightSegment]:
        logger.info("Fetching trip details to schedule check-ins")
        driver = Driver(
            uc=True,
            headless2=not self.headed,
            headed=self.headed,
            incognito=True,
        )

        try:
            driver.get(MANAGE_TRIP_URL)
            self._fill_field(
                driver,
                [
                    "input[name='confirmationNumber']",
                    "input[name='confirmationNumberModel.number']",
                    "#flightCheckInConfNumber",
                ],
                confirmation_number,
            )
            self._fill_field(
                driver,
                [
                    "input[name='lastName']",
                    "input[name='confirmationNumberModel.lastName']",
                    "#flightCheckInLastName",
                ],
                last_name,
            )

            with contextlib.suppress(Exception):
                driver.click('button[type="submit"]')

            segments_container = (
                "div.app-containers-TripDetails-FlightSegmentsContainer-"
                "flightSegmentsContainer__flightBlockSingle--HzR1s"
            )
            driver.wait_for_element_visible(segments_container, timeout=30)

            segments: list[FlightSegment] = []
            wrappers = driver.find_elements(
                "css selector",
                "div.app-containers-TripDetails-SingleFlight-singleFlight__flightWrapper--bvJSe",
            )

            for wrapper in wrappers:
                try:
                    segments.append(self._parse_segment(wrapper))
                except Exception:
                    logger.warning("Failed to parse a flight segment from the page")

            logger.info("Found %d flight segment(s)", len(segments))
            return segments
        finally:
            driver.quit()

    def _parse_segment(self, wrapper: any) -> FlightSegment:  # pragma: no cover - heavy UI calls
        date_text = self._safe_text(
            wrapper.find_element(
                "css selector",
                "p[class*='departureDate'] span",
            )
        )
        time_text = self._safe_text(
            wrapper.find_element(
                "css selector",
                "p[class*='departureTime'] span",
            )
        )

        departure_airport = self._safe_text(
            wrapper.find_element(
                "css selector",
                "div[class*='departure'] span.atm-u-typography-preset-2--bold",
            )
        )
        arrival_airport = self._safe_text(
            wrapper.find_element(
                "css selector",
                "div[class*='arrival'] span.atm-u-typography-preset-2--bold",
            )
        )

        departure_time = self._parse_departure_time(date_text, time_text)
        logger.debug(
            "Segment parsed: %s to %s departing %s",
            departure_airport,
            arrival_airport,
            departure_time,
        )
        return FlightSegment(departure_time, departure_airport, arrival_airport)

    def _fill_field(self, driver: Driver, selector: str, value: str) -> None:
        driver.wait_for_element_visible(selector, timeout=20)
        driver.type(selector, value)

    def _parse_departure_time(self, date_text: str, time_text: str) -> datetime:
        date_obj = datetime.strptime(date_text.strip(), "%a, %b %d, %Y").date()
        time_obj = datetime.strptime(time_text.strip(), "%I:%M %p").time()
        return datetime.combine(date_obj, time_obj, tzinfo=self._timezone)

    @staticmethod
    def _safe_text(element: any) -> str:
        return element.text.strip()


class UnitedCheckInScheduler:
    """Schedules check-ins 24 hours before each United flight segment."""

    def __init__(self, headed: bool = False) -> None:
        self.headed = headed
        self.checkin = UnitedCheckIn(headed=headed)
        self.scraper = UnitedTripScraper(headed=headed)
        self._threads: list[Thread] = []

    def schedule_checkins(self, confirmation_number: str, last_name: str) -> None:
        try:
            segments = self.scraper.fetch_segments(confirmation_number, last_name)
        except Exception:
            logger.exception(
                "Failed to fetch trip details; attempting immediate check-in instead"
            )
            self._attempt_submit(confirmation_number, last_name)
            return

        if not segments:
            logger.warning(
                "No segments found; attempting immediate check-in instead"
            )
            self._attempt_submit(confirmation_number, last_name)
            return

        for segment in segments:
            self._schedule_segment(segment, confirmation_number, last_name)

        for thread in self._threads:
            thread.join()

    def _schedule_segment(
        self,
        segment: FlightSegment,
        confirmation_number: str,
        last_name: str,
    ) -> None:
        checkin_time = segment.checkin_time()
        now = get_current_time().astimezone(checkin_time.tzinfo)
        delay = (checkin_time - now).total_seconds()

        if delay <= 0:
            logger.info(
                "Check-in window already open; submitting for %s -> %s",
                segment.departure_airport,
                segment.arrival_airport,
            )
            self.checkin.submit(confirmation_number, last_name)
            return

        logger.info(
            "Scheduling check-in for %s -> %s at %s",
            segment.departure_airport,
            segment.arrival_airport,
            checkin_time.strftime("%Y-%m-%d %I:%M %p %Z"),
        )

        thread = Thread(
            target=self._sleep_and_checkin,
            args=(delay, confirmation_number, last_name),
            daemon=False,
        )
        thread.start()
        self._threads.append(thread)

    def _sleep_and_checkin(
        self, delay: float, confirmation_number: str, last_name: str
    ) -> None:
        self._safe_sleep(delay)
        self.checkin.submit(confirmation_number, last_name)

    @staticmethod
    def _safe_sleep(delay: float) -> None:
        # mirror long-sleep behavior from Southwest scheduling
        two_weeks = 60 * 60 * 24 * 14
        while delay > 0:
            sleep_time = min(delay, two_weeks)
            time.sleep(sleep_time)
            delay -= sleep_time

    def _attempt_submit(self, confirmation_number: str, last_name: str) -> None:
        try:
            self.checkin.submit(confirmation_number, last_name)
        except Exception:
            logger.exception("United check-in submission failed")
