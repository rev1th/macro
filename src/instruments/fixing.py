from pydantic.dataclasses import dataclass
from enum import StrEnum
import datetime as dtm

from common.models.base_instrument import BaseInstrument


class RateFixingType(StrEnum):
    RFR = 'RFR'
    IBOR = 'IBOR'

@dataclass
class RateFixing(BaseInstrument):
    _type: RateFixingType

    def get(self, date: dtm.date):
        try:
            return self.data[date]
        except KeyError:
            return self.data.get_latest_value(date)
    
    def get_last_value(self) -> float:
        return self.data.get_last_point()[1]


@dataclass
class InflationIndex(BaseInstrument):

    def get(self, date: dtm.date):
        next_id = self.data.bisect_right(date)
        # assert(next_id > 0, f"{date} is before the first available point {self.data.get_first_point()[0]}")
        last_date, last_value = self.data.peekitem(next_id-1)
        if last_date == date:
            return last_value
        try:
            next_date, next_value = self.data.peekitem(next_id)
        except IndexError:
            raise IndexError(f"{date} is after the last available point {self.data.get_last_point()[0]}")
        slope = (next_value - last_value) / (next_date - last_date).days
        return last_value + slope * (date - last_date).days

