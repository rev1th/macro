
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
import datetime as dtm

from common.chrono.tenor import Tenor
from common.currency import Currency
from common.models.base_instrument import BaseInstrument
from instruments.rate_curve_instrument import CurveInstrument
from instruments.rate_curve import RateCurve


@dataclass
class FXBase(BaseInstrument):
    _ccy1: Currency
    _: KW_ONLY
    _ccy2: Currency = Currency.USD
    _inverse: bool = False

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
    _expiry: Tenor
    
    def expiry(self) -> dtm.date:
        return self._expiry.get_date(self.value_date)


@dataclass
class FXSwap(FXBase):
    _far_leg_settle_date: dtm.date
    _near_leg_settle_date: dtm.date | None = None
    _is_ndf: bool = False
    _units: float = 1/10000  # basis point
    
    @property
    def is_ndf(self) -> bool:
        return self._is_ndf
    
    @property
    def far_leg_settle_date(self) -> dtm.date:
        return self._far_leg_settle_date
    
    @property
    def near_leg_settle_date(self) -> dtm.date:
        return self._near_leg_settle_date

@dataclass
class FXSwapC(FXSwap, CurveInstrument):
    _end: dtm.date = field(init=False)

    def __post_init__(self):
        self._end = self._far_leg_settle_date
    
    def get_pv(self, discount_curve: RateCurve, ref_discount_curve: RateCurve, spot: FXSpot) -> float:
        if self.far_leg_settle_date and self.far_leg_settle_date != spot.settle_date:
            ccy1_far_df = discount_curve.get_df(self.far_leg_settle_date) / discount_curve.get_df(spot.settle_date)
            ccy2_far_df = ref_discount_curve.get_df(self.far_leg_settle_date) / ref_discount_curve.get_df(spot.settle_date)
        else:
            ccy1_far_df = ccy2_far_df = 1
        if self.near_leg_settle_date and self.near_leg_settle_date != spot.settle_date:
            ccy1_near_df = discount_curve.get_df(self.near_leg_settle_date) / discount_curve.get_df(spot.settle_date)
            ccy2_near_df = ref_discount_curve.get_df(self.near_leg_settle_date) / ref_discount_curve.get_df(spot.settle_date)
        else:
            ccy1_near_df = ccy2_near_df = 1
        value_date = discount_curve.date
        spot_price = spot.data[value_date]
        if self.inverse:
            fwd_pts = (ccy2_far_df / ccy1_far_df - ccy2_near_df / ccy1_near_df) * spot_price
        else:
            fwd_pts = (ccy1_far_df / ccy2_far_df - ccy1_near_df / ccy2_near_df) * spot_price
        return self.notional * (fwd_pts - self.data[value_date] * self._units)


@dataclass
class FXCurve(RateCurve):
    _spot: FXSpot
    _domestic_curve: RateCurve
    
    def get_fx_rate(self, date: dtm.date) -> float:
        spot_date = self._spot.settle_date
        if date == spot_date:
            return self._spot.price
        else:
            spot_price = self._spot.data[self.date]
            if self._spot.inverse:
                spot_pv = spot_price * self.get_df(spot_date) / self._domestic_curve.get_df(spot_date)
                return spot_pv * self._domestic_curve.get_df(date) / self.get_df(date)
            else:
                spot_pv = spot_price * self._domestic_curve.get_df(spot_date) / self.get_df(spot_date)
                return spot_pv * self.get_df(date) / self._domestic_curve.get_df(date)
