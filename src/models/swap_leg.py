
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
from abc import abstractmethod
import datetime as dtm

from common.chrono import Tenor
from models.swap_convention import SwapLegConvention
from models.rate_curve import YieldCurve


@dataclass
class SwapLeg:
    _convention: SwapLegConvention
    _start: Tenor
    _end: Tenor
    _notional: float
    _units: float = 1
    
    _value_date: dtm.date = field(init=False, default=None)

    _start_date: ClassVar[dtm.date]
    _end_date: ClassVar[dtm.date]
    coupon_dates: ClassVar[list[dtm.date]]
    coupon_pay_dates: ClassVar[list[dtm.date]]
    
    @property
    def start_date(self) -> dtm.date:
        return self._start_date
    
    @property
    def end_date(self) -> dtm.date:
        return self._end_date
    
    @property
    def notional(self) -> float:
        return self._notional
    
    @property
    def notional_exchange(self):
        return self._convention.notional_exchange
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._convention.daycount_type.get_dcf(from_date, to_date)
    
    def set_market(self, date: dtm.date) -> None:
        self._value_date = date
        self._start_date = self._start.get_date(self._convention.spot_delay.get_date(self._value_date))
        self._end_date = self._end.get_date(self._start_date, bd_adjust=self._convention.coupon_adjust)
        self.coupon_dates = self._convention.coupon_frequency.generate_schedule(
            self.start_date, self.end_date,
            bd_adjust=self._convention.coupon_adjust)
        self.coupon_pay_dates = [self._convention.coupon_pay_delay.get_date(rd) for rd in self.coupon_dates]
    
    @abstractmethod
    def get_pv(self) -> float:
        """Get PV for Swap Leg"""

    def get_annuity(self, discount_curve: YieldCurve) -> float:
        annuity = 0
        accrual_start_date = self.start_date
        for cp_i in range(0, len(self.coupon_dates)):
            cp_d_i = self.coupon_dates[cp_i]
            cp_pd_i = self.coupon_pay_dates[cp_i]
            annuity += self.notional * self.get_dcf(accrual_start_date, cp_d_i) * discount_curve.get_df(cp_pd_i)
            accrual_start_date = cp_d_i
        return annuity

@dataclass
class SwapFixLeg(SwapLeg):
    _rate: float = field(init=False)
    
    def set_market(self, date: dtm.date, rate: float = 0) -> None:
        super().set_market(date)
        self._rate = rate

    def get_pv(self, discount_curve: YieldCurve) -> float:
        pv = 0
        if self.notional_exchange.initial:
            pv += self.notional * discount_curve.get_df(self.start_date)
        pv += self.get_annuity(discount_curve=discount_curve) * self._rate * self._units
        if self.notional_exchange.final:
            pv += self.notional * discount_curve.get_df(self.end_date)
        return pv

@dataclass
class SwapFloatLeg(SwapLeg):
    _spread: float = field(init=False)

    @property
    def fixing(self):
        return self._convention.fixing

    def set_market(self, date: dtm.date, spread: float = 0) -> None:
        super().set_market(date)
        self._spread = spread
        self.coupon_fix_dates = [self._convention.fixing_lag.get_date(rd) for rd in [self.start_date] + self.coupon_dates]

    def get_pv(self, discount_curve: YieldCurve, forward_curve: YieldCurve = None) -> float:
        if not forward_curve:
            forward_curve = discount_curve
        pv = 0
        if self.notional_exchange.initial:
            pv += self.notional * discount_curve.get_df(self.start_date)
        forward_start_date = self.start_date
        fixing_start_date = self.coupon_fix_dates[0]
        for cp_i in range(0, len(self.coupon_dates)):
            forward_end_date = self.coupon_dates[cp_i]
            fixing_end_date = self.coupon_fix_dates[cp_i+1]
            pv += self.notional * (forward_curve.get_forecast_rate(fixing_start_date, fixing_end_date, self.fixing) + \
                                   self._spread * self._units) * \
                    self.get_dcf(forward_start_date, forward_end_date) * \
                    discount_curve.get_df(self.coupon_pay_dates[cp_i])
            forward_start_date = forward_end_date
            fixing_start_date = fixing_end_date
        if self.notional_exchange.final:
            pv += self.notional * discount_curve.get_df(self.end_date)
        return pv
