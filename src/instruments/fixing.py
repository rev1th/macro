
import logging
from pydantic.dataclasses import dataclass
from enum import StrEnum
from sortedcontainers import SortedDict
import datetime as dtm

from common.base_class import NameClass
from common.models.base_instrument import BaseInstrument

logger = logging.Logger(__name__)


@dataclass
class Fixing(BaseInstrument):
    pass


class RateFixingType(StrEnum):

    RFR = 'RFR'
    IBOR = 'IBOR'


# No validators for non-default classes like SortedDict, pandas.DataFrame
# https://docs.pydantic.dev/latest/usage/model_config/#arbitrary-types-allowed
@dataclass(config=dict(arbitrary_types_allowed = True))
class FixingCurve(NameClass):
    _datevalue: SortedDict[dtm.date, float]

    def get(self, date: dtm.date):
        try:
            return self._datevalue[date]
        except KeyError:
            if date > self._datevalue.peekitem(-1)[0]:
                logger.error(f"{date} is after the last available point {self._datevalue.peekitem(-1)[0]}")
                return self._datevalue.peekitem(-1)[1]
            elif date < self._datevalue.peekitem(0)[0]:
                raise Exception(f"{date} is before the first available point {self._datevalue.peekitem(0)[0]}")
            else:
                return self._datevalue.peekitem(self._datevalue.bisect_left(date)-1)[1]
        
    def get_last_date(self) -> dtm.date:
        return self._datevalue.peekitem(-1)[0]

    def get_last_value(self) -> float:
        return self._datevalue[self.get_last_date()]

