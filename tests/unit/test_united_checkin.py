from pytest_mock import MockerFixture

from lib.united_checkin import UnitedCheckInScheduler


class TestUnitedCheckInScheduler:
    def test_schedule_handles_bogus_trip_without_crashing(
        self, mocker: MockerFixture
    ) -> None:
        scheduler = UnitedCheckInScheduler(headed=False)
        mocker.patch.object(scheduler.scraper, "fetch_segments", return_value=[])
        submit_mock = mocker.patch.object(
            scheduler.checkin, "submit", side_effect=RuntimeError("submission failed")
        )

        scheduler.schedule_checkins("ABC123", "LASTNAME")

        submit_mock.assert_called_once_with("ABC123", "LASTNAME")

    def test_schedule_handles_trip_lookup_failure(
        self, mocker: MockerFixture
    ) -> None:
        scheduler = UnitedCheckInScheduler(headed=False)
        mocker.patch.object(
            scheduler.scraper, "fetch_segments", side_effect=RuntimeError("lookup error")
        )
        attempt_mock = mocker.patch.object(scheduler, "_attempt_submit")

        scheduler.schedule_checkins("ABC123", "LASTNAME")

        attempt_mock.assert_called_once_with("ABC123", "LASTNAME")
