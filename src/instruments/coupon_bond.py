
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm
import bisect

from common.chrono import Frequency, BDayAdjust, BDayAdjustType
from common.chrono.daycount import DayCount
from common.chrono.roll import RollConvention, RollConventionType
from common.numeric import solver
from instruments.bond import Bond, BondSnap, BondYieldParameters, CashFlow, FACE_VALUE
from instruments.rate_curve import RateCurve

@dataclass
class FixCouponBond(Bond):
    _coupon_rate: float
    _coupon_frequency: Frequency
    _first_settle_date: dtm.date
    _original_term: float = field(kw_only=True, default=None)
    
    @property
    def original_term(self):
        return self._original_term
    
    def display_name(self):
        return f"{self.name} {self._coupon_rate:.3%}"
    
    def get_coupon_dcf(self) -> float:
        return self._coupon_frequency.get_unit_dcf()
    
    def __post_init__(self):
        coupon_dates = self._coupon_frequency.generate_schedule(
            self._first_settle_date, self._maturity_date,
            roll_convention=RollConvention(RollConventionType.EndOfMonth),
            bd_adjust=BDayAdjust(BDayAdjustType.ModifiedFollowing, self.calendar), extended=True)
        c_dcf = self.get_coupon_dcf()
        self.cashflows = []
        for cd_id in range(1, len(coupon_dates)):
            self.cashflows.append(CashFlow(coupon_dates[cd_id], self._coupon_rate * c_dcf, coupon_dates[cd_id-1]))
        # Add Notional
        self.cashflows.append(CashFlow(coupon_dates[-1], 1))

