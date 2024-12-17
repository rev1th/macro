from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm

from common.chrono.tenor import Tenor
from common.models.base_instrument import BaseInstrument
from models.config_context import ConfigContext
from .trade import DomesticSwap, BasisSwap

@dataclass
class SwapTemplate(BaseInstrument):
    _convention_name: str
    _end: Tenor
    # mutable defaults not allowed
    # https://docs.python.org/3/library/dataclasses.html#default-factory-functions
    _start: Tenor = field(default_factory=Tenor.bday)

    def __post_init__(self):
        if not self.name:
            self.name = f'{self._convention_name}_{self._end}'
    
    def to_trade(self, trade_date: dtm.date):
        convention = ConfigContext().get_swap_convention(self._convention_name)
        swap_class = BasisSwap if convention.is_basis() else DomesticSwap
        start_date = self._start.get_date(convention.spot_delay().get_date(trade_date))
        end_date = self._end.get_date(start_date)
        return swap_class(convention, start_date, end_date, name=self.name)
