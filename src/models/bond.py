
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm
from enum import StrEnum

from lib import solver
from models.abstract_instrument import BaseInstrument
from models.rate_curve import RateCurve
from common.chrono import Tenor, DayCount, Frequency, BDayAdjust, BDayAdjustType, Compounding


FACE_VALUE = 100

class BondPriceType(StrEnum):
    CLEAN = 'clean'
    DIRTY = 'dirty'

class YieldType(StrEnum):
    YTM = 'ytm'
    DISCOUNT = 'discount'

@dataclass(frozen=True)
class CashFlow:
    date: dtm.date
    amount: float


@dataclass
class BondGeneric(BaseInstrument):
    _maturity_date: dtm.date
    _daycount_type: DayCount = field(kw_only=True, default=DayCount.ACT360)
    _yield_compounding: Compounding = field(kw_only=True, default=Compounding.SemiAnnual)
    _settle_delay: Tenor = field(kw_only=True, default_factory=Tenor.bday)

    _price: float = field(init=False, default=None)
    _price_type: BondPriceType = field(init=False, default=BondPriceType.CLEAN)

    settle_date: ClassVar[dtm.date]
    cashflows: ClassVar[list[CashFlow]]
    
    @property
    def maturity_date(self) -> dtm.date:
        return self._maturity_date
    
    @property
    def yield_compounding(self):
        return self._yield_compounding
    
    @property
    def price(self) -> float:
        return self._price
    
    @property
    def price_type(self):
        return self._price_type
    
    def __lt__(self, other) -> bool:
        return self.maturity_date < other.maturity_date
    
    def set_market(self, date: dtm.date, price: float) -> None:
        # assert date <= self.maturity_date, "Value date cannot be after maturity date"
        super().set_market(date)
        self.settle_date = self._settle_delay.get_date(date, BDayAdjust(BDayAdjustType.Following, self.calendar))
        self._price = price
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

    def get_settle_dcf(self, date: dtm.date) -> float:
        return self._daycount_type.get_dcf(self.settle_date, date)
    
    def get_yield_dcf(self) -> float:
        return Frequency(self._yield_compounding.value).get_unit_dcf()

    def get_yield(self, _: YieldType) -> float:
        """Gives Yield of instrument"""
    
    def get_macaulay_duration(self) -> float:
        """Gives Macaulay Duration of instrument"""
    
    def get_modified_duration(self) -> float:
        """Gives Modified Duration of instrument"""
    
    def get_dv01(self) -> float:
        """Gives DV01 of instrument"""

    def _rate_from_curve(self, date: dtm.date, curve: RateCurve) -> float:
        return self._yield_compounding.get_rate(curve.get_df(date), self.get_settle_dcf(date))

    def get_zspread(self) -> float:
        """Gives Z-Spread of instrument"""

    def get_price_from_curve(self, _: RateCurve) -> float:
        """Gives Price fom Bond curve"""

@dataclass
class Bill(BondGeneric):

    def set_market(self, date: dtm.date, price: float) -> None:
        super().set_market(date, price)
        self.cashflows = [CashFlow(self._maturity_date, 1)]

    def get_yield(self, yield_type: YieldType = None) -> float:
        match yield_type:
            case YieldType.YTM | None:
                return self._yield_compounding.get_rate(self.price / FACE_VALUE, self.get_settle_dcf(self.maturity_date))
            case YieldType.DISCOUNT:
                return (1 - self.price / FACE_VALUE) / self.get_settle_dcf(self.maturity_date)

    def get_macaulay_duration(self) -> float:
        return self.get_settle_dcf(self.maturity_date)
    
    def get_modified_duration(self) -> float:
        return self.get_settle_dcf(self.maturity_date) / (1 + self.get_yield() * self.get_yield_dcf())

    def get_dv01(self) -> float:
        return self.price * self.get_modified_duration() * 1e-4

    def get_zspread(self, curve: RateCurve) -> float:
        return self.get_yield() - self._rate_from_curve(self.maturity_date, curve)
    
    def get_price_from_curve(self, curve: RateCurve) -> float:
        return FACE_VALUE * curve.get_df(self.maturity_date)