@dataclass
class FixCouponBondSnap(BondSnap):
    _bond: FixCouponBond

    coupon_index: ClassVar[int]
    acrrued_interest: ClassVar[float]

    def __post_init__(self):
        self.coupon_index = bisect.bisect_right(self._bond.cashflows, self.settle_date, key=lambda cshf: cshf.date)
        self.acrrued_interest = self.get_accrued_interest(self.settle_date, self._bond.cashflows[self.coupon_index])
    
    def get_accrued_interest(self, settle_date: dtm.date, cashflow: CashFlow):
        cshf_start = cashflow.start_date
        if settle_date > cshf_start:
            accrued_fraction = (settle_date - cshf_start).days / (cashflow.date - cshf_start).days
            return cashflow.amount * accrued_fraction
        else:
            return 0
    
    def roll_date(self, date: dtm.date):
        return FixCouponBondSnap(self._bond, date)
    
    def get_full_price(self) -> float:
        return self._price + self.acrrued_interest * FACE_VALUE
    
    def get_price_from_yield(self, yld: float, yield_params = BondYieldParameters()) -> float:
        c_dcf = self._bond.get_coupon_dcf()
        c_id = self.coupon_index
        yc_dcf = yield_params.get_period_dcf()
        yc0_dcf = yield_params.get_dcf(self.settle_date, self.cashflows[c_id].date)
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        pv = self.cashflows[c_id].amount * df
        for cshf in self.cashflows[c_id+1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            pv += cshf.amount * df
        pv += self.cashflows[-1].amount * df
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_yield(self, yield_params = BondYieldParameters()) -> float:
        return solver.find_root(
            lambda yld, ym : self._price - self.get_price_from_yield(yld, ym),
            init_guess=self._bond._coupon_rate, f_prime=self._yield_prime,
            args=(yield_params)
        )
    
    def _yield_prime(self, yld: float, yield_params: BondYieldParameters, macaulay: bool = False) -> float:
        c_dcf = self._bond.get_coupon_dcf()
        c_id = self.coupon_index
        yc_dcf = yield_params.get_period_dcf()
        cd_dcf = yield_params.get_dcf(self.settle_date, self.cashflows[c_id].date)
        df = 1 / (1 + yld * yc_dcf) ** (cd_dcf / yc_dcf)
        pv_y = self.cashflows[c_id].amount * df * cd_dcf
        for cshf in self.cashflows[c_id+1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            cd_dcf += c_dcf
            pv_y += cshf.amount * df * cd_dcf
        pv_y += self.cashflows[-1].amount * df * cd_dcf
        return pv_y * FACE_VALUE / (1 if macaulay else (1 + yld * yc_dcf))
    
    def get_macaulay_duration(self, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(yield_params), yield_params, macaulay=True) / self._price
    
    def get_modified_duration(self, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(yield_params), yield_params) / self._price
    
    def get_dv01(self, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(yield_params), yield_params) * 1e-4
    
    def get_zspread(self, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        return solver.find_root(
            lambda spread, ym, curve=curve : self._price - self.get_price_from_zspread(spread, curve, ym),
            init_guess=0, f_prime=self._yield_prime,
            args=(yield_params)
        )
    
    def get_price_from_zspread(self, spread: float, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        c_dcf = self._bond.get_coupon_dcf()
        c_id = self.coupon_index
        cd_i = self.cashflows[c_id].date
        cd_dcf = yield_params.get_dcf(self.settle_date, cd_i)
        settle_df = curve.get_df(self.settle_date)
        rate = yield_params._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
        df = yield_params._compounding.get_df(rate + spread, cd_dcf)
        pv = self.cashflows[c_id].amount * df
        for cshf in self.cashflows[c_id+1:-1]:
            cd_i = cshf.date
            cd_dcf += c_dcf
            rate = yield_params._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
            df = yield_params._compounding.get_df(rate + spread, cd_dcf)
            pv += cshf.amount * df
        pv += self.cashflows[-1].amount * df
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_curve(self, curve: RateCurve) -> float:
        pv = 0
        for cshf in self.cashflows[self.coupon_index:]:
            pv += cshf.amount * curve.get_df(cshf.date)
        pv /= curve.get_df(self.settle_date)
        pv -= self.acrrued_interest
        return pv * FACE_VALUE
    
    def get_forward_price(self, date: dtm.date, repo_rate: float, repo_daycount = DayCount.ACT360) -> float:
        spot_pv = self._price / FACE_VALUE + self.acrrued_interest
        fwd_pv = spot_pv * (1 + repo_rate * repo_daycount.get_dcf(self.settle_date, date))
        for cshf in self.cashflows[self.coupon_index:]:
            if cshf.date <= date:
                fwd_pv -= cshf.amount * (1 + repo_rate * repo_daycount.get_dcf(cshf.date, date))
            else:
                fwd_pv -= self.get_accrued_interest(date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_price_curve(self, date: dtm.date, curve: RateCurve) -> float:
        spot_pv = self._price / FACE_VALUE + self.acrrued_interest
        fwd_pv = spot_pv * curve.get_df(self.settle_date) / curve.get_df(date)
        for cshf in self.cashflows[self.coupon_index:]:
            if cshf.date <= date:
                fwd_pv -= cshf.amount * curve.get_df(cshf.date) / curve.get_df(date)
            else:
                fwd_pv -= self.get_accrued_interest(date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_repo(self, date: dtm.date, price: float, repo_daycount = DayCount.ACT360) -> float:
        assert date > self.settle_date, f"Forward date {date} should be after {self.settle_date}"
        spot_pv = self._price / FACE_VALUE + self.acrrued_interest
        fwd_pv = price / FACE_VALUE
        realized_cash = 0
        realized_cash_dcf = 0
        for cshf in self.cashflows[self.coupon_index:]:
            if cshf.date <= date:
                realized_cash += cshf.amount
                realized_cash_dcf += cshf.amount * repo_daycount.get_dcf(cshf.date, date)
            else:
                fwd_pv += self.get_accrued_interest(date, cshf)
                break
        return (fwd_pv - spot_pv + realized_cash) / \
            (spot_pv * repo_daycount.get_dcf(self.settle_date, date) - realized_cash_dcf)
