from cloud import CloudService
from models import BinReading


def test_cloud_saves_and_alerts_above_80_percent() -> None:
    saved = []
    service = CloudService(saved.append)

    alert = service.process(
        BinReading("bin-1", 81, "2026-01-01T00:00:00+00:00")
    )

    assert saved == [BinReading("bin-1", 81, "2026-01-01T00:00:00+00:00")]
    assert alert == "Pickup alert: bin-1 is 81% full"


def test_cloud_does_not_alert_at_80_percent() -> None:
    assert (
        CloudService(lambda _: None).process(BinReading("bin-1", 80, "now"))
        is None
    )
