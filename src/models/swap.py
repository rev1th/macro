
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
from typing import ClassVar
from abc import abstractmethod
import datetime as dtm

from common.chrono import Tenor
from models.abstract_instrument import BaseInstrument
from models.swap_convention import SwapConvention, get_swap_convention
from models.rate_curve_instrument import CurveInstrument
from models.rate_curve import YieldCurve
from models.swap_leg import SwapLeg, SwapFixLeg, SwapFloatLeg


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
        self._convention = get_swap_convention(self._convention_name)
    
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
    
    @abstractmethod
    def get_par(self, _: YieldCurve) -> float:
        """Get Par rate for Swap"""

    @abstractmethod
    def get_pv01(self, _: YieldCurve) -> float:
        """Get PV01 for Swap"""

@dataclass
class SwapCommonC(SwapCommon, CurveInstrument):
    
    def set_market(self, date: dtm.date, rate1: float = 0, rate2: float = 0) -> None:
        super().set_market(date, rate1, rate2)
        self._knot = self.end_date
        assert date <= self.knot, "Valuation date cannot be after expiry"

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
    
    def get_pv(self, forward_curve: YieldCurve, discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = forward_curve
        float_pv = self._float_leg.get_pv(forward_curve=forward_curve, discount_curve=discount_curve)
        return self._fix_leg.get_pv(discount_curve) + float_pv
    
    def get_par(self, forward_curve: YieldCurve, discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = forward_curve
        pv = self.get_pv(forward_curve=forward_curve, discount_curve=discount_curve)
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
               leg1_forward_curve: YieldCurve, leg2_forward_curve: YieldCurve,
               discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forward_curve
        leg1_pv = self._leg1.get_pv(forward_curve=leg1_forward_curve, discount_curve=discount_curve)
        leg2_pv = self._leg2.get_pv(forward_curve=leg2_forward_curve, discount_curve=discount_curve)
        return leg1_pv + leg2_pv

    def get_par(self,
                leg1_forward_curve: YieldCurve, leg2_forward_curve: YieldCurve,
                discount_curve: YieldCurve = None) -> float:
        if not discount_curve:
            discount_curve = leg2_forward_curve
        pv = self.get_pv(
            leg1_forward_curve=leg1_forward_curve,
            leg2_forward_curve=leg2_forward_curve,
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
               leg2_forward_curve: YieldCurve = None) -> float:
        return self._leg1.get_pv(leg1_discount_curve) + self._leg2.get_pv(leg2_forward_curve, leg2_discount_curve)


# Cross currency Float vs Float
@dataclass
class XCCYBasisSwap(BasisSwap):

    def get_pv(self,
               leg1_forward_curve: YieldCurve,
               leg1_discount_curve: YieldCurve,
               leg2_discount_curve: YieldCurve,
               leg2_forward_curve: YieldCurve = None) -> float:
        return self._leg1.get_pv(leg1_forward_curve, leg1_discount_curve) + self._leg2.get_pv(leg2_forward_curve, leg2_discount_curve)

