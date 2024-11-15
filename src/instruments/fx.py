from pydantic.dataclasses import dataclass
from dataclasses import field
import datetime as dtm

from common.chrono.tenor import Tenor
from common.currency import Currency
from common.models.base_instrument import BaseInstrument
from instruments.rate_curve import RateCurve


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

@dataclass
class FXSpot(FXBase):
    _settle_date: dtm.date

    @classmethod
    def from_date(ccy: Currency, value_date: dtm.date, **kwargs):
        return FXSpot(ccy, Tenor.bday(2).get_date(value_date), **kwargs)
    
    @property
    def settle_date(self) -> dtm.date:
        return self._settle_date

@dataclass
class FXForward(FXSpot):
    _expiry: dtm.date

    @classmethod
    def from_tenor(ccy: Currency, expiry: Tenor, value_date: dtm.date, **kwargs):
        expiry_date = expiry.get_date(value_date)
        return FXForward(ccy, expiry_date, **kwargs)
    
    @property
    def expiry(self):
        return self._expiry


@dataclass
class FXSwap(FXBase):
    _far_settle_date: dtm.date
    _near_settle_date: dtm.date | None = None
    _is_ndf: bool = False
    _units: float = 1/10000  # basis point
    
    @property
    def is_ndf(self) -> bool:
        return self._is_ndf
    
    @property
    def far_settle_date(self) -> dtm.date:
        return self._far_settle_date
    
    @property
    def near_settle_date(self) -> dtm.date:
        return self._near_settle_date
    
    def get_pv(self, discount_curve: RateCurve, ref_discount_curve: RateCurve, spot: FXSpot) -> float:
        if self._far_settle_date and self._far_settle_date != spot._settle_date:
            ccy1_far_df = discount_curve.get_df(self._far_settle_date) / discount_curve.get_df(spot._settle_date)
            ccy2_far_df = ref_discount_curve.get_df(self._far_settle_date) / ref_discount_curve.get_df(spot._settle_date)
        else:
            ccy1_far_df = ccy2_far_df = 1
        if self._near_settle_date and self._near_settle_date != spot._settle_date:
            ccy1_near_df = discount_curve.get_df(self._near_settle_date) / discount_curve.get_df(spot._settle_date)
            ccy2_near_df = ref_discount_curve.get_df(self._near_settle_date) / ref_discount_curve.get_df(spot._settle_date)
        else:
            ccy1_near_df = ccy2_near_df = 1
        value_date = discount_curve.date
        spot_price = spot.data[value_date]
        if self._inverse:
            fwd_pts = (ccy2_far_df / ccy1_far_df - ccy2_near_df / ccy1_near_df) * spot_price
        else:
            fwd_pts = (ccy1_far_df / ccy2_far_df - ccy1_near_df / ccy2_near_df) * spot_price
        return (fwd_pts - self.data[value_date] * self._units)


@dataclass
class FXCurve(RateCurve):
    _spot: FXSpot
    _domestic_curve: RateCurve
    
    def get_forward_price(self, date: dtm.date) -> float:
        spot_date = self._spot.settle_date
        spot_price = self._spot.data[self.date]
        if date == spot_date:
            return spot_price
        else:
            if self._spot.inverse:
                spot_pv = spot_price * self.get_df(spot_date) / self._domestic_curve.get_df(spot_date)
                return spot_pv * self._domestic_curve.get_df(date) / self.get_df(date)
            else:
                spot_pv = spot_price * self._domestic_curve.get_df(spot_date) / self.get_df(spot_date)
                return spot_pv * self.get_df(date) / self._domestic_curve.get_df(date)
