from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm

from common.models.future import Future
from instruments.bonds.coupon_bond import FixCouponBond
from instruments.rate_curve import RateCurve


@dataclass
class BondFutureBond:
    bond: FixCouponBond
    conversion_factor: float

    ctd_date: dtm.date = field(init=False)
    repo_rate: float = field(init=False)
    net_basis: float = field(init=False)
    
    def set_ctd(self, trade_date: dtm.date, fut_price: float, delivery_dates: list[dtm.date], curve: RateCurve) -> None:
        fut_implied = fut_price * self.conversion_factor
        fwd_prices = [(self.bond.get_forward_price_curve(trade_date, date, curve), date) for date in delivery_dates]
        fwd_prices.sort(reverse=True)
        ctd_price, self.ctd_date = fwd_prices[0]
        self.net_basis = fut_implied - ctd_price
        self.repo_rate = self.bond.get_forward_repo(trade_date, self.ctd_date, fut_implied)
    
    def __lt__(self, other):
        return self.net_basis < other.net_basis

@dataclass
class BondFuture(Future):
    _first_delivery: dtm.date
    _last_delivery: dtm.date
    _basket_bonds: list[BondFutureBond] = field(kw_only=True, default_factory=list)

    underlying: str | None = field(init=False, default=None)
    
    def get_basket_metrics(self, date: dtm.date, curve: RateCurve) -> list[BondFutureBond]:
        for bfb in self._basket_bonds:
            delivery_dates = [max(self._first_delivery, bfb.bond.settle_date(date)), self._last_delivery]
            bfb.set_ctd(date, self.data[date], delivery_dates, curve)
        return sorted(self._basket_bonds, reverse=True)
    
    def get_ctd(self):
        basket_bonds = self.get_basket_metrics()
        if not basket_bonds:
            return None
        return basket_bonds[0].bond
