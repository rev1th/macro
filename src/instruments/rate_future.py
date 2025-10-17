
from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm
import numpy as np

from common.models.future import Future
from common.date_helper import get_bdate_series
from common.chrono.tenor import Tenor
from common.chrono.daycount import DayCount
from instruments.rate_curve import RateCurve
from instruments.vol_curve import VolCurve
from lib.rate_helper import get_forecast_rate
from models.data_context import DataContext


@dataclass
class RateFuture(Future):
    _settle: dtm.date
    _rate_start_date: dtm.date
    _rate_end_date: dtm.date = None

    _convexity: float = field(init=False)
    
    @property
    def settle_date(self):
        return self._settle
    
    def get_settle_rate(self, date: dtm.date, curve: RateCurve) -> float:
        "Get settlement rate for RateFuture"
    
    def set_convexity(self, rate_vol_curve: VolCurve, daycount_type: DayCount = DayCount.ACT360) -> None:
        date = rate_vol_curve.date
        if self._rate_start_date <= date:
            self._convexity = 0
            return
        mean_reversion_rate = 0.03
        vol = rate_vol_curve.get_vol(self.settle_date)
        dcf_v_s = daycount_type.get_dcf(date, self.settle_date)
        dcf_rs_re = daycount_type.get_dcf(self._rate_start_date, self._rate_end_date)
        beta_rs_re = (1 - np.exp(-mean_reversion_rate * dcf_rs_re)) / mean_reversion_rate
        convex_unit = vol * vol / 2 * beta_rs_re * dcf_v_s * (dcf_v_s - dcf_rs_re)
        self._convexity = (100 - self.data[date] + 100 / dcf_rs_re) * (1 - np.exp(-convex_unit))

    def get_pv(self, curve: RateCurve) -> float:
        settle_rate = self.get_settle_rate(curve.date, curve)
        price = self.data[curve.date]
        return (1 - settle_rate - (price + self._convexity) / 100)

@dataclass
class RateFutureCompound(RateFuture):

    def __post_init__(self):
        self._rate_end_date = self.settle_date
    
    def get_settle_rate(self, _: dtm.date, curve: RateCurve) -> float:
        return get_forecast_rate(self._rate_start_date, self._rate_end_date, curve, self.underlying)

@dataclass
class RateFutureAverage(RateFuture):
    _rate_start_date: dtm.date = field(init=False)

    def __post_init__(self):
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
    
    def get_settle_rate(self, date: dtm.date, curve: RateCurve) -> float:
        settle_rate = 0
        bdates = self.fixing_dates
        context = DataContext()
        for di in range(0, len(bdates)-1):
            date_i = bdates[di]
            date_i_next = bdates[di+1]
            if date_i >= date:
                rate_fix = curve.get_forward_rate(date_i, date_i_next)
            else:
                rate_fix = context.get_fixing(self.underlying, date_i)
            settle_rate += rate_fix * (date_i_next - date_i).days
            date_i = date_i_next
        
        settle_rate /= (self._rate_end_date - self._rate_start_date).days
        return settle_rate
