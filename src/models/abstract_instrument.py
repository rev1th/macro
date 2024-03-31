
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
from abc import abstractmethod
import datetime as dtm

from common.model import NameClass
from common.currency import Currency
from common.chrono import Calendar

@dataclass
class BaseInstrument(NameClass):
    _: KW_ONLY
    _currency: Currency = Currency.USD
    _calendar: Calendar = Calendar.USEX
    _value_date: dtm.date = field(init=False, default=None)

    @property
    def currency(self) -> Currency:
        return self._currency
    
    @property
    def calendar(self) -> str:
        return self._calendar
    
    @property
    def value_date(self) -> dtm.date:
        return self._value_date

    @property
    @abstractmethod
    def price(self) -> float:
        """Gives Price of instrument"""

    def set_market(self, date: dtm.date) -> None:
        self._value_date = date


@dataclass
class Future(BaseInstrument):
    _underlying: str
    _expiry: dtm.date
    _settle: dtm.date

    _price: float = field(init=False, default=None)

    @property
    def underlying(self) -> str:
        return self._underlying
    
    @property
    def expiry(self) -> dtm.date:
        return self._expiry

    @property
    def settle_date(self) -> dtm.date:
        return self._settle
    
    @property
    def price(self) -> float:
        return self._price
    
    def set_market(self, date: dtm.date, price: float) -> None:
        assert date <= self.expiry, "Value date cannot be after expiry"
        super().set_market(date)
        self._price = price
