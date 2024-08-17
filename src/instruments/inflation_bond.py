from pydantic.dataclasses import dataclass
import datetime as dtm

from instruments.coupon_bond import FixCouponBond


@dataclass
class InflationIndexBond(FixCouponBond):
    _base_index_date: dtm.date
    _base_index_value: float

