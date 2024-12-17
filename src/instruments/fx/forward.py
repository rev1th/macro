from pydantic.dataclasses import dataclass
import datetime as dtm

from common.chrono.tenor import Tenor
from common.currency import Currency
from .base import FXBase
from lib import fx_dates as fx_date_lib


@dataclass
class FXSpot(FXBase):
    _settle_date: dtm.date

    @classmethod
    def from_date(ccy: Currency, trade_date: dtm.date, **kwargs):
        return FXSpot(ccy, fx_date_lib.get_spot_date(ccy, trade_date), **kwargs)
    
    @property
    def settle_date(self) -> dtm.date:
        return self._settle_date

@dataclass
class FXForward(FXSpot):
    _expiry: dtm.date

    @classmethod
    def from_tenor(ccy: Currency, expiry: Tenor, trade_date: dtm.date, **kwargs):
        spot_date = fx_date_lib.get_spot_date(ccy, trade_date)
        expiry_date, delivery_date = fx_date_lib.get_forward_dates(ccy, expiry, spot_date)
        return FXForward(ccy, delivery_date, expiry_date, **kwargs)
    
    @property
    def expiry(self):
        return self._expiry
