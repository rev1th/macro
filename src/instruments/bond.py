
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar, Self
import datetime as dtm
from enum import StrEnum

from lib import solver
from common.models.base_instrument import BaseInstrument
from common.chrono import Tenor, DayCount, Frequency, BDayAdjust, BDayAdjustType, Compounding
from instruments.rate_curve import RateCurve


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
    start_date: dtm.date | None = None


@dataclass
class BondYieldMethod:
    _compounding: Compounding = Compounding.SemiAnnual
    
    def get_period_dcf(self) -> float:
        return Frequency(self._compounding.value).get_unit_dcf()

@dataclass
class Bond(BaseInstrument):
    _maturity_date: dtm.date
    _daycount_type: DayCount = field(kw_only=True, default=DayCount.ACT365)
    _settle_delay: Tenor = field(kw_only=True, default_factory=Tenor.bday)
    _original_term: float = field(kw_only=True, default=None)

    _price: float = field(init=False, default=None)
    _price_type: BondPriceType = field(init=False, default=BondPriceType.CLEAN)

    settle_date: ClassVar[dtm.date]
    cashflows: ClassVar[list[CashFlow]]
    
    @property
    def maturity_date(self) -> dtm.date:
        return self._maturity_date
    
    @property
    def original_term(self) -> dtm.date:
        return self._original_term
    
    @property
    def price(self) -> float:
        return self._price
    
    def display_name(self):
        return self.name
    
    def __lt__(self, other) -> bool:
        return self.maturity_date < other.maturity_date
    
    def set_market(self, date: dtm.date, price: float, trade_date: dtm.date = None) -> None:
        # assert date <= self.maturity_date, "Value date cannot be after maturity date"
        if date:
            super().set_market(date)
            self.settle_date = date
        else:
            super().set_market(trade_date)
            self.settle_date = self._settle_delay.get_date(trade_date,
                                    BDayAdjust(BDayAdjustType.Following, self.calendar))
        self._price = price
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)
    
    def get_settle_dcf(self, date: dtm.date) -> float:
        return self._daycount_type.get_dcf(self.settle_date, date)
    
    def get_full_price(self) -> float:
        return self._price
    
    def _rate_from_curve(self, date: dtm.date, curve: RateCurve, yield_method: BondYieldMethod) -> float:
        return yield_method._compounding.get_rate(curve.get_df(date) / curve.get_df(self.settle_date),
                                                    self.get_settle_dcf(date))
    
    def get_yield(self, _: YieldType) -> float:
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
    
    def copy(self) -> Self:
        """Creates a copy of Bond"""
    
    def roll_date(self, date: dtm.date, price: float = None) -> Self:
        cls = self.copy()
        cls.set_market(date, price)
        return cls

@dataclass
class ZeroCouponBond(Bond):
    
    def set_market(self, date: dtm.date, price: float, trade_date: dtm.date = None) -> None:
        super().set_market(date, price, trade_date)
        self.cashflows = [CashFlow(self._maturity_date, 1)]
    
    def copy(self):
        return ZeroCouponBond(self._maturity_date, name=self.name,
                            _daycount_type=self._daycount_type,
                            _settle_delay=self._settle_delay)
    
    def get_yield(self, yield_method = BondYieldMethod()) -> float:
        return yield_method._compounding.get_rate(self.price / FACE_VALUE, self.get_settle_dcf(self.maturity_date))
        # return (1 - self.price / FACE_VALUE) / self.get_settle_dcf(self.maturity_date)
    
    def get_macaulay_duration(self, _) -> float:
        return self.get_settle_dcf(self.maturity_date)
    
    def get_modified_duration(self, yield_method = BondYieldMethod()) -> float:
        yt = self.get_yield(yield_method) * yield_method.get_period_dcf()
        return self.get_settle_dcf(self.maturity_date) / (1 + yt)
    
    def get_dv01(self, yield_method = BondYieldMethod()) -> float:
        return self.price * self.get_modified_duration(yield_method) * 1e-4
    
    def get_zspread(self, curve: RateCurve, yield_method = BondYieldMethod()) -> float:
        return self.get_yield() - self._rate_from_curve(self.maturity_date, curve, yield_method)
    
    def get_price_from_curve(self, curve: RateCurve) -> float:
        return FACE_VALUE * curve.get_df(self.maturity_date) / curve.get_df(self.settle_date)

