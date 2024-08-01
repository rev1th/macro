
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
from abc import abstractmethod
import datetime as dtm
import numpy as np

from common.models.base_instrument import BaseInstrument
from common.chrono.tenor import Tenor
from instruments.rate_curve import RateCurve


# BaseModel doesn't initialize private attributes
# https://docs.pydantic.dev/latest/usage/models/#private-model-attributes
@dataclass
class CurveInstrument(BaseInstrument):
    _end: Tenor | dtm.date
    _: KW_ONLY
    _notional: float = 1000000
    
    _knot: dtm.date = None
    exclude_knot: bool = False

    @property
    def end(self):
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
            return self._end
    
    @knot.setter
    def knot(self, value: dtm.date):
        self._knot = value
    
    @abstractmethod
    def get_pv(self) -> float:
        """Get PV of rate curve instrument."""
    
    def __lt__(self, other) -> bool:
        return self._end < other._end


@dataclass
class Deposit(CurveInstrument):
    _start: Tenor | dtm.date | None = None
    _rate: float = field(init=False)

    def start_date(self, date: dtm.date) -> dtm.date:
        if not self._start:
            return date
        elif isinstance(self._start, Tenor):
            return self._start.get_date(date)
        return self._start
    
    def get_pv(self, curve: RateCurve) -> float:
        start_date = self.start_date(curve.date)
        fcast_rate = curve.get_forward_rate(start_date, self.end)
        period_dcf = curve.get_dcf(start_date, self.end)
        fcast_rate *= period_dcf
        fixed_rate = np.exp(self.data[curve.date] * period_dcf) - 1
        return self.notional * (fcast_rate - fixed_rate)

