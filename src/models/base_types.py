
from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm
from sortedcontainers import SortedDict


# frozen=True generates hash function and makes it immutable
@dataclass(frozen=True)
class DataPoint:
    date: dtm.date
    value: float = 0
    
    # @property
    # def date(self):
    #     return self._date
    
    # @property
    # def value(self):
    #     return self._value

    def __lt__(self, other):
        return self.date < other.date

    def __eq__(self, other):
        return (self.date == other.date) and (self.value == other.value)


# Mixin/Traits
@dataclass()
class NamedClass:
    name: str = field(kw_only=True, default=None)

    # @property
    # def name(self) -> str:
    #     return self._name

@dataclass()
class NamedDatedClass(NamedClass):
    date: dtm.date

    # @property
    # def date(self) -> dtm.date:
    #     return self._date


# No validators for non-default classes like SortedDict, pandas.DataFrame
# https://docs.pydantic.dev/latest/usage/model_config/#arbitrary-types-allowed
@dataclass(config=dict(arbitrary_types_allowed = True))
class FixingCurve(NamedClass):
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


FIXING_CURVE_MAP: dict[str, FixingCurve] = {}
def get_fixing(fixing_name, date: dtm.date) -> float:
    return FIXING_CURVE_MAP[fixing_name].get(date)
