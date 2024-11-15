from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import ClassVar
import datetime as dtm
import numpy as np
import logging

from common.models.base_instrument import BaseInstrument
from common.chrono.tenor import Tenor
from instruments.fx import FXSwap
from instruments.rate_curve import RateCurve
from instruments.rate_future import RateFuture
from instruments.swap import SwapTrade, DomesticSwap, BasisSwap

logger = logging.Logger(__name__)

CVXADJ_RATE_TOLERANCE = 0.2e-4

# BaseModel doesn't initialize private attributes
# https://docs.pydantic.dev/latest/usage/models/#private-model-attributes
@dataclass
class CurveInstrument:
    _underlier: BaseInstrument
    _node: dtm.date = None
    _notional: float = field(kw_only=True, default=1000000)
    exclude_fit: bool = field(kw_only=True, default=False)
    _end: ClassVar[dtm.date]

    def __post_init__(self):
        if isinstance(self._underlier, RateFuture):
            self._end = self._underlier.expiry
        elif isinstance(self._underlier, SwapTrade):
            self._end = self._underlier.end_date
        elif isinstance(self._underlier, FXSwap):
            self._end = self._underlier.far_settle_date
        elif isinstance(self._underlier, Deposit):
            self._end = self._underlier._end
        if not self._node:
            self._node = self._end
    
    @property
    def underlier(self):
        return self._underlier
    
    @property
    def notional(self):
        return self._notional
    
    @property
    def name(self):
        return self._underlier.name
    
    @property
    def end(self):
        return self._end
    
    @property
    def node(self):
        return self._node
    
    def set_node(self, value: dtm.date):
        self._node = value
    
    def __lt__(self, other) -> bool:
        return self._node < other._node
    
    def get_pv(self, curve: RateCurve, collateral_curve: RateCurve = None, collateral_spot=None) -> float:
        underlier = self._underlier
        if isinstance(underlier, FXSwap):
            return self._notional * underlier.get_pv(
                curve, ref_discount_curve=collateral_curve, spot=collateral_spot)
        elif isinstance(underlier, DomesticSwap):
            return underlier.get_pv(forward_curve=curve, discount_curve=collateral_curve)
        elif isinstance(underlier, BasisSwap):
            return underlier.get_pv(leg1_forward_curve=curve, leg2_forward_curve=collateral_curve)
        return self._notional * underlier.get_pv(curve)
    
    def set_convexity(self, *args) -> None:
        if isinstance(self._underlier, RateFuture):
            self._underlier.set_convexity(*args)
        return
    
    def is_convexity_swap(self, node_date: dtm.date):
        return isinstance(self._underlier, SwapTrade) and self.exclude_fit and self._underlier.end_date > node_date
    
    def get_convexity_adjustment(self, curve: RateCurve, node_date: dtm.date, node_vol: float,
                                 collateral_curve: RateCurve = None) -> float | None:
        swap_inst = self._underlier
        if isinstance(swap_inst, DomesticSwap):
            fut_implied_par = swap_inst.get_par(curve)
            sw_crv_diff = fut_implied_par - swap_inst.fix_rate(curve.date)
        elif isinstance(swap_inst, BasisSwap):
            fut_implied_par = swap_inst.get_par(leg1_forward_curve=curve,
                                                leg2_forward_curve=collateral_curve)
            sw_crv_diff = fut_implied_par - swap_inst.spread(curve.date)
        logger.warning(f"{swap_inst.name} Implied Rate={fut_implied_par/swap_inst._units},"\
                        f"Market Rate={swap_inst.data[curve.date]}")
        if abs(sw_crv_diff) > CVXADJ_RATE_TOLERANCE:
            sw_dcf_1 = curve.get_dcf(node_date)
            sw_dcf_2 = curve.get_dcf(swap_inst.end_date)
            pv01_unit = abs(swap_inst.get_pv01(curve) * 10000 / self._notional)
            var_offset = np.log(1 + sw_crv_diff * pv01_unit / curve.get_df(swap_inst.end_date)) *\
                            12 / (2*sw_dcf_2**3 - 3*sw_dcf_1*sw_dcf_2**2 + sw_dcf_1**3)
            # var_offset = sw_crv_diff * 12 * sw_dcf_2 / (2*sw_dcf_2**3 - 3*sw_dcf_1*sw_dcf_2**2 + sw_dcf_1**3)
            var_adjusted = np.square(node_vol) + var_offset
            vol_adjusted = np.sqrt(var_adjusted) if var_adjusted > 0 else 0
            logger.warning(f'Rate Vol Adjusted for {swap_inst.end_date} is {vol_adjusted}')
            if node_vol != vol_adjusted:
                return vol_adjusted
        return None


@dataclass
class Deposit(BaseInstrument):
    _end: dtm.date
    _start: Tenor | dtm.date | None = None
    _rate: float = field(init=False)

    def start_date(self, date: dtm.date) -> dtm.date:
        if not self._start:
            return date
        elif isinstance(self._start, Tenor):
            return self._start.get_date(date)
        return self._start
    
    def get_pv(self, curve: RateCurve) -> float:
        start_date = self.start_date(curve.date)
        fcast_rate = curve.get_forward_rate(start_date, self._end)
        period_dcf = curve.get_dcf_from(start_date, self._end)
        fcast_rate *= period_dcf
        fixed_rate = np.exp(self.data[curve.date] * period_dcf) - 1
        return (fcast_rate - fixed_rate)

