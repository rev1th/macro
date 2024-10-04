from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm
import bisect

from common.chrono import Frequency, BDayAdjust, BDayAdjustType
from common.chrono.daycount import DayCount
from common.chrono.roll import RollConvention, RollConventionType
from common.numeric import solver
from instruments.bond.bond import Bond, BondSettleInfo, BondYieldParameters, CashFlow, FACE_VALUE
from instruments.rate_curve import RateCurve

@dataclass(frozen=True)
class CouponCashFlow(CashFlow):
    start_date: dtm.date

@dataclass
class CouponBondSettleInfo(BondSettleInfo):
    coupon_index: int
    acrrued_interest: float

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
        super().__post_init__()
        coupon_dates = self._coupon_frequency.generate_schedule(
            self._first_settle_date, self._maturity_date,
            roll_convention=RollConvention(RollConventionType.EndOfMonth),
            bd_adjust=BDayAdjust(BDayAdjustType.Following, self.calendar), extended=True)
        c_dcf = self.get_coupon_dcf()
        self.cashflows = []
        for cd_id in range(1, len(coupon_dates)):
            self.cashflows.append(CouponCashFlow(
                coupon_dates[cd_id], self._coupon_rate * c_dcf, coupon_dates[cd_id-1]))
        # Add Notional
        self.cashflows.append(CashFlow(coupon_dates[-1], 1))
    
    def get_accrued_interest(self, settle_date: dtm.date, cashflow: CouponCashFlow):
        cshf_start = cashflow.start_date
        if settle_date > cshf_start:
            accrued_fraction = (settle_date - cshf_start).days / (cashflow.date - cshf_start).days
            return cashflow.amount * accrued_fraction
        else:
            return 0
    
    def get_settle_info(self, settle_date: dtm.date):
        if settle_date >= self._maturity_date:
            return CouponBondSettleInfo(settle_date, -1, 0)
        coupon_index = bisect.bisect_right(self.cashflows, settle_date, key=lambda cshf: cshf.date)
        assert coupon_index < len(self.cashflows)-1, f'{self.name} settle {settle_date} after last coupon'
        acrrued_interest = self.get_accrued_interest(settle_date, self.cashflows[coupon_index])
        return CouponBondSettleInfo(settle_date, coupon_index, acrrued_interest)
    
    def set_data(self, date: dtm.date, price: float):
        super().set_data(date, price)
        settle_date = self._settle_delay.get_date(date)
        self.settle_info[date] = self.get_settle_info(settle_date)
    
    def get_cashflows(self, date: dtm.date):
        return self.cashflows[self.settle_info[date].coupon_index:]
    
    def get_accrued(self, date: dtm.date):
        return self.settle_info[date].acrrued_interest
    
    def get_full_price(self, date: dtm.date) -> float:
        return self.price(date) + self.get_accrued(date) * FACE_VALUE
    
    def _price_from_yield(self, yld: float, settle_info: CouponBondSettleInfo,
                          yield_params = BondYieldParameters()) -> float:
        c_dcf = self.get_coupon_dcf()
        cashflows = self.cashflows[settle_info.coupon_index:]
        yc_dcf = yield_params.get_period_dcf()
        yc0_dcf = yield_params.get_dcf(settle_info.date, cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (yc0_dcf / yc_dcf)
        pv = cashflows[0].amount * df
        for cshf in cashflows[1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            pv += cshf.amount * df
        pv += cashflows[-1].amount * df
        pv -= settle_info.acrrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_yield(self, date: dtm.date, yld: float, yield_params = BondYieldParameters()) -> float:
        return self._price_from_yield(yld, self.settle_info[date], yield_params)
    
    def get_yield(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        price = self.price(date)
        return solver.find_root(
            lambda yld, si, yp : price - self._price_from_yield(yld, si, yp),
            init_guess=self._coupon_rate, f_prime=self._yield_prime,
            args=(self.settle_info[date], yield_params)
        )
    
    def _yield_prime(self, yld: float, settle_info: CouponBondSettleInfo,
                     yield_params: BondYieldParameters, macaulay: bool = False) -> float:
        c_dcf = self.get_coupon_dcf()
        cashflows = self.cashflows[settle_info.coupon_index:]
        yc_dcf = yield_params.get_period_dcf()
        cd_dcf = yield_params.get_dcf(settle_info.date, cashflows[0].date)
        df = 1 / (1 + yld * yc_dcf) ** (cd_dcf / yc_dcf)
        pv_y = cashflows[0].amount * df * cd_dcf
        for cshf in cashflows[1:-1]:
            df /= (1 + yld * yc_dcf) ** (c_dcf / yc_dcf)
            cd_dcf += c_dcf
            pv_y += cshf.amount * df * cd_dcf
        pv_y += cashflows[-1].amount * df * cd_dcf
        return pv_y * FACE_VALUE / (1 if macaulay else (1 + yld * yc_dcf))
    
    def get_macaulay_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(date, yield_params), self.settle_info[date], yield_params,
                                 macaulay=True) / self.price(date)
    
    def get_modified_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(date, yield_params), self.settle_info[date], yield_params) / self.price(date)
    
    def get_dv01(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return self._yield_prime(self.get_yield(date, yield_params), self.settle_info[date], yield_params) * 1e-4
    
    def get_zspread(self, date: dtm.date, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        price = self.price(date)
        return solver.find_root(
            lambda spread, si, yp : price - self._price_from_zspread(spread, si, curve, yp),
            init_guess=0, f_prime=self._yield_prime,
            args=(self.settle_info[date], yield_params)
        )
    
    def _price_from_zspread(self, spread: float, settle_info: CouponBondSettleInfo, curve: RateCurve,
                            yield_params = BondYieldParameters()) -> float:
        c_dcf = self.get_coupon_dcf()
        cashflows = self.cashflows[settle_info.coupon_index:]
        cd_i = cashflows[0].date
        cd_dcf = yield_params.get_dcf(settle_info.date, cd_i)
        settle_df = curve.get_df(settle_info.date)
        rate = yield_params._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
        df = yield_params._compounding.get_df(rate + spread, cd_dcf)
        pv = cashflows[0].amount * df
        for cshf in cashflows[1:-1]:
            cd_i = cshf.date
            cd_dcf += c_dcf
            rate = yield_params._compounding.get_rate(curve.get_df(cd_i) / settle_df, cd_dcf)
            df = yield_params._compounding.get_df(rate + spread, cd_dcf)
            pv += cshf.amount * df
        pv += cashflows[-1].amount * df
        pv -= settle_info.acrrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_zspread(self, date: dtm.date, spread: float, curve: RateCurve,
                               yield_params = BondYieldParameters()) -> float:
        return self._price_from_zspread(spread, self.settle_info[date], curve, yield_params)
    
    def _price_from_curve(self, settle_info: CouponBondSettleInfo, curve: RateCurve) -> float:
        pv = 0
        for cshf in self.cashflows[settle_info.coupon_index:]:
            pv += cshf.amount * curve.get_df(cshf.date)
        pv /= curve.get_df(settle_info.date)
        pv -= settle_info.acrrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_curve(self, date: dtm.date, curve: RateCurve) -> float:
        return self._price_from_curve(self.settle_info[date], curve)
    
    def get_forward_price(self, date: dtm.date, forward_date: dtm.date,
                          repo_rate: float, repo_daycount = DayCount.ACT360) -> float:
        spot_pv = self.price(date) / FACE_VALUE + self.get_accrued(date)
        fwd_pv = spot_pv * (1 + repo_rate * repo_daycount.get_dcf(self.settle_date(date), forward_date))
        for cshf in self.get_cashflows(date):
            if cshf.date <= forward_date:
                fwd_pv -= cshf.amount * (1 + repo_rate * repo_daycount.get_dcf(cshf.date, forward_date))
            else:
                fwd_pv -= self.get_accrued_interest(forward_date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_price_curve(self, date: dtm.date, horizon_date: dtm.date, curve: RateCurve) -> float:
        spot_pv = self.price(date) / FACE_VALUE + self.get_accrued(date)
        fwd_pv = spot_pv * curve.get_df(self.settle_date(date)) / curve.get_df(horizon_date)
        for cshf in self.get_cashflows(date):
            if cshf.date <= horizon_date:
                fwd_pv -= cshf.amount * curve.get_df(cshf.date) / curve.get_df(horizon_date)
            else:
                fwd_pv -= self.get_accrued_interest(horizon_date, cshf)
                break
        return fwd_pv * FACE_VALUE
    
    def get_forward_repo(self, date: dtm.date, forward_date: dtm.date, forward_price: float,
                         repo_daycount = DayCount.ACT360) -> float:
        spot_pv = self.price(date) / FACE_VALUE + self.get_accrued(date)
        fwd_pv = forward_price / FACE_VALUE
        realized_cash = 0
        realized_cash_dcf = 0
        for cshf in self.get_cashflows(date):
            if cshf.date <= forward_date:
                realized_cash += cshf.amount
                realized_cash_dcf += cshf.amount * repo_daycount.get_dcf(cshf.date, forward_date)
            else:
                fwd_pv += self.get_accrued_interest(forward_date, cshf)
                break
        return (fwd_pv - spot_pv + realized_cash) / \
            (spot_pv * repo_daycount.get_dcf(self.settle_date(date), forward_date) - realized_cash_dcf)
