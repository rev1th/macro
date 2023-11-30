
from typing import Union
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
import datetime as dtm

from model.abstract_instrument import BaseInstrument
from lib.date_utils import Tenor
from rate_curve import YieldCurve


# BaseModel doesn't initialize private attributes
# https://docs.pydantic.dev/latest/usage/models/#private-model-attributes
@dataclass
class CurveInstrument(BaseInstrument):
    _end: Union[Tenor, dtm.date]
    _: KW_ONLY
    _notional: float = 1000000
    
    _knot: dtm.date = None
    exclude_knot: bool = False

    @property
    def end(self):
        return self._end
    
    @property
    def end_date(self) -> dtm.date:
        if isinstance(self._end, Tenor):
            return self._end.get_date(self.value_date)
        return self._end
    
    @property
    def notional(self) -> float:
        return self._notional
    
    @property
    def knot(self):
        if self.exclude_knot:
            return None
        elif self._knot:
            return self._knot
        else:
            return self.end_date
    
    @knot.setter
    def knot(self, value: dtm.date):
        self._knot = value
    
    def get_pv(self) -> float:
        raise NotImplementedError("Abstract function: get_pv")
    
    @property
    def price(self) -> float:
        raise NotImplementedError("Property not defined: price")
    
    def __lt__(self, other) -> bool:
        return self.end < other.end


@dataclass
class Deposit(CurveInstrument):
    _start: Union[Tenor, dtm.date] = None
    _rate: float = field(init=False)

    @property
    def start_date(self) -> dtm.date:
        if not self._start:
            return self.value_date
        elif isinstance(self._start, Tenor):
            return self._start.get_date(self.value_date, 'F')
        return self._start
    
    @property
    def price(self) -> float:
        return self._rate

    def set_market(self, date: dtm.date, fixing: float) -> None:
        super().set_market(date)
        self._rate = fixing

    def get_pv(self, curve: YieldCurve) -> float:
        fcast_rate = curve.get_forward_rate(self.start_date, self.end_date)
        fcast_rate *= curve.get_dcf(self.start_date, self.end_date)
        fixed_rate = 1 / curve.get_step_df(self._rate, self.start_date, self.end_date) - 1
        return self.notional * (fcast_rate - fixed_rate)

