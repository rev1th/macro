import datetime as dtm
import common.chrono as date_lib

CALENDAR = date_lib.Calendar.USEX
TIMEZONE = 'America/New_York'

def get_valuation_dates(from_date: dtm.date, to_date: dtm.date = None):
    if not from_date:
        if not to_date:
            return [None]
        else:
            return date_lib.get_bdate_series(to_date, to_date, CALENDAR)
    if not to_date:
        to_date = date_lib.get_last_valuation_date(timezone=TIMEZONE, calendar=CALENDAR.value)
    return date_lib.get_bdate_series(from_date, to_date, CALENDAR)

def get_last_valuation_date():
    return date_lib.get_last_valuation_date(timezone=TIMEZONE, calendar=CALENDAR.value)
