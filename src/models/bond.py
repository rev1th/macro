
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm
from enum import StrEnum

from lib import solver
from models.abstract_instrument import BaseInstrument
from common.chrono import Tenor, DayCount, Frequency, BDayAdjust, BDayAdjustType


BOND_PAR = 100

class PriceType(StrEnum):
    CLEAN = 'clean'
    DIRTY = 'dirty'

class YieldType(StrEnum):
    YTM = 'ytm'
    DISCOUNT = 'discount'
    DEFAULT = 'default'


@dataclass
class BondGeneric(BaseInstrument):
    _maturity_date: dtm.date
    _daycount_type: DayCount = field(kw_only=True, default=DayCount.ACT360)
    _yield_compound_frequency: Frequency = field(kw_only=True, default=Frequency.SemiAnnual)
    _settle_delay: Tenor = field(kw_only=True, default_factory=Tenor.bday)

    _price: float = field(init=False, default=None)
    _price_type: PriceType = field(init=False, default=PriceType.CLEAN)

    settle_date: ClassVar[dtm.date]
    
    @property
    def maturity_date(self) -> dtm.date:
        return self._maturity_date
    
    @property
    def price(self) -> float:
        return self._price
    
    @property
    def price_type(self):
        return self._price_type
    
    def __lt__(self, other) -> bool:
        return self.maturity_date < other.maturity_date
    
    def get_yield_dcf(self) -> float:
        return self._yield_compound_frequency.get_unit_dcf()
    
    def set_market(self, date: dtm.date, price: float) -> None:
        # assert date <= self.maturity_date, "Value date cannot be after maturity date"
        super().set_market(date)
        self.settle_date = self._settle_delay.get_date(date, BDayAdjust(BDayAdjustType.Following, self.calendar))
        self._price = price
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

    def get_yield(self, _: YieldType) -> float:
        """Gives Yield of instrument"""
    
    def get_macaulay_duration(self) -> float:
        """Gives Macaulay Duration of instrument"""
    
    def get_modified_duration(self) -> float:
        """Gives Modified Duration of instrument"""
    
    def get_dv01(self) -> float:
        """Gives DV01 of instrument"""

@dataclass
class Bill(BondGeneric):

    def get_yield(self, yield_type: YieldType = YieldType.DEFAULT) -> float:
        match yield_type:
            case YieldType.YTM | YieldType.DEFAULT:
                yc_dcf = self.get_yield_dcf()
                return ((BOND_PAR / self.price) ** (yc_dcf / self.get_dcf(self.settle_date, self.maturity_date)) - 1) / yc_dcf
            case YieldType.DISCOUNT:
                return (1 - self.price / BOND_PAR) / self.get_dcf(self.settle_date, self.maturity_date)

    def get_macaulay_duration(self) -> float:
        return self.get_dcf(self.settle_date, self.maturity_date)
    
    def get_modified_duration(self) -> float:
        return self.get_dcf(self.settle_date, self.maturity_date) / (1 + self.get_yield() * self.get_yield_dcf())

    def get_dv01(self) -> float:
        return self.price * self.get_modified_duration() * 1e-4

@dataclass
class Bond(BondGeneric):
    _coupon: float
    _coupon_frequency: Frequency

    coupon_dates: ClassVar[list[dtm.date]]
    
    def set_market(self, date: dtm.date, price: float) -> None:
        super().set_market(date, price)
        self.coupon_dates = self._coupon_frequency.generate_schedule(
            self.value_date, self.maturity_date,
            bd_adjust=BDayAdjust(BDayAdjustType.Previous, self.calendar), extended=True)
    
    @property
    def coupon(self) -> float:
        return self._coupon
    
    @property
    def coupon_frequency(self):
        return self._coupon_frequency
    
    def get_coupon_dcf(self) -> float:
        return self._coupon_frequency.get_unit_dcf()
    
    def get_yield_dcf(self) -> float:
        if self._yield_compound_frequency:
            return self._yield_compound_frequency.get_unit_dcf()
        else:
            return self._coupon_frequency.get_unit_dcf()
    
    def get_acrrued_interest(self) -> float:
        c_d_real = (self.settle_date - self.coupon_dates[0]).days / (self.coupon_dates[1] - self.coupon_dates[0]).days
        return self.coupon * self.get_coupon_dcf() * c_d_real
    
    def get_price_from_yield(self, yld: float) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = self.get_yield_dcf()
        yc0_dcf = self.get_dcf(self.settle_date, self.coupon_dates[1])
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        pv = self.coupon * c_dcf * df
        for _ in range(2, len(self.coupon_dates)):
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            pv += self.coupon * c_dcf * df
        pv += df
        if self.price_type == PriceType.CLEAN:
            pv -= self.get_acrrued_interest()
        return pv * BOND_PAR

    def get_yield(self, _: YieldType = YieldType.DEFAULT) -> float:
        return solver.find_root(
            self._yield_error,
            init_guess=self.coupon, f_prime=self._yield_prime,
        )
    
    def _yield_prime(self, yld: float, macaulay: bool = False) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = self.get_yield_dcf()
        yc0_dcf = self.get_dcf(self.settle_date, self.coupon_dates[1])
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        dcf = yc0_dcf
        pv_y = self.coupon * c_dcf * df * dcf
        for _ in range(2, len(self.coupon_dates)):
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            dcf += c_dcf
            pv_y += self.coupon * c_dcf * df * dcf
        pv_y += df * dcf
        return pv_y * BOND_PAR / (1 if macaulay else (1 + yld * yc_dcf))
    
    def _yield_error(self, yld: float) -> float:
        return self.price - self.get_price_from_yield(yld)

    def get_macaulay_duration(self) -> float:
        return self._yield_prime(self.get_yield(), macaulay=True) / self.price

    def get_modified_duration(self) -> float:
        return self._yield_prime(self.get_yield()) / self.price

    def get_dv01(self) -> float:
        return self._yield_prime(self.get_yield()) * 1e-4
