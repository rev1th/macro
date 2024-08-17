from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar, Self
import datetime as dtm
from enum import StrEnum

from common.models.base_instrument import BaseInstrument
from common.models.data_series import DataSeries
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


@dataclass
class BondYieldParameters:
    _compounding: Compounding = Compounding.SemiAnnual
    _daycount_type: DayCount = DayCount.ACT365
    
    def get_period_dcf(self) -> float:
        return Frequency(self._compounding.value).get_unit_dcf()
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

@dataclass
class BondSettleInfo:
    date: dtm.date

@dataclass
class Bond(BaseInstrument):
    _maturity_date: dtm.date
    _settle_delay: Tenor = field(kw_only=True, default_factory=Tenor.bday)

    cashflows: ClassVar[list[CashFlow]]
    settle_info: ClassVar[DataSeries[dtm.date, BondSettleInfo]]
    
    def __post_init__(self):
        self.settle_info = DataSeries()
    
    @property
    def maturity_date(self):
        return self._maturity_date
    
    def display_name(self):
        return self.name
    
    def settle_date(self, date: dtm.date) -> dtm.date:
        return self.settle_info[date].date
    
    def price(self, date: dtm.date) -> float:
        return self.data[date]
    
    def get_cashflows(self, _: dtm.date):
        return self.cashflows
    
    def set_data(self, date: dtm.date, price: float):
        self.data[date] = price
    
    def __lt__(self, other: Self) -> bool:
        return self.maturity_date < other.maturity_date
    
    def _rate_from_curve(self, settle_date: dtm.date, date: dtm.date,
                        curve: RateCurve, yield_params: BondYieldParameters) -> float:
        return yield_params._compounding.get_rate(
            curve.get_df(date) / curve.get_df(settle_date), yield_params.get_dcf(settle_date, date))
    
    def get_full_price(self, date: dtm.date) -> float:
        return self.price(date)
    
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

@dataclass
class ZeroCouponBond(Bond):
    
    def __post_init__(self):
        super().__post_init__()
        self.cashflows = [CashFlow(self._maturity_date, 1)]
    
    def set_data(self, date: dtm.date, price: float):
        super().set_data(date, price)
        self.settle_info[date] = BondSettleInfo(self._settle_delay.get_date(date))
    
    def get_yield(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return yield_params._compounding.get_rate(self.price(date) / FACE_VALUE,
                    yield_params.get_dcf(self.settle_date(date), self.maturity_date))
    
    def get_macaulay_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return yield_params.get_dcf(self.settle_date(date), self.maturity_date)
    
    def get_modified_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        yt = self.get_yield(date, yield_params) * yield_params.get_period_dcf()
        return yield_params.get_dcf(self.settle_date(date), self.maturity_date) / (1 + yt)
    
    def get_dv01(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return self.price(date) * self.get_modified_duration(date, yield_params) * 1e-4
    
    def get_zspread(self, date: dtm.date, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        return self.get_yield(date) - self._rate_from_curve(self.settle_date(date), self.maturity_date, curve, yield_params)
    
    def get_price_from_curve(self, date: dtm.date, curve: RateCurve) -> float:
        return FACE_VALUE * curve.get_df(self.maturity_date) / curve.get_df(self.settle_date(date))
