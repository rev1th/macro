
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar, Self
import datetime as dtm
from enum import StrEnum

from common.models.base_instrument import BaseInstrument
from common.chrono import Tenor, Frequency, Compounding
from common.chrono.daycount import DayCount
from instruments.rate_curve import RateCurve


FACE_VALUE = 100

class BondPriceType(StrEnum):
    CLEAN = 'clean'
    DIRTY = 'dirty'

@dataclass(frozen=True)
class CashFlow:
    date: dtm.date
    amount: float
    start_date: dtm.date | None = None


@dataclass
class BondYieldParameters:
    _compounding: Compounding = Compounding.SemiAnnual
    _daycount_type: DayCount = DayCount.ACT365
    
    def get_period_dcf(self) -> float:
        return Frequency(self._compounding.value).get_unit_dcf()
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

@dataclass
class Bond(BaseInstrument):
    _maturity_date: dtm.date
    _settle_delay: Tenor = field(kw_only=True, default_factory=Tenor.bday)

    cashflows: ClassVar[list[CashFlow]]
    
    @property
    def maturity_date(self):
        return self._maturity_date
    
    def display_name(self):
        return self.name
    
    def __lt__(self, other) -> bool:
        return self.maturity_date < other.maturity_date

@dataclass
class BondSnap:
    _bond: Bond
    settle_date: dtm.date
    _price: float = None
    _price_type: BondPriceType = field(init=False, default=BondPriceType.CLEAN)
    
    @property
    def maturity_date(self):
        return self._bond._maturity_date
    
    @property
    def name(self):
        return self._bond.name
    
    @property
    def price(self) -> float:
        return self._price
    
    @property
    def cashflows(self):
        return self._bond.cashflows
    
    # def __post_init__(self):
        # assert date <= self.maturity_date, "Value date cannot be after maturity date"
    
    def __lt__(self, other: Self) -> bool:
        return self.settle_date < other.settle_date and self._bond < other._bond
    
    def display_name(self):
        return self._bond.display_name()
    
    def get_full_price(self) -> float:
        return self._price
    
    def _rate_from_curve(self, date: dtm.date, curve: RateCurve, yield_params: BondYieldParameters) -> float:
        return yield_params._compounding.get_rate(curve.get_df(date) / curve.get_df(self.settle_date),
                                                    yield_params.get_dcf(self.settle_date, date))
    
    def get_yield(self, _: BondYieldParameters) -> float:
        """Gives Yield of instrument"""
    
    def get_macaulay_duration(self) -> float:
        """Gives Macaulay Duration of instrument"""
    
    def get_modified_duration(self) -> float:
        """Gives Modified Duration of instrument"""
    
    def get_dv01(self) -> float:
        """Gives DV01 of instrument"""
    
    def get_zspread(self) -> float:
        """Gives Z-Spread of instrument"""
    
    def get_price_from_curve(self, _: RateCurve) -> float:
        """Gives Price from Bond curve"""
    
    def roll_date(self, _: dtm.date) -> Self:
        """Roll settle date of bond"""

@dataclass
class ZeroCouponBond(Bond):
    
    def __post_init__(self):
        self.cashflows = [CashFlow(self._maturity_date, 1)]

@dataclass
class ZeroCouponBondSnap(BondSnap):
    _bond: ZeroCouponBond
    
    def roll_date(self, date: dtm.date):
        return ZeroCouponBondSnap(self._bond, date)
    
    def get_yield(self, yield_params = BondYieldParameters()) -> float:
        return yield_params._compounding.get_rate(self._price / FACE_VALUE,
                    yield_params.get_dcf(self.settle_date, self.maturity_date))
    
    def get_macaulay_duration(self, yield_params = BondYieldParameters()) -> float:
        return yield_params.get_dcf(self.settle_date, self.maturity_date)
    
    def get_modified_duration(self, yield_params = BondYieldParameters()) -> float:
        yt = self.get_yield(yield_params) * yield_params.get_period_dcf()
        return yield_params.get_dcf(self.settle_date, self.maturity_date) / (1 + yt)
    
    def get_dv01(self, yield_params = BondYieldParameters()) -> float:
        return self._price * self.get_modified_duration(yield_params) * 1e-4
    
    def get_zspread(self, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        return self.get_yield() - self._rate_from_curve(self.maturity_date, curve, yield_params)
    
    def get_price_from_curve(self, curve: RateCurve) -> float:
        return FACE_VALUE * curve.get_df(self.maturity_date) / curve.get_df(self.settle_date)
