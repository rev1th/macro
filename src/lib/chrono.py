
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import Union, Iterable
import datetime as dtm
import calendar as cal_lib
import holidays
from zoneinfo import ZoneInfo
import numpy as np
from pandas.tseries.offsets import DateOffset, MonthEnd, QuarterEnd, YearEnd, MonthBegin, CustomBusinessDay as CBDay
from enum import StrEnum

FIRSTDATE = dtm.date(1900, 1, 1)
_CACHED_BDC: dict[str, np.busdaycalendar] = {}
_YEARS = range(2022, 2026)


def get_bdc(calendar: str):
    if calendar not in _CACHED_BDC:
        subcals = calendar.split('-')
        if len(subcals) > 1:
            hols = list(holidays.country_holidays(subcals[0], subdiv=subcals[1], years = _YEARS).keys())
        else:
            hols = list(holidays.country_holidays(subcals[0][:2], years = _YEARS).keys())
        _CACHED_BDC[calendar] = np.busdaycalendar(holidays=hols)
    return _CACHED_BDC[calendar]

def date_to_int(dt: dtm.date) -> int:
    return (dt-FIRSTDATE).days

def str_to_int(str_int: str) -> int:
    if str_int.isdigit() or (str_int[0] == '-' and str_int[1:].isdigit()):
        return int(str_int)
    return None

def get_adjusted_date(adjust_type: str, date: dtm.date, calendar: str = None) -> dtm.date:
    match adjust_type:
        case 'F':
            return (date + CBDay(0, calendar=get_bdc(calendar))).date()
        case 'P':
            bdc = get_bdc(calendar)
            return (date + CBDay(1, calendar=bdc) + CBDay(-1, calendar=bdc)).date()
        case 'MF':
            date_f = get_adjusted_date('F', date, calendar)
            # if EOM then preceding else following
            if date_f.year > date.year or (date_f.year == date.year and date_f.month > date.month):
                return get_adjusted_date('P', date, calendar)
            return date_f
        case _:
            return date

class BDayAdjustType(StrEnum):

    NoAdjust = ''
    Following = 'F'
    Previous = 'P'
    ModifiedFollowing = 'MF'

    def get_date(self, date: dtm.date) -> dtm.date:
        return get_adjusted_date(self.value, date)

@dataclass()
class BDayAdjust():
    _adjust_type: str
    _calendar: str

    def get_date(self, date: dtm.date) -> dtm.date:
        return get_adjusted_date(self._adjust_type, date, self._calendar)

def parseTenor(offsets: Union[str, tuple[str, str]]):
    if isinstance(offsets, str):
        offset, bdc = offsets, None
    else:
        offset = offsets[0]
        bdc = get_bdc(offsets[1]) if offsets[1] else None
    if len(offset) < 2:
        raise Exception(f'Invalid input {offset}')
    if len(offset) > 3:
        offset_int = str_to_int(offset[:-3])
        match offset[-3:].upper():
            case 'BOM'|'SOM':
                return MonthBegin(n=offset_int)
            case 'EOM':
                return MonthEnd(n=offset_int)
            case 'EOQ':
                return QuarterEnd(n=offset_int)
            case 'EOY':
                return YearEnd(n=offset_int)
    offset_int = str_to_int(offset[:-1])
    match offset[-1]:
        case 'B' | 'b':
            return CBDay(n=offset_int, calendar=bdc)
        case 'Y' | 'y':
            return DateOffset(years=offset_int)
        case 'M' | 'm':
            return DateOffset(months=offset_int)
        case 'W' | 'w':
            return DateOffset(weeks=offset_int)
        case 'D' | 'd':
            return DateOffset(days=offset_int)
        case _:
            raise RuntimeError(f'Cannot parse tenor {offset}')


