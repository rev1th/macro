from pydantic.dataclasses import dataclass
import datetime as dtm

from instruments.bonds.coupon_bond import FixCouponBond, CouponBondSettleInfo, FACE_VALUE
from instruments.rate_curve import RateCurve
from models.data_context import DataContext


@dataclass
class InflationBondSettleInfo(CouponBondSettleInfo):
    inflation_value: float

@dataclass
class InflationIndexBond(FixCouponBond):
    _base_index_value: float
    # _base_index_date: dtm.date
    _series_id: str

    def get_inflation_value(self, date: dtm.date) -> float:
        return DataContext().get_inflation_series(self._series_id).get(date)
    
    def get_settle_info(self, settle_date: dtm.date):
        coupon_info = super().get_settle_info(settle_date)
        return InflationBondSettleInfo(settle_date, coupon_info.coupon_index,
            coupon_info.accrued_interest, self.get_inflation_value(settle_date))
    
    def get_full_price(self, date: dtm.date) -> float:
        index_ratio = self.settle_info[date].inflation_value / self._base_index_value
        return super().get_full_price(date) * index_ratio
    
    def _price_from_curve_inflation(self, settle_info: InflationBondSettleInfo,
                                    nominal_curve: RateCurve, inflation_curve: RateCurve) -> float:
        pv = 0
        for cshf in self.cashflows[settle_info.coupon_index:]:
            pv += cshf.amount * nominal_curve.get_df(cshf.date) / inflation_curve.get_df(cshf.date)
        pv /= nominal_curve.get_df(settle_info.date)
        pv -= settle_info.accrued_interest
        return pv * FACE_VALUE
    
    def get_price_from_curve_inflation(self, date: dtm.date,
                                       nominal_curve: RateCurve, inflation_curve: RateCurve) -> float:
        return self._price_from_curve_inflation(self.settle_info[date], nominal_curve, inflation_curve)

