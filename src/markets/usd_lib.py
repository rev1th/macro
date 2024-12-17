import datetime as dtm
from zoneinfo import ZoneInfo
import common.chrono as date_lib

CALENDAR = date_lib.CalendarID.USEX
TIMEZONE = ZoneInfo('America/New_York')
CLOSE_TIME = dtm.time(17, 0, tzinfo=TIMEZONE)

def get_trade_dates(from_date: dtm.date, to_date: dtm.date = None):
    if not to_date:
        to_date = date_lib.get_last_business_date(calendar=CALENDAR, roll_time=CLOSE_TIME)
    if not from_date:
        return date_lib.get_bdate_series(to_date, to_date, CALENDAR)
    return date_lib.get_bdate_series(from_date, to_date, CALENDAR)

def get_last_trade_date():
    return date_lib.get_last_business_date(calendar=CALENDAR, roll_time=CLOSE_TIME)
