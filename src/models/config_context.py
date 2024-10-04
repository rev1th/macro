import datetime as dtm
from instruments.bond_future import BondFuture
from instruments.bond.coupon_bond import FixCouponBond
from instruments.bond.inflation_bond import InflationIndexBond
from instruments.bond.zero_bond import ZeroCouponBond
from instruments.rate_future import RateFuture
from instruments.swap_convention import SwapConvention


class ConfigContext(object):
    _meeting_nodes: dict[str, list[dtm.date]] = {}
    _swap_conventions: dict[str, SwapConvention] = {}
    _rate_futures: dict[str, list[RateFuture]] = {}
    _zero_bonds: dict[str, list[ZeroCouponBond]] = {}
    _coupon_bonds: dict[str, list[FixCouponBond]] = {}
    _bond_futures: dict[str, list[BondFuture]] = {}
    _inflation_bonds: dict[str, list[InflationIndexBond]] = {}
    
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
    
    def add_futures(self, name: str, futures: list[RateFuture]) -> None:
        self._rate_futures[name] = futures
    
    def get_futures(self, name: str):
        return self._rate_futures[name]
    
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
    
    def add_inflation_bonds(self, name: str, bonds: list[InflationIndexBond]) -> None:
        self._inflation_bonds[name] = bonds
    
    def has_inflation_bonds(self, name: str) -> bool:
        return name in self._inflation_bonds
    
    def get_inflation_bonds(self, name: str):
        return self._inflation_bonds[name]
    
    def get_bonds(self, name: str):
        return self._zero_bonds[name] + self._coupon_bonds[name]
    
    def add_bond_futures(self, name: str, futures: list[BondFuture]) -> None:
        self._bond_futures[name] = futures
    
    def has_bond_futures(self, name: str) -> bool:
        return name in self._bond_futures
    
    def get_bond_futures(self, name: str):
        return self._bond_futures[name]