@dataclass(config=dict(arbitrary_types_allowed = True))
class Tenor():
    offset_init: InitVar[Union[str, tuple[str, str], DateOffset, Iterable[DateOffset], dtm.date]]
    
    def __post_init__(self, offset_init):
        if isinstance(offset_init, str) or isinstance(offset_init, tuple):
            self._offset = parseTenor(offset_init)
        else:
            self._offset = offset_init
    
    def __add__(self, new):
        offsets = self._offset if isinstance(self._offset, Iterable) else [self._offset]
        if isinstance(new._offset, Iterable):
            offsets.extend(new._offset)
        else:
            offsets.append(new._offset)
        return Tenor(offsets)
    
    @classmethod
    def bday(cls, n: int = 0, calendar: str = None):
        return cls(CBDay(n=n, calendar=(get_bdc(calendar) if calendar else None)))
    
    @property
    def isbackward(self) -> dtm.date:
        offset = self._offset
        if isinstance(offset, DateOffset):
            return offset.n < 0
        elif isinstance(offset, Iterable):
            return offset[0].n < 0
        return False
    
    def _get_date(self, date: dtm.date = None) -> dtm.date:
        offset = self._offset
        if isinstance(offset, dtm.date):
            return offset
        elif isinstance(offset, DateOffset):
            return (date + offset).date()
        elif isinstance(offset, Iterable):
            res = date
            for off_i in offset:
                res = res + off_i
            return res.date()
        return date + offset
    
    def get_date(self, date: dtm.date = None, adjust_type: BDayAdjustType = BDayAdjustType.NoAdjust) -> dtm.date:
        return adjust_type.get_date(self._get_date(date))
    
    # Generates schedule with Tenor for [from_date, to_date]
    def generate_series(self, from_date: dtm.date, to_date: dtm.date,
                          isbackward: bool = False,
                          adjust_type: BDayAdjustType = BDayAdjustType.NoAdjust) -> list[dtm.date]:
        schedule = []
        if isbackward:
            date_i = to_date
            while date_i >= from_date:
                date_i_adj = adjust_type.get_date(date_i)
                schedule.insert(0, date_i_adj)
                date_i = self.get_date(date_i)
        else:
            date_i = from_date
            while date_i <= to_date:
                date_i_adj = adjust_type.get_date(date_i)
                schedule.append(date_i_adj)
                date_i = self.get_date(date_i)
        return schedule


class Frequency(StrEnum):

    Annual = 'A'
    SemiAnnual = 'S'
    Quarterly = 'Q'
    Monthly = 'M'
    Weekly = 'W'

    def to_tenor(self, backward: bool = True) -> Tenor:
        match self.value.upper():
            case 'A':
                return Tenor('-1y' if backward else '1y')
            case 'S':
                return Tenor('-6m' if backward else '6m')
            case 'Q':
                return Tenor('-3m' if backward else '3m')
            case 'M':
                return Tenor('-1m' if backward else '1m')
            case 'W' | '7D':
                return Tenor('-1w' if backward else '1w')
            case '4W' | '28D':
                return Tenor('-4w' if backward else '4w')
            case 'D' | 'B':
                return Tenor('-1b' if backward else '1b')
            case _:
                raise RuntimeError(f'Cannot parse frequency {self.value}')
    
    def generate_schedule(self, start: Union[dtm.date, Tenor], end: Union[dtm.date, Tenor],
                          ref_date: dtm.date = None,
                          adjust_type: BDayAdjustType = BDayAdjustType.NoAdjust) -> list[dtm.date]:
        start_date = start if isinstance(start, dtm.date) else start.get_date(ref_date)
        end_date = end if isinstance(end, dtm.date) else end.get_date(start_date)

        freq_tenor = self.to_tenor(backward=True)
        schedule = []
        date_i = end_date
        while date_i > start_date:
            date_i_adj = adjust_type.get_date(date_i)
            schedule.insert(0, date_i_adj)
            date_i = freq_tenor.get_date(date_i)
        return schedule


