
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
from typing import ClassVar
from abc import abstractmethod
import datetime as dtm

from common.chrono import Tenor
from models.abstract_instrument import BaseInstrument
from models.swap_convention import SwapConvention, SwapLegConvention
from models.rate_curve_instrument import CurveInstrument
from models.rate_curve import YieldCurve


@dataclass
class SwapLeg():
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
    def fixing(self) -> str:
        return self._convention.fixing

    def set_market(self, date: dtm.date, spread: float = 0) -> None:
        super().set_market(date)
        self._spread = spread
        self.coupon_fix_dates = [self._convention.fixing_lag.get_date(rd) for rd in [self.start_date] + self.coupon_dates]

    def get_pv(self, discount_curve: YieldCurve, forecast_curve: YieldCurve = None) -> float:
        if not forecast_curve:
            forecast_curve = discount_curve
        pv = 0
        if self.notional_exchange.initial:
            pv += self.notional * discount_curve.get_df(self.start_date)
        forecast_start_date = self.start_date
        fixing_start_date = self.coupon_fix_dates[0]
        for cp_i in range(0, len(self.coupon_dates)):
            forecast_end_date = self.coupon_dates[cp_i]
            fixing_end_date = self.coupon_fix_dates[cp_i+1]
            pv += self.notional * (forecast_curve.get_forecast_rate(fixing_start_date, fixing_end_date, self.fixing) + \
                                   self._spread * self._units) * \
                    self.get_dcf(forecast_start_date, forecast_end_date) * \
                    discount_curve.get_df(self.coupon_pay_dates[cp_i])
            forecast_start_date = forecast_end_date
            fixing_start_date = fixing_end_date
        if self.notional_exchange.final:
            pv += self.notional * discount_curve.get_df(self.end_date)
        return pv


@dataclass
class SwapCommon(BaseInstrument):
    _convention_name: str
    _end: Tenor
    _: KW_ONLY
    _notional: float = 1000000
    _units: float = 1
    # mutable defaults not allowed
    # https://docs.python.org/3/library/dataclasses.html#default-factory-functions
    _start: Tenor = field(default_factory=Tenor.bday)

    _convention: ClassVar[SwapConvention]
    _leg1: ClassVar[SwapLeg] = None
    _leg2: ClassVar[SwapLeg] = None
    
    def __post_init__(self):
        if not self.name:
            self.name = f'{self._convention_name}_{self._end}'
        self._convention = SwapConvention(self._convention_name)
    
    @property
    def convention_name(self) -> str:
        return self._convention_name

    @property
    def end(self):
        return self._end
    
    @property
    def end_date(self) -> dtm.date:
        return self._leg1.end_date

    @property
    def start(self):
        return self._start
    
    @property
    def start_date(self) -> dtm.date:
        return self._leg1.start_date

    @property
    def notional(self) -> float:
        return self._notional
    
    @property
    def convention(self):
        return self._convention
    
    def set_market(self, date: dtm.date, rate1: float = 0, rate2: float = 0) -> None:
        super().set_market(date)
        self._leg1.set_market(date, rate1)
        self._leg2.set_market(date, rate2)
        self._knot = self.end_date
        assert date <= self.knot, "Valuation date cannot be after expiry"
    
    @abstractmethod
    def get_par(self, _: YieldCurve) -> float:
        """Get Par rate for Swap"""

    @abstractmethod
    def get_pv01(self, _: YieldCurve) -> float:
        """Get PV01 for Swap"""

@dataclass
class SwapCommonC(SwapCommon, CurveInstrument):
    pass

