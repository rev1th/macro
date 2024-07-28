
from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm
from typing import Optional, ClassVar, Self

from common.models.future import Future
from instruments.coupon_bond import FixCouponBondSnap
from instruments.rate_curve import RateCurve


@dataclass
class BondFutureBond:
    bond: FixCouponBondSnap
    conversion_factor: float

    delivery_date: Optional[dtm.date] = None
    repo: ClassVar[float]
    net_basis: ClassVar[float]
    
    def set_delivery(self, date: dtm.date, fut_price: float, curve: RateCurve) -> None:
        self.delivery_date = date
        bond_fut_implied = fut_price * self.conversion_factor
        self.repo = self.bond.get_forward_repo(date, bond_fut_implied)
        bond_fwd_price = self.bond.get_forward_price_curve(date, curve)
        self.net_basis = bond_fut_implied - bond_fwd_price

    def __lt__(self, other: Self):
        return self.net_basis < other.net_basis


@dataclass
class BondFuture(Future):
    _first_delivery: dtm.date
    _last_delivery: dtm.date
    _basket_bonds: list[BondFutureBond] = field(kw_only=True, default_factory=list)

    _underlying: Optional[str] = field(init=False, default=None)
    _settle: Optional[dtm.date] = field(init=False, default=None)

    @property
    def first_delivery(self):
        return self._first_delivery
    
    def get_basket_metrics(self, curve: RateCurve, early: bool = False) -> list[BondFutureBond]:
        for bfb in self._basket_bonds:
            if early:
                delivery_date = max(self._first_delivery, bfb.bond.settle_date)
            else:
                delivery_date = self._last_delivery
            bfb.set_delivery(delivery_date, self.data[curve.date], curve)
        return sorted(self._basket_bonds, reverse=True)
    
    def get_ctd(self):
        basket_bonds = self.get_basket_metrics()
        if not basket_bonds:
            return None
        return basket_bonds[0].bond
