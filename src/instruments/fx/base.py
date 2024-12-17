from pydantic.dataclasses import dataclass
from dataclasses import field

from common.currency import Currency
from common.models.base_instrument import BaseInstrument


@dataclass
class FXBase(BaseInstrument):
    _ccy1: Currency
    _ccy2: Currency = field(kw_only=True, default=Currency.USD)
    _inverse: bool = field(kw_only=True, default=False)

    @property
    def ccy1(self):
        return self._ccy1
    
    @property
    def ccy2(self):
        return self._ccy2
    
    @property
    def inverse(self) -> bool:
        return self._inverse
