
from pydantic.dataclasses import dataclass
from enum import StrEnum
from sortedcontainers import SortedDict
import datetime as dtm

from common.model import NameClass


@dataclass(frozen=True)
class Fixing:
    name: str


class RateFixingType(StrEnum):

    RFR = 'RFR'
    IBOR = 'IBOR'


# No validators for non-default classes like SortedDict, pandas.DataFrame
# https://docs.pydantic.dev/latest/usage/model_config/#arbitrary-types-allowed
@dataclass(config=dict(arbitrary_types_allowed = True))
class FixingCurve(NameClass):
    _datevalue: SortedDict[dtm.date, float]

    def get(self, date: dtm.date):
        if date in self._datevalue:
            return self._datevalue[date]
        elif date < self._datevalue.peekitem(0)[0]:
            raise Exception(f"{date} is before the first available point {self._datevalue.peekitem(0)[0]}")
        elif date > self._datevalue.peekitem(-1)[0]:
            raise Exception(f"{date} is after the last available point {self._datevalue.peekitem(-1)[0]}")
        else:
            return self._datevalue.peekitem(self._datevalue.bisect_left(date)-1)[1]
        
    def get_last_date(self) -> dtm.date:
        return self._datevalue.peekitem(-1)[0]

    def get_last_value(self) -> float:
        return self._datevalue[self.get_last_date()]


FIXING_CURVE_MAP: dict[Fixing, FixingCurve] = {}

def get_fixing(fixing: Fixing, date: dtm.date) -> float:
    return FIXING_CURVE_MAP[fixing].get(date)

def add_fixing_curve(fixing_curve: FixingCurve) -> None:
    FIXING_CURVE_MAP[Fixing(fixing_curve.name)] = fixing_curve