@dataclass
class FixCouponBond(Bond):
    _coupon_rate: float
    _coupon_frequency: Frequency

    # coupon_dates: ClassVar[list[dtm.date]]
    acrrued_interest: ClassVar[float]
    
    @property
    def coupon_frequency(self):
        return self._coupon_frequency
    
    def display_name(self):
        return f"{self.name} {self._coupon_rate:.3%}"
    
    def set_market(self, date: dtm.date, price: float, trade_date: dtm.date = None) -> None:
        super().set_market(date, price, trade_date)
        coupon_dates = self._coupon_frequency.generate_schedule(
            self.settle_date, self.maturity_date,
            bd_adjust=BDayAdjust(BDayAdjustType.ModifiedFollowing, self.calendar), extended=True)
        c_dcf = self.get_coupon_dcf()
        self.cashflows = []
        for cd_id in range(1, len(coupon_dates)):
            self.cashflows.append(CashFlow(coupon_dates[cd_id], self._coupon_rate * c_dcf, coupon_dates[cd_id-1]))
        # Add Notional
        self.cashflows.append(CashFlow(coupon_dates[-1], 1))
        self.acrrued_interest = self.get_accrued_interest(self.settle_date, self.cashflows[0])
    
    def get_accrued_interest(self, settle_date: dtm.date, cashflow: CashFlow):
        cshf_start = cashflow.start_date
        if settle_date > cshf_start:
            accrued_fraction = (settle_date - cshf_start).days / (cashflow.date - cshf_start).days
            return cashflow.amount * accrued_fraction
        else:
            return 0
    
    def copy(self):
        return FixCouponBond(self._maturity_date, self._coupon_rate, self._coupon_frequency,
                            name=self.name, _daycount_type=self._daycount_type,
                            _settle_delay=self._settle_delay)
    
    def get_coupon_dcf(self) -> float:
        return self._coupon_frequency.get_unit_dcf()
    
    def get_full_price(self) -> float:
        return self._price + self.acrrued_interest
    
    def get_price_from_yield(self, yld: float, yield_method = BondYieldMethod()) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = yield_method.get_period_dcf()
        yc0_dcf = self.get_settle_dcf(self.cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        pv = self.cashflows[0].amount * df
        for cshf in self.cashflows[1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            pv += cshf.amount * df
        pv += self.cashflows[-1].amount * df
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_yield(self, yield_method = BondYieldMethod()) -> float:
        return solver.find_root(
            lambda yld, ym : self.price - self.get_price_from_yield(yld, ym),
            init_guess=self._coupon_rate, f_prime=self._yield_prime,
            args=(yield_method)
        )
    
    def _yield_prime(self, yld: float, yield_method: BondYieldMethod, macaulay: bool = False) -> float:
        c_dcf = self.get_coupon_dcf()
        yc_dcf = yield_method.get_period_dcf()
        cd_dcf = self.get_settle_dcf(self.cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (cd_dcf / yc_dcf)
        pv_y = self.cashflows[0].amount * df * cd_dcf
        for cshf in self.cashflows[1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            cd_dcf += c_dcf
            pv_y += cshf.amount * df * cd_dcf
        pv_y += self.cashflows[-1].amount * df * cd_dcf
        return pv_y * FACE_VALUE / (1 if macaulay else (1 + yld * yc_dcf))
    
    def get_macaulay_duration(self, yield_method = BondYieldMethod()) -> float:
        return self._yield_prime(self.get_yield(yield_method), yield_method, macaulay=True) / self.price
    
    def get_modified_duration(self, yield_method = BondYieldMethod()) -> float:
        return self._yield_prime(self.get_yield(yield_method), yield_method) / self.price
    
    def get_dv01(self, yield_method = BondYieldMethod()) -> float:
        return self._yield_prime(self.get_yield(yield_method), yield_method) * 1e-4
    
    def get_zspread(self, curve: RateCurve, yield_method = BondYieldMethod()) -> float:
        return solver.find_root(
            lambda spread, ym, curve=curve : self.price - self.get_price_from_zspread(spread, curve, ym),
            init_guess=0, f_prime=self._yield_prime,
            args=(yield_method)
        )
    
    def get_price_from_zspread(self, spread: float, curve: RateCurve, yield_method = BondYieldMethod()) -> float:
        c_dcf = self.get_coupon_dcf()
        cd_i = self.cashflows[0].date
        cd_dcf = self.get_settle_dcf(cd_i)
        settle_df = curve.get_df(self.settle_date)
        rate = yield_method._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
        df = yield_method._compounding.get_df(rate + spread, cd_dcf)
        pv = self.cashflows[0].amount * df
        for cshf in self.cashflows[1:-1]:
            cd_i = cshf.date
            cd_dcf += c_dcf
            rate = yield_method._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
            df = yield_method._compounding.get_df(rate + spread, cd_dcf)
            pv += cshf.amount * df
        pv += self.cashflows[-1].amount * df
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_curve(self, curve: RateCurve) -> float:
        pv = 0
        for cshf in self.cashflows:
            pv += cshf.amount * curve.get_df(cshf.date)
        pv /= curve.get_df(self.settle_date)
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_forward_price(self, date: dtm.date, repo_rate: float) -> float:
        spot_pv = self.price / FACE_VALUE + self.acrrued_interest
        fwd_pv = spot_pv * (1 + repo_rate * self.get_settle_dcf(date))
        for cshf in self.cashflows:
            if cshf.date <= date:
                fwd_pv -= cshf.amount * (1 + repo_rate * self.get_dcf(cshf.date, date))
            else:
                fwd_pv -= self.get_accrued_interest(date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_price_curve(self, date: dtm.date, curve: RateCurve) -> float:
        spot_pv = self.price / FACE_VALUE + self.acrrued_interest
        fwd_pv = spot_pv * curve.get_df(self.settle_date) / curve.get_df(date)
        for cshf in self.cashflows:
            if cshf.date <= date:
                fwd_pv -= cshf.amount * curve.get_df(cshf.date) / curve.get_df(date)
            else:
                fwd_pv -= self.get_accrued_interest(date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_repo(self, date: dtm.date, price: float) -> float:
        assert date > self.settle_date, f"Forward date {date} should be after {self.settle_date}"
        spot_pv = self.price / FACE_VALUE + self.acrrued_interest
        fwd_pv = price / FACE_VALUE
        realized_cash = 0
        realized_cash_dcf = 0
        for cshf in self.cashflows:
            if cshf.date <= date:
                realized_cash += cshf.amount
                realized_cash_dcf += cshf.amount * self.get_dcf(cshf.date, date)
            else:
                fwd_pv += self.get_accrued_interest(date, cshf)
                break
        return (fwd_pv - spot_pv + realized_cash) / (spot_pv * self.get_settle_dcf(date) - realized_cash_dcf)
