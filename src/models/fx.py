
from pydantic.dataclasses import dataclass
from dataclasses import field, KW_ONLY
import datetime as dtm

from common.chrono import Tenor
from common.currency import Currency
from common.models.base_instrument import BaseInstrument
from models.rate_curve_instrument import CurveInstrument
from models.rate_curve import RateCurve


@dataclass
class FXBase(BaseInstrument):
    _ccy1: Currency
    _: KW_ONLY
    _ccy2: Currency = Currency.USD
    _inverse: bool = False
    _settle_date: dtm.date = field(init=False, default=None)

    @property
    def ccy1(self):
        return self._ccy1
    
    @property
    def ccy2(self):
        return self._ccy2
    
    @property
    def inverse(self) -> bool:
        return self._inverse
    
    @property
    def settle_date(self) -> dtm.date:
        return self._settle_date

@dataclass
class FXSpot(FXBase):
    _price: float = field(init=False, default=None)
    
    @property
    def price(self) -> float:
        return self._price

    @property
    def price_norm(self) -> float:
        if self.inverse:
            return 1 / self._price
        else:
            return self._price

    def set_market(self, date: dtm.date, price: float, settle_date: dtm.date = None) -> None:
        super().set_market(date)
        self._price = price
        self._settle_date = settle_date if settle_date else Tenor.bday(2).get_date(self.value_date)

@dataclass
class FXForward(FXSpot):
    _expiry: Tenor
    
    @property
    def expiry(self) -> dtm.date:
        return self._expiry.get_date(self.value_date)


@dataclass
class FXSwap(FXBase):
    _is_ndf: bool = False
    _units: float = 1/10000  # 1 basis point

    _far_leg_settle_date: dtm.date = field(init=False, default=None)
    _near_leg_settle_date: dtm.date = field(init=False, default=None)
    _points: float = field(init=False, default=None)
    
    @property
    def is_ndf(self) -> bool:
        return self._is_ndf
    
    @property
    def price(self) -> float:
        return self._points
    
    @property
    def points(self) -> float:
        return self._points
    
    @property
    def far_leg_settle_date(self) -> dtm.date:
        return self._far_leg_settle_date
    
    @property
    def near_leg_settle_date(self) -> dtm.date:
        return self._near_leg_settle_date
    
    def set_market(self, date: dtm.date, points: float, settle_date: dtm.date, near_date: dtm.date = None) -> None:
        super().set_market(date)
        self._points = points * self._units
        self._near_leg_settle_date = near_date
        self._settle_date = self._far_leg_settle_date = settle_date

@dataclass
class FXSwapC(FXSwap, CurveInstrument):
    _end: dtm.date = field(init=False)

    def set_market(self, date: dtm.date, points: float, settle_date: dtm.date, near_date: dtm.date = None) -> None:
        super().set_market(date, points, settle_date, near_date)
        self._end = settle_date

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
        if self.inverse:
            fwd_pts = (ccy2_far_df / ccy1_far_df - ccy2_near_df / ccy1_near_df) * spot.price
        else:
            fwd_pts = (ccy1_far_df / ccy2_far_df - ccy1_near_df / ccy2_near_df) * spot.price
        return self.notional * (fwd_pts - self.points)
