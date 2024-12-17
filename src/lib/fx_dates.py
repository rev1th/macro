import datetime as dtm

from common.chrono.badjust import BDayAdjust, BDayAdjustType
from common.chrono.calendar import CalendarID
from common.chrono.roll import RollConvention, RollConventionType
from common.chrono.tenor import Tenor
from common.currency import Currency

CALENDAR_MAP = dict(
    CNY=CalendarID.CNY,
)
TOM_SPOT_LIST = ('CAD', 'TRY', 'PHP', 'RUB')
ROLL_DEFAULT = RollConvention(RollConventionType.EndOfMonth)

def get_settle_calendar(ccy_cal: str):
    return f'{ccy_cal}+{CalendarID.USD.value}'

def get_spot_date(ccy: Currency, date: dtm.date):
    ccy_cal = CALENDAR_MAP[ccy].value
    ccy_usd_cal = get_settle_calendar(ccy_cal)
    if ccy in TOM_SPOT_LIST:
        return Tenor.bday(1, ccy_usd_cal).get_date(date)
    ccy_bd = Tenor.bday(2, ccy_cal).get_date(date)
    return BDayAdjust(BDayAdjustType.Following, ccy_usd_cal).get_date(ccy_bd)

def get_delivery_date(ccy: Currency, tenor: Tenor, spot_date: dtm.date):
    ccy_usd_cal = get_settle_calendar(CALENDAR_MAP[ccy].value)
    return tenor.get_rolled_date(spot_date, ROLL_DEFAULT, BDayAdjust(BDayAdjustType.ModifiedFollowing, ccy_usd_cal))

def get_forward_dates(ccy: Currency, tenor: Tenor, spot_date: dtm.date):
    delivery_date = get_delivery_date(ccy, tenor, spot_date)
    ccy_cal = CALENDAR_MAP[ccy].value
    if ccy in TOM_SPOT_LIST:
        expiry_date = Tenor.bday(-1, ccy_cal).get_date(delivery_date)
    else:
        expiry_date = Tenor.bday(-2, ccy_cal).get_date(delivery_date)
    return expiry_date, delivery_date
