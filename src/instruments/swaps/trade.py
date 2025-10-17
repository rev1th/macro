from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm

from common.models.base_instrument import BaseInstrument
from instruments.rate_curve import RateCurve
from .convention import SwapConvention
from .leg import SwapLeg, SwapFixLeg, SwapFloatLeg

@dataclass
class SwapTrade(BaseInstrument):
    _convention: SwapConvention
    _start_date: dtm.date
    _end_date: dtm.date
    _notional: float = field(kw_only=True, default=1000000)
    _units: float = field(kw_only=True, default=1)

    _leg1: SwapLeg = field(init=False)
    _leg2: SwapLeg = field(init=False)
    
    @property
    def end_date(self):
        return self._end_date
    
    @property
    def start_date(self):
        return self._start_date

    @property
    def notional(self):
        return self._notional
    
    @property
    def convention(self):
        return self._convention
    
    def __lt__(self, other) -> bool:
        return self._end_date < other._end_date
    
    def get_par(self, _: RateCurve) -> float:
        """Get Par rate for Swap"""

    def get_pv01(self, _: RateCurve) -> float:
        """Get PV01 for Swap"""

# Single currency Fix vs Float
@dataclass
class DomesticSwap(SwapTrade):
    _fix_leg_id: int = 1
    _units: float = 1/100  # standard in %
    
    def __post_init__(self):
        assert self._fix_leg_id in (1, 2), f"Invalid fix leg specified {self._fix_leg_id}"
        self._leg1 = SwapFixLeg(self.convention.leg1, self._start_date, self._end_date, self._notional)
        self._leg2 = SwapFloatLeg(self.convention.leg2, self._start_date, self._end_date, -self._notional)
    
    @property
    def fix_leg(self) -> SwapFixLeg:
        return self._leg1
    
    @property
    def float_leg(self):
        return self._leg2
    
    def fix_rate(self, date: dtm.date) -> float:
        return self.data[date] * self._units
    
    def set_data(self, date: dtm.date, rate: float):
        self.data[date] = rate
        self.fix_leg._rate = rate * self._units
    
    def get_pv(self, forward_curve: RateCurve, discount_curve: RateCurve = None) -> float:
        if not discount_curve:
            discount_curve = forward_curve
        float_pv = self.float_leg.get_pv(forward_curve=forward_curve, discount_curve=discount_curve)
        return self.fix_leg.get_pv(discount_curve) + float_pv
    
    def get_par(self, forward_curve: RateCurve, discount_curve: RateCurve = None) -> float:
        if not discount_curve:
            discount_curve = forward_curve
        pv = self.get_pv(forward_curve=forward_curve, discount_curve=discount_curve)
        return self.data[forward_curve.date] * self._units - pv / self.fix_leg.get_annuity(discount_curve)

    def get_pv01(self, discount_curve: RateCurve) -> float:
        return self.fix_leg.get_annuity(discount_curve) / 10000


# Single currency Float vs Float
@dataclass
class BasisSwap(SwapTrade):
    _spread_leg_id: int = 2
    _units: float = 1/10000  # standard in bps

    def __post_init__(self):
        assert self._spread_leg_id in (1, 2), f"Invalid spread leg specified {self._spread_leg_id}"
        self._leg1 = SwapFloatLeg(self.convention.leg1, self._start_date, self._end_date, 
                                  self._notional, _units=self._units)
        self._leg2 = SwapFloatLeg(self.convention.leg2, self._start_date, self._end_date, 
                                  -self._notional, _units=self._units)
    
    @property
    def spread_leg(self) -> SwapFloatLeg:
        return self._leg2
    
    def spread(self, date: dtm.date) -> float:
        return self.data[date] * self._units
    
    def set_data(self, date: dtm.date, spread: float):
        self.data[date] = spread
        self.spread_leg._spread = spread * self._units
    
    def get_pv(self,
               leg1_forward_curve: RateCurve, leg2_forward_curve: RateCurve,
               discount_curve: RateCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forward_curve
        leg1_pv = self._leg1.get_pv(forward_curve=leg1_forward_curve, discount_curve=discount_curve)
        leg2_pv = self._leg2.get_pv(forward_curve=leg2_forward_curve, discount_curve=discount_curve)
        return leg1_pv + leg2_pv

    def get_par(self,
                leg1_forward_curve: RateCurve, leg2_forward_curve: RateCurve,
                discount_curve: RateCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forward_curve
        pv = self.get_pv(
            leg1_forward_curve=leg1_forward_curve,
            leg2_forward_curve=leg2_forward_curve,
            discount_curve=discount_curve)
        return self.data[leg1_forward_curve.date] * self._units - pv / self.spread_leg.get_annuity(discount_curve)

    def get_pv01(self, discount_curve: RateCurve) -> float:
        return self.spread_leg.get_annuity(discount_curve) / 10000


# Cross currency Fix vs Float
@dataclass
class XCCYSwap(DomesticSwap):

    def get_pv(self,
               leg1_discount_curve: RateCurve,
               leg2_discount_curve: RateCurve,
               leg2_forward_curve: RateCurve = None) -> float:
        return self._leg1.get_pv(leg1_discount_curve) + self._leg2.get_pv(leg2_forward_curve, leg2_discount_curve)


# Cross currency Float vs Float
@dataclass
class XCCYBasisSwap(BasisSwap):

    def get_pv(self,
               leg1_forward_curve: RateCurve,
               leg1_discount_curve: RateCurve,
               leg2_discount_curve: RateCurve,
               leg2_forward_curve: RateCurve = None) -> float:
        return self._leg1.get_pv(leg1_forward_curve, leg1_discount_curve) + self._leg2.get_pv(leg2_forward_curve, leg2_discount_curve)