# Single currency Fix vs Float
@dataclass
class DomesticSwap(SwapCommonC):
    _fix_leg_id: int = 1
    _units: float = 1/100  # standard in %
    _rate: float = field(init=False)

    _fix_leg: ClassVar[SwapFixLeg]
    _float_leg: ClassVar[SwapFloatLeg]
    
    def __post_init__(self):
        super().__post_init__()
        assert self._fix_leg_id in (1, 2), f"Invalid fix leg specified {self._fix_leg_id}"
        self._fix_leg = SwapFixLeg(self.convention.leg1, self._start, self._end, self.notional, _units=self._units)
        self._float_leg = SwapFloatLeg(self.convention.leg2, self._start, self._end, -self.notional)
        if self._fix_leg_id == 1:
            self._leg1, self._leg2 = self._fix_leg, self._float_leg
        else:
            self._leg1, self._leg2 = self._float_leg, self._fix_leg
    
    @property
    def price(self) -> float:
        return self._rate
    
    @property
    def fix_rate(self) -> float:
        return self._rate * self._units
    
    def set_market(self, date: dtm.date, rate: float) -> None:
        super().set_market(date, rate1=rate)
        self._rate = rate
    
    def get_pv(self, forecast_curve: YieldCurve, discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = forecast_curve
        float_pv = self._float_leg.get_pv(forecast_curve=forecast_curve, discount_curve=discount_curve)
        return self._fix_leg.get_pv(discount_curve) + float_pv
    
    def get_par(self, forecast_curve: YieldCurve, discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = forecast_curve
        pv = self.get_pv(forecast_curve=forecast_curve, discount_curve=discount_curve)
        return self._rate * self._units - pv / self._fix_leg.get_annuity(discount_curve)

    def get_pv01(self, discount_curve: YieldCurve) -> float:
        return self._fix_leg.get_annuity(discount_curve) / 10000


# Single currency Float vs Float
@dataclass
class BasisSwap(SwapCommonC):
    _spread_leg_id: int = 2
    _units: float = 1/10000  # standard in bps
    _spread: float = field(init=False)

    _spread_leg: ClassVar[SwapFloatLeg]

    def __post_init__(self):
        super().__post_init__()
        assert self._spread_leg_id in (1, 2), f"Invalid spread leg specified {self._spread_leg_id}"
        self._leg1 = SwapFloatLeg(self.convention.leg1, self._start, self._end, self.notional, _units=self._units)
        self._leg2 = SwapFloatLeg(self.convention.leg2, self._start, self._end, -self.notional, _units=self._units)
        if self._spread_leg_id == 1:
            self._spread_leg = self._leg1
        else:
            self._spread_leg = self._leg2
    
    def set_market(self, date: dtm.date, points: float) -> None:
        if self._spread_leg_id == 1:
            super().set_market(date, rate1=points)
        else:
            super().set_market(date, rate2=points)
        self._spread = points
    
    @property
    def price(self) -> float:
        return self._spread
    
    @property
    def spread_leg(self) -> SwapFloatLeg:
        return self._spread_leg
    
    @property
    def spread(self) -> float:
        return self._spread * self._units
    
    def get_pv(self,
               leg1_forecast_curve: YieldCurve, leg2_forecast_curve: YieldCurve,
               discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forecast_curve
        leg1_pv = self._leg1.get_pv(forecast_curve=leg1_forecast_curve, discount_curve=discount_curve)
        leg2_pv = self._leg2.get_pv(forecast_curve=leg2_forecast_curve, discount_curve=discount_curve)
        return leg1_pv + leg2_pv

    def get_par(self,
                leg1_forecast_curve: YieldCurve, leg2_forecast_curve: YieldCurve,
                discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forecast_curve
        pv = self.get_pv(
            leg1_forecast_curve=leg1_forecast_curve,
            leg2_forecast_curve=leg2_forecast_curve,
            discount_curve=discount_curve)
        return self._spread * self._units - pv / self.spread_leg.get_annuity(discount_curve)

    def get_pv01(self, discount_curve: YieldCurve) -> float:
        return self.spread_leg.get_annuity(discount_curve) / 10000


# Cross currency Fix vs Float
@dataclass
class XCCYSwap(DomesticSwap):

    def get_pv(self,
               leg1_discount_curve: YieldCurve,
               leg2_discount_curve: YieldCurve,
               leg2_forecast_curve: YieldCurve = None) -> float:
        return self._leg1.get_pv(leg1_discount_curve) + self._leg2.get_pv(leg2_forecast_curve, leg2_discount_curve)


# Cross currency Float vs Float
@dataclass
class XCCYBasisSwap(BasisSwap):

    def get_pv(self,
               leg1_forecast_curve: YieldCurve,
               leg1_discount_curve: YieldCurve,
               leg2_discount_curve: YieldCurve,
               leg2_forecast_curve: YieldCurve = None) -> float:
        return self._leg1.get_pv(leg1_forecast_curve, leg1_discount_curve) + self._leg2.get_pv(leg2_forecast_curve, leg2_discount_curve)