class DayCount(StrEnum):
    
    ACT360 = 'ACT360'
    ACT365 = 'ACT365'
    ACTACT = 'ACTACT'
    ACTACTISDA = 'ACTACTISDA'
    _30360 = '30360'
    _30E360 = '30E360'
    # ACTACTISMA = 'ACTACTISMA'

    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        match self.value:
            case 'ACT360':
                return (to_date-from_date).days/360.0
            case 'ACT365':
                return (to_date-from_date).days/365.0
            case 'ACTACT':
                if (from_date.month > to_date.month) or (from_date.month == to_date.month and from_date.day > to_date.day):
                    from_date_to = dtm.date(from_date.year+1, to_date.month, to_date.day)
                    dcf = to_date.year-from_date.year-1
                else:
                    from_date_to = dtm.date(from_date.year, to_date.month, to_date.day)
                    dcf = to_date.year-from_date.year
                days_in_year = 365
                if cal_lib.isleap(from_date.year):
                    if from_date < dtm.date(from_date.year, 2, 29) <= from_date_to:
                        days_in_year += 1
                dcf += (from_date_to-from_date).days / days_in_year
                return dcf
            case 'ACTACTISDA':
                if to_date.year > from_date.year:
                    from_date_to = dtm.date(from_date.year+1, 1, 1)
                    dcf = (from_date_to-from_date).days / (365+cal_lib.isleap(from_date.year))
                    dcf += to_date.year-from_date.year-1
                    to_date_from = dtm.date(to_date.year, 1, 1)
                    dcf += (to_date-to_date_from).days / (365+cal_lib.isleap(to_date.year))
                    return dcf
                else:
                    return (to_date-from_date).days / (365+cal_lib.isleap(to_date.year))
            case '30360':
                from_day = 30 if from_date.day == 31 else from_date.day
                to_day = 30 if to_date.day == 31 and from_date.day in (30, 31) else to_date.day
                return (to_date.year-from_date.year) + (to_date.month-from_date.month)/12 + (to_day-from_day)/360
            case '30E360':
                from_day = 30 if from_date.day == 31 else from_date.day
                to_day = 30 if to_date.day == 31 else to_date.day
                return (to_date.year-from_date.year) + (to_date.month-from_date.month)/12 + (to_day-from_day)/360
            case _:
                raise Exception(f'{self.value} not recognized for day count fraction')

# Return all business dates over a period
def get_bdate_series(from_date: dtm.date, to_date: dtm.date, calendar: str = None) -> list[dtm.date]:
    return Tenor.bday(1, calendar=calendar).generate_series(from_date, to_date)

# Returns last valuation date
def get_last_valuation_date(timezone: str = None, calendar: str = None,
                            roll_hour: int = 18, roll_minute: int = 0) -> dtm.date:
    sys_dtm = dtm.datetime.now()
    val_dtm = sys_dtm.astimezone(ZoneInfo(timezone) if timezone else None)
    val_dt = get_adjusted_date('P', date=val_dtm.date(), calendar=calendar)
    if val_dt < val_dtm.date():
        return val_dt
    if val_dtm.hour < roll_hour or (val_dtm.hour == roll_hour and val_dtm.minute < roll_minute):
        return Tenor(('-1B', calendar)).get_date(val_dt)
    return val_dtm.date()

# Returns current valuation date, roll forward on holiday
def get_current_valuation_date(timezone: str = None, calendar: str = None,
                               roll_hour: int = 18, roll_minute: int = 0) -> dtm.date:
    sys_dtm = dtm.datetime.now()
    val_dtm = sys_dtm.astimezone(ZoneInfo(timezone) if timezone else None)
    val_dt = get_adjusted_date('F', date=val_dtm.date(), calendar=calendar)
    if val_dt > val_dtm.date():
        return val_dt
    if val_dtm.hour > roll_hour or (val_dtm.hour == roll_hour and val_dtm.minute >= roll_minute):
        return Tenor(('1B', calendar)).get_date(val_dt)
    return val_dtm.date()

