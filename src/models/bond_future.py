
from pydantic.dataclasses import dataclass
import datetime as dtm
from typing import Optional, ClassVar

from common.models.future import Future
from common.chrono import Tenor
from models.bond import FixCouponBond


@dataclass
class BondFuture(Future):
    _first_delivery: dtm.date
    _last_delivery: dtm.date
    _min_tenor: Tenor
    _max_tenor: Optional[Tenor]
    _original_term: Optional[float] = None

    _ytm_standard: float = 0.06
    bonds_eligible: ClassVar[list[FixCouponBond]]

    def set_market(self, date: dtm.date, price: float, bonds: list[FixCouponBond]) -> None:
        super().set_market(date, price)
        ref_date = dtm.date(self._first_delivery.year, self._first_delivery.month, 1)
        min_maturity = self._min_tenor.get_date(ref_date)
        max_maturity = self._max_tenor.get_date(ref_date) if self._max_tenor else dtm.date.max
        self.bonds_eligible = []
        for bnd in bonds:
            if (not self._original_term or bnd.original_term <= self._original_term
                ) and min_maturity <= bnd.maturity_date <= max_maturity:
                self.bonds_eligible.append(bnd)
    
    def get_implied_repos(self) -> list[tuple[float, dtm.date, FixCouponBond]]:
        if not self.bonds_eligible:
            return []
        delivery_month = self._first_delivery.replace(day=1)
        repos_bond = []
        for bond in self.bonds_eligible:
            fwd_bond = bond.roll_date(delivery_month)
            if fwd_bond.cashflows[0].date <= self._last_delivery:
                delivery_date = fwd_bond.cashflows[0].date
                fwd_bond.set_market(delivery_date, None)
            else:
                fwd_bond.set_market(delivery_month.replace(day=min(bond.maturity_date.day, 30)), None)
                delivery_date = self._first_delivery
            conversion_factor = fwd_bond.get_price_from_yield(self._ytm_standard) / 100
            fwd_bond.set_market(delivery_date, self.price * conversion_factor)
            repo = bond.get_forward_repo(fwd_bond)
            repos_bond.append((repo, delivery_date, bond))
        repos_bond = sorted(repos_bond, reverse=True)
        return repos_bond
    
    def get_ctd(self) -> FixCouponBond:
        repos_bond = self.get_implied_repos()
        if not repos_bond:
            return None
        return repos_bond[0][2]
