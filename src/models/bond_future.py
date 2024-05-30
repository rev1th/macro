
from pydantic.dataclasses import dataclass
import datetime as dtm
from typing import Optional, ClassVar, Self

from common.models.future import Future
from common.chrono import Tenor
from models.bond import FixCouponBond
from models.rate_curve import RateCurve


@dataclass
class BondFutureFactor(FixCouponBond):
    _months_round: int = 1

    @classmethod
    def create(cls, bond: FixCouponBond, months_round: int):
        return BondFutureFactor(bond._maturity_date, bond._coupon_rate, bond._coupon_frequency,
                        _settle_delay=bond._settle_delay,
                        _months_round=months_round)
    
    def _next_coupon_ratio(self, date: dtm.date):
        m_diff = date.month - self.settle_date.month + (date.year - self.settle_date.year) * 12
        assert m_diff < 6, f"Unexpected next cashflow to settle date {date}"
        m_inc = self._months_round
        return int(m_diff / m_inc) * m_inc / 6
    
    def get_settle_dcf(self, date: dtm.date) -> float:
        return self._next_coupon_ratio(date) * self.get_coupon_dcf()
    
    def get_accrued_interest(self, *_):
        return self._coupon_rate * self.get_coupon_dcf() * (1 - self._next_coupon_ratio(self.cashflows[0].date))
    
    def get_conversion_factor(self, ref_date: dtm.date, yield_norm: float):
        self.set_market(ref_date, None)
        return self.get_price_from_yield(yield_norm) / 100

@dataclass
class BondFutureBond:
    bond: FixCouponBond
    conversion_factor: float

    delivery_date: Optional[dtm.date] = None
    repo: ClassVar[float]
    net_basis: ClassVar[float]
    
    def set_delivery(self, date: dtm.date, fut_price: float, curve: RateCurve) -> None:
        self.delivery_date = date
        bond_fut_price = fut_price * self.conversion_factor
        self.repo = self.bond.get_forward_repo(date, bond_fut_price)
        bond_fwd_price = self.bond.get_forward_price_curve(date, curve)
        self.net_basis = bond_fut_price - bond_fwd_price

    def __lt__(self, other: Self):
        return self.net_basis < other.net_basis


@dataclass
class BondFuture(Future):
    _first_delivery: dtm.date
    _last_delivery: dtm.date
    _min_tenor: Tenor
    _max_tenor: Optional[Tenor]
    _original_term: Optional[float] = None

    _months_round: int = 1
    _ytm_standard: float = 0.06
    bonds_eligible: ClassVar[list[BondFutureBond]]

    @property
    def first_delivery(self):
        return self._first_delivery
    
    def display_name(self):
        return f'{self.name}_{self._min_tenor._code}'
    
    def set_market(self, date: dtm.date, price: float, bonds: list[FixCouponBond]) -> None:
        super().set_market(date, price)
        ref_date = dtm.date(self._first_delivery.year, self._first_delivery.month, 1)
        min_maturity = self._min_tenor.get_date(ref_date)
        max_maturity = self._max_tenor.get_date(ref_date) if self._max_tenor else dtm.date.max
        self.bonds_eligible = []
        for bond in bonds:
            if (not self._original_term or bond.original_term <= self._original_term
                ) and min_maturity <= bond.maturity_date <= max_maturity:
                proxy = BondFutureFactor.create(bond, self._months_round)
                cf = proxy.get_conversion_factor(ref_date, self._ytm_standard)
                self.bonds_eligible.append(BondFutureBond(bond, cf))
    
    def get_basket_metrics(self, curve: RateCurve, early: bool = False) -> list[BondFutureBond]:
        if not self.bonds_eligible:
            return []
        for bfb in self.bonds_eligible:
            if early:
                delivery_date = max(self._first_delivery, bfb.bond.settle_date)
            else:
                delivery_date = self._last_delivery
            bfb.set_delivery(delivery_date, self.price, curve)
        return sorted(self.bonds_eligible, reverse=True)
    
    def get_ctd(self) -> FixCouponBond:
        repos_bond = self.get_implied_repos()
        if not repos_bond:
            return None
        return repos_bond[0][2]
