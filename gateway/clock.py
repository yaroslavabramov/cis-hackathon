import os
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime

START = os.getenv("DEMO_START", "01:59:20")
_anchor = time.time()


def reset():
    global _anchor
    _anchor = time.time()


def now() -> datetime:
    return datetime.combine(date.today(), dtime.fromisoformat(START)) + timedelta(seconds=time.time() - _anchor)


def label(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%H:%M:%S")
