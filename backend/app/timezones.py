"""Application timezones loaded from the backend's pinned IANA data."""

from importlib.resources import files
from zoneinfo import ZoneInfo


def _bundled_zoneinfo(key: str) -> ZoneInfo:
    resource = files("tzdata.zoneinfo").joinpath(*key.split("/"))
    with resource.open("rb") as zone_file:
        return ZoneInfo.from_file(zone_file, key=key)


APPLICATION_TIMEZONE = _bundled_zoneinfo("America/Vancouver")
