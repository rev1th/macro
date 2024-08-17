import datetime as dtm
from instruments.bond import ZeroCouponBond
from instruments.coupon_bond import FixCouponBond
from instruments.rate_future import RateFutureC
from instruments.swap_convention import SwapConvention


class ConfigContext(object):
    _meeting_nodes: dict[str, list[dtm.date]] = {}
    _swap_conventions: dict[str, SwapConvention] = {}
    _rate_futures: dict[str, list[RateFutureC]] = {}
    _zero_bonds: dict[str, list[ZeroCouponBond]] = {}
    _coupon_bonds: dict[str, list[FixCouponBond]] = {}
    
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(ConfigContext, cls).__new__(cls)
        return cls.instance
    
    def add_meeting_nodes(self, name: str, dates: list[dtm.date]) -> None:
        self._meeting_nodes[name] = dates
    
    def get_meeting_nodes(self, name: str):
        return self._meeting_nodes[name]
    
    def add_swap_convention(self, conv: SwapConvention) -> None:
        self._swap_conventions[conv._code] = conv
    
    def get_swap_convention(self, name: str):
        return self._swap_conventions[name]
    
    def add_futures(self, code: str, futures: list[RateFutureC]) -> None:
        self._rate_futures[code] = futures
    
    def get_futures(self, code: str):
        return self._rate_futures[code]
    
    def add_zero_bonds(self, name: str, bonds: list[ZeroCouponBond]) -> None:
        self._zero_bonds[name] = bonds
    
    def has_zero_bonds(self, name: str) -> bool:
        return name in self._zero_bonds
    
    def add_coupon_bonds(self, name: str, bonds: list[FixCouponBond]) -> None:
        self._coupon_bonds[name] = bonds
    
    def has_coupon_bonds(self, name: str) -> bool:
        return name in self._coupon_bonds
    
    def get_coupon_bonds(self, name: str):
        return self._coupon_bonds[name]
    
    def get_bonds(self, name: str):
        return self._zero_bonds[name] + self._coupon_bonds[name]
