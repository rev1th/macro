
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm

from instruments.swap_convention import SwapLegConvention, SwapFloatLegConvention
from instruments.rate_curve import RateCurve
from lib.rate_helper import get_forecast_rate

@dataclass
class SwapLeg:
    _convention: SwapLegConvention
    _start_date: dtm.date
    _end_date: dtm.date
    _notional: float

    coupon_dates: ClassVar[list[dtm.date]]
    coupon_pay_dates: ClassVar[list[dtm.date]]
    
    def __post_init__(self):
        self.coupon_dates = self._convention.coupon_frequency.generate_schedule(
            self._start_date, self._end_date, bd_adjust=self._convention.coupon_adjust())
        pay_delay = self._convention.coupon_pay_delay()
        self.coupon_pay_dates = [pay_delay.get_date(rd) for rd in self.coupon_dates]
    
    @property
    def notional_exchange(self):
        return self._convention.notional_exchange
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._convention.daycount_type.get_dcf(from_date, to_date)
    
    def get_pv(self) -> float:
        """Get PV for Swap Leg"""

    def get_annuity(self, discount_curve: RateCurve) -> float:
        annuity = 0
        accrual_start_date = self._start_date
        for cp_i in range(len(self.coupon_dates)):
            cp_d_i = self.coupon_dates[cp_i]
            cp_pd_i = self.coupon_pay_dates[cp_i]
            annuity += self._notional * self.get_dcf(accrual_start_date, cp_d_i) * discount_curve.get_df(cp_pd_i)
            accrual_start_date = cp_d_i
        return annuity

@dataclass
class SwapFixLeg(SwapLeg):
    _rate: float = field(init=False)

    def get_pv(self, discount_curve: RateCurve) -> float:
        pv = 0
        if self.notional_exchange.initial:
            pv += self._notional * discount_curve.get_df(self._start_date)
        pv += self.get_annuity(discount_curve=discount_curve) * self._rate
        if self.notional_exchange.final:
            pv += self._notional * discount_curve.get_df(self._end_date)
        return pv

@dataclass
class SwapFloatLeg(SwapLeg):
    _convention: SwapFloatLegConvention
    _spread: float = field(init=False, default=0)

    fixing_periods: ClassVar[list[list[tuple[dtm.date, dtm.date], tuple[dtm.date, dtm.date]]]]
    
    def __post_init__(self):
        super().__post_init__()
        accrual_dates = [self._start_date] + self.coupon_dates
        fixing_periods = [[] for _ in range(len(self.coupon_dates))]
        fixing_lag = self._convention.fixing_lag()
        if self._convention.is_interim_reset():
            reset_freq = self._convention.reset_frequency()
            for a_id in range(1, len(accrual_dates)):
                reset_dates = reset_freq.generate_schedule(
                    accrual_dates[a_id-1], accrual_dates[a_id],
                    step_backward=False, bd_adjust=self._convention.coupon_adjust())
                fixing_dates = [fixing_lag.get_date(rd) for rd in reset_dates]
                for f_id in range(1, len(fixing_dates)):
                    fixing_periods[a_id-1].append((
                        (fixing_dates[f_id-1], fixing_dates[f_id]),
                        (reset_dates[f_id-1], reset_dates[f_id])))
        else:
            fixing_dates = [fixing_lag.get_date(ad) for ad in accrual_dates]
            for f_id in range(1, len(fixing_dates)):
                fixing_periods[f_id-1].append((
                    (fixing_dates[f_id-1], fixing_dates[f_id]),
                    (accrual_dates[f_id-1], accrual_dates[f_id])))
        self.fixing_periods = fixing_periods

    @property
    def fixing(self):
        return self._convention.fixing
    
    def get_pv(self, discount_curve: RateCurve, forward_curve: RateCurve = None) -> float:
        if not forward_curve:
            forward_curve = discount_curve
        pv = 0
        if self.notional_exchange.initial:
            pv += self._notional * discount_curve.get_df(self._start_date)
        for cp_i in range(len(self.coupon_dates)):
            forecast_rate = 0
            for fix_i in self.fixing_periods[cp_i]:
                forecast_rate = (1 + forecast_rate) * \
                                (1 + get_forecast_rate(fix_i[0][0], fix_i[0][1], forward_curve, self.fixing) * \
                                    self.get_dcf(fix_i[1][0], fix_i[1][1])) - 1
            pv += self._notional * (forecast_rate + self._spread) * \
                    discount_curve.get_df(self.coupon_pay_dates[cp_i])
        if self.notional_exchange.final:
            pv += self._notional * discount_curve.get_df(self._end_date)
        return pv
