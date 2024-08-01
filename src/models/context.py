from instruments.bond import Bond
from instruments.rate_future import RateFutureC
from instruments.swap_convention import SwapConvention


class ConfigContext(object):
    _swap_conventions: dict[str, SwapConvention] = {}
    _rate_futures: dict[str, list[RateFutureC]] = {}
    _bonds: list[Bond] = []
    
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(ConfigContext, cls).__new__(cls)
        return cls.instance
    
    def add_swap_convention(self, conv: SwapConvention) -> None:
        self._swap_conventions[conv._code] = conv
    
    def get_swap_convention(self, name: str):
        return self._swap_conventions[name]
    
    def add_futures(self, code: str, futures: list[RateFutureC]) -> None:
        self._rate_futures[code] = futures
    
    def get_futures(self, code: str):
        return self._rate_futures[code]
    
    def add_bonds(self, bonds: list[Bond]) -> None:
        self._bonds = bonds
    
    def get_bonds(self):
        return self._bonds