@dataclass
class Bond(BondGeneric):
    _coupon: float
    _coupon_frequency: Frequency

    # coupon_dates: ClassVar[list[dtm.date]]
    acrrued_interest: ClassVar[float]
    
    @property
    def coupon(self) -> float:
        return self._coupon
    
    @property
    def coupon_frequency(self):
        return self._coupon_frequency
    
    def set_market(self, date: dtm.date, price: float) -> None:
        super().set_market(date, price)

        coupon_dates = self._coupon_frequency.generate_schedule(
            self.settle_date, self.maturity_date,
            bd_adjust=BDayAdjust(BDayAdjustType.ModifiedFollowing, self.calendar), extended=True)
        c_dcf = self.get_coupon_dcf()
        self.cashflows = [CashFlow(cd_i, self.coupon * c_dcf) for cd_i in coupon_dates[1:]]
        # Add Notional
        self.cashflows[-1] = CashFlow(self.cashflows[-1].date, self.cashflows[-1].amount+1)
        
        if self.settle_date > coupon_dates[0]:
            accrued_fraction = (self.settle_date - coupon_dates[0]).days / (coupon_dates[1] - coupon_dates[0]).days
            self.acrrued_interest = self.coupon * c_dcf * accrued_fraction
        else:
            self.acrrued_interest = 0
    
    def get_coupon_dcf(self) -> float:
        return self._coupon_frequency.get_unit_dcf()
    
    def get_price_from_yield(self, yld: float) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = self.get_yield_dcf()
        yc0_dcf = self.get_settle_dcf(self.cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        pv = self.cashflows[0].amount * df
        for cshf in self.cashflows[1:]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            pv += cshf.amount * df
        if self.price_type == BondPriceType.CLEAN:
            pv -= self.acrrued_interest
        return pv * FACE_VALUE

    def get_yield(self, _: YieldType = None) -> float:
        return solver.find_root(
            lambda yld : self.price - self.get_price_from_yield(yld),
            init_guess=self.coupon, f_prime=self._yield_prime,
        )
    
    def _yield_prime(self, yld: float, macaulay: bool = False) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = self.get_yield_dcf()
        cd_dcf = self.get_settle_dcf(self.cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (cd_dcf / yc_dcf)
        pv_y = self.cashflows[0].amount * df * cd_dcf
        for cshf in self.cashflows[1:]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            cd_dcf += c_dcf
            pv_y += cshf.amount * df * cd_dcf
        return pv_y * FACE_VALUE / (1 if macaulay else (1 + yld * yc_dcf))

    def get_macaulay_duration(self) -> float:
        return self._yield_prime(self.get_yield(), macaulay=True) / self.price

    def get_modified_duration(self) -> float:
        return self._yield_prime(self.get_yield()) / self.price

    def get_dv01(self) -> float:
        return self._yield_prime(self.get_yield()) * 1e-4

    def get_zspread(self, curve: RateCurve) -> float:
        return solver.find_root(
            lambda spread, curve : self.price - self.get_price_from_zspread(spread, curve),
            init_guess=0, f_prime=self._yield_prime,
            args=(curve)
        )

    def get_price_from_zspread(self, spread: float, curve: RateCurve) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = self.get_yield_dcf()
        cd_i = self.cashflows[0].date
        cd_dcf = self.get_settle_dcf(cd_i)
        rate = self._yield_compounding.get_rate(curve.get_df(cd_i), cd_dcf)
        df = 1 / (1 + (rate + spread) * yc_dcf) ** (cd_dcf / yc_dcf)
        pv = self.cashflows[0].amount * df
        for cshf in self.cashflows[1:]:
            cd_i = cshf.date
            cd_dcf += c_dcf
            rate = self._rate_from_curve(cd_i, curve)
            df = 1 / (1 + (rate + spread) * yc_dcf) ** (cd_dcf / yc_dcf)
            pv += cshf.amount * df
        if self.price_type == BondPriceType.CLEAN:
            pv -= self.acrrued_interest
        return pv * FACE_VALUE

    def get_price_from_curve(self, curve: RateCurve) -> float:
        pv = 0
        for cshf in self.cashflows:
            pv += cshf.amount * curve.get_df(cshf.date)
        if self.price_type == BondPriceType.CLEAN:
            pv -= self.acrrued_interest
        return pv * FACE_VALUE
