
from pydantic.dataclasses import dataclass
import datetime as dtm
from typing import Optional, ClassVar

from models.abstract_instrument import Future
from models.bond import FixCouponBond
from common.chrono import Tenor


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
    
    def get_ctd(self, date: dtm.date = None) -> FixCouponBond:
        if not self.bonds_eligible:
            return None
        fwd_ref_date = self._first_delivery
        repos_bond = []
        for bond in self.bonds_eligible:
            fwd_ref_date = fwd_ref_date.replace(day=min(bond.maturity_date.day, 30))
            fwd_bond: FixCouponBond = bond.roll_date(fwd_ref_date)
            conversion_factor = fwd_bond.get_price_from_yield(self._ytm_standard) / 100
            fwd_bond.set_market(fwd_ref_date, self.price * conversion_factor)
            repo = bond.get_forward_repo(fwd_bond)
            repos_bond.append((repo, bond))
        repos_bond = sorted(repos_bond, reverse=True)
        return repos_bond[0][1]
