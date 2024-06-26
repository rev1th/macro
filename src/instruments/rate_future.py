
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm
import numpy as np

from common.models.future import Future
from instruments.rate_curve_instrument import CurveInstrument
from common.chrono import Tenor, DayCount, get_bdate_series
from instruments.fixing import Fixing, get_fixing
from instruments.rate_curve import RateCurve
from instruments.vol_curve import VolCurve


@dataclass
class RateFuture(Future):
    _rate_start_date: dtm.date
    _rate_end_date: dtm.date = None

    _convexity: ClassVar[float]
    
    @property
    def convexity(self) -> float:
        return self._convexity
    
    def underlying_rate(self, date: dtm.date) -> float:
        return get_fixing(self.underlying, date)
    
    def set_convexity(self, rate_vol_curve: VolCurve, daycount_type: DayCount = DayCount.ACT360) -> None:
        if self._rate_start_date <= self.value_date:
            self._convexity = 0
            return
        mean_reversion_rate = 0.03
        vol = rate_vol_curve.get_vol(self.settle_date)
        dcf_v_s = daycount_type.get_dcf(self.value_date, self.settle_date)
        dcf_rs_re = daycount_type.get_dcf(self._rate_start_date, self._rate_end_date)
        beta_rs_re = (1 - np.exp(-mean_reversion_rate * dcf_rs_re)) / mean_reversion_rate
        convex_unit = vol * vol / 2 * beta_rs_re * dcf_v_s * (dcf_v_s - dcf_rs_re)
        self._convexity = (100 - self.price + 100 / dcf_rs_re) * (1 - np.exp(-convex_unit))
    

@dataclass
class RateFutureC(RateFuture, CurveInstrument):
    _end: dtm.date = field(init=False)

    def __post_init__(self):
        self._end = self.expiry
    
    def get_pv(self, curve: RateCurve) -> float:
        return self.notional * (1 - self.get_settle_rate(curve) - (self.price + self.convexity) / 100)


@dataclass
class RateFutureIMM(RateFutureC):

    def __post_init__(self):
        super().__post_init__()
        self._rate_end_date = self.settle_date
    
    def get_settle_rate(self, curve: RateCurve) -> float:
        return curve.get_forecast_rate(self._rate_start_date, self.settle_date, self.underlying)


@dataclass
class RateFutureSerial(RateFutureC):
    _rate_start_date: dtm.date = field(init=False)

    def __post_init__(self):
        super().__post_init__()
        # first day of the expiry month
        self._rate_start_date = dtm.date(self.expiry.year, self.expiry.month, 1)
        # first day of next expiry month
        self._rate_end_date = Tenor('1BOM').get_date(self.expiry)

        bdates = get_bdate_series(self._rate_start_date, self._rate_end_date, self.calendar)
        if bdates[0] > self._rate_start_date:
            bdates.insert(0, self._rate_start_date)
        if bdates[-1] < self._rate_end_date:
            bdates.append(self._rate_end_date)
        self.fixing_dates = bdates
    
    def set_market(self, date: dtm.date, price: float) -> None:
        super().set_market(date, price)
    
    def get_settle_rate(self, curve: RateCurve) -> float:
        settle_rate = 0
        bdates = self.fixing_dates
        for di in range(0, len(bdates)-1):
            date_i = bdates[di]
            date_i_next = bdates[di+1]
            if date_i >= self.value_date:
                rate_fix = curve.get_forward_rate(date_i, date_i_next)
            else:
                rate_fix = self.underlying_rate(date_i)
            
            settle_rate += rate_fix * (date_i_next - date_i).days
            date_i = date_i_next
        
        settle_rate /= (self._rate_end_date - self._rate_start_date).days
        return settle_rate
