
from pydantic.dataclasses import dataclass
from typing import ClassVar, Union
import datetime as dtm
import logging
from copy import deepcopy
import numpy as np
import pandas as pd

from lib import solver
from lib.base_types import NamedClass, NamedDatedClass
from lib.date_utils import DayCount
from lib.curve_instrument import CurveInstrument
from lib.rate_future import RateFutureC
from lib.swap import DomesticSwap, BasisSwap
from lib.fx import FXSpot, FXSwapC
from rate_curve import YieldCurve
from vol_curve import VolCurve

CURVE_SOLVER_MAX_ITERATIONS = 10
CURVE_SOLVER_TOLERANCE = 1e-6
DF_UPPER_LIMIT = 1e2
DF_LOWER_LIMIT = 1e-4
CVXADJ_RATE_TOLERANCE = 0.3e-4

logger = logging.Logger(__name__)


@dataclass
class YieldCurveDefinition(NamedClass):

    _instruments: list[CurveInstrument]
    _step_cutoff: Union[dtm.date, int] = None
    _daycount_type: DayCount = None
    _collateral_curve: YieldCurve = None
    _collateral_spot: FXSpot = None
    _rate_vol_curve: VolCurve = None

    _curve: ClassVar[YieldCurve]
    _constructor: ClassVar[NamedDatedClass]

    @property
    def instruments(self) -> list[CurveInstrument]:
        return self._instruments
    
    @property
    def collateral_curve(self) -> YieldCurve:
        return self._collateral_curve
    
    @property
    def collateral_spot(self) -> YieldCurve:
        return self._collateral_spot
    
    @property
    def vol_curve(self) -> VolCurve:
        return self._rate_vol_curve
    
    @property
    def curve(self) -> YieldCurve:
        return self._curve
    
    @property
    def constructor(self):
        return self._constructor
    
    @property
    def knots(self) -> list[dtm.date]:
        knot_dates = []
        for ins in self.instruments:
            if ins.knot and (not knot_dates or knot_dates[-1] != ins.knot):
                knot_dates.append(ins.knot)
        return knot_dates
    
    def reset(self, date: dtm.date = None) -> None:
        if date:
            kwargs = {}
            if self._step_cutoff:
                kwargs['step_cutoff'] = self._step_cutoff
            # kwargs['interpolation_method'] = 'MonotoneConvex'
            if self._daycount_type:
                kwargs['_daycount_type'] = self._daycount_type
            self._curve = YieldCurve(
                f"{self.constructor.name}-{self.name}", date,
                [(k, 1) for k in self.knots],
                _calendar = self.constructor._calendar,
                **kwargs
            )
            if self.vol_curve:
                self.set_convexity()
        else:
            self._curve = None
    
    def get_calibration_errors(self) -> pd.DataFrame:
        return pd.DataFrame(
            [(ins.name, ins.knot, ins.price, self.get_instrument_pv(ins)) for ins in self.instruments],
            columns=['Name', 'Date', 'Price', 'Error']
            )
    
    def get_instrument_pv(self, instrument: CurveInstrument) -> float:
        if isinstance(instrument, FXSwapC):
            return instrument.get_pv(self.curve, ref_discount_curve=self.collateral_curve, spot=self.collateral_spot)
        elif self != self.constructor.definitions[0]:
            if isinstance(instrument, DomesticSwap):
                return instrument.get_pv(forecast_curve=self.curve, discount_curve=self.constructor.definitions[0].curve)
            elif isinstance(instrument, BasisSwap):
                return instrument.get_pv(leg1_forecast_curve=self.curve, discount_curve=self.constructor.definitions[0].curve)
            else:
                return instrument.get_pv(self.curve)
        else:
            return instrument.get_pv(self.curve)
    
    def get_calibration_error_root(self, value: float, date: dtm.date) -> float:
        self.curve.update_node(date, value)
        knot_ins = [ins for ins in self.instruments if ins.knot == date]
        assert len(knot_ins) > 0, logger.critical(f'No instruments to solve knot {date}')
        return self.get_instrument_pv(knot_ins[-1])
    
    def get_calibration_error_solver(self, values: list[float]) -> float:
        error = 0
        for ins in self.instruments:
            if ins.knot:
                pv = self.get_instrument_pv(ins)
                error += pv*pv
        return error
    
    def set_convexity(self) -> None:
        for f_ins in self.instruments:
            if isinstance(f_ins, RateFutureC):
                f_ins.set_convexity(self.vol_curve)
        return
    
    def calibrate_convexity(self, last_fixed_vol_date: dtm.date = None) -> None:
        self.constructor.build()

        if last_fixed_vol_date is None:
            last_fixed_vol_date = self.constructor.date
        for sw_ins in self.instruments:
            if isinstance(sw_ins, DomesticSwap) and sw_ins.exclude_knot and sw_ins.end_date > last_fixed_vol_date:
                fut_implied_par = sw_ins.get_par(self.curve)
                sw_crv_diff = fut_implied_par - sw_ins.fix_rate
                last_fixed_vol = self.vol_curve.get_vol(last_fixed_vol_date)
                logger.critical(f'{sw_ins.name} Implied Rate={fut_implied_par}, Market Rate={sw_ins.fix_rate}')
                if abs(sw_crv_diff) > CVXADJ_RATE_TOLERANCE:
                    sw_dcf_1 = self.curve.get_dcf(self.curve.date, last_fixed_vol_date)
                    sw_dcf_2 = self.curve.get_dcf(self.curve.date, sw_ins.end_date)
                    var_adjusted = np.square(last_fixed_vol) + 3 * sw_crv_diff / (np.square(sw_dcf_1) + np.square(sw_dcf_2))
                    vol_adjusted = np.sqrt(var_adjusted) if var_adjusted > 0 else 0
                    logger.critical(f'Rate Vol Adjusted {sw_ins.end_date} {vol_adjusted}')
                    self.vol_curve.update_node(last_fixed_vol_date, vol_adjusted)
                    return self.constructor.calibrate_convexity(last_fixed_vol_date)
                else:
                    last_fixed_vol_date = sw_ins.end_date
                    self.vol_curve.add_node(last_fixed_vol_date, last_fixed_vol)
        return


@dataclass
class YieldCurveSetConstructor(NamedDatedClass):
    _definitions: list[YieldCurveDefinition]
    _calendar: str = ''

    def __post_init__(self):
        for crv_def in self._definitions:
            crv_def._constructor = self
    
    @property
    def definitions(self) -> list[YieldCurveDefinition]:
        return self._definitions
    
    @property
    def knots(self) -> list[dtm.date]:
        knot_dates = set()
        for crv_def in self.definitions:
            knot_dates = knot_dates.union(crv_def.knots)
        return sorted(list(knot_dates))
    
    @property
    def curves(self) -> list[YieldCurve]:
        return [crv_def.curve for crv_def in self.definitions]
    
    def build_terative(self, iter: int = 1) -> bool:
        nodes_in = [deepcopy(crv_def.curve.nodes) for crv_def in self.definitions]
        for k in self.knots:
            for crv_def in self.definitions:
                if k not in crv_def.knots:
                    continue
                solver.find_root(
                    crv_def.get_calibration_error_root,
                    args=(k,),
                    bracket=[DF_LOWER_LIMIT, DF_UPPER_LIMIT]
                )
        for i, crv_def in enumerate(self.definitions):
            error = 0
            for j, nd in enumerate(crv_def.curve.nodes):
                assert nodes_in[i][j].date == nd.date, f"Unexpected nodes mismatch {nodes_in[i][j]} {nd}"
                error += abs(nodes_in[i][j].discountfactor - nd.discountfactor)
            if error > CURVE_SOLVER_TOLERANCE:
                if iter >= CURVE_SOLVER_MAX_ITERATIONS:
                    logger.error(f"Failed to fit the curve after {CURVE_SOLVER_MAX_ITERATIONS}.\n {nodes_in}")
                    return False
                return self.build_terative(iter=iter+1)
        return True
    
    def build(self) -> bool:
        for crv_def in self.definitions:
            crv_def.reset(self.date)
        return self.build_terative()
    
    def calibrate_convexity(self, last_fixed_vol_date: dtm.date = None) -> None:
        for con in self.definitions:
            con.calibrate_convexity(last_fixed_vol_date=last_fixed_vol_date)
        return
    
    def get_calibration_errors(self) -> list[pd.DataFrame]:
        return pd.concat([con.get_calibration_errors() for con in self.definitions])
    
    def get_graph_info(self) -> tuple[dict[str, int], dict[str, int]]:
        fwd_rates = {}
        node_zrates = {}
        for yc in self.curves:
            fwd_rates[yc.name] = {}
            node_zrates[yc.name] = {}
            for d in yc._bdates[:-1]:
                fwd_rates[yc.name][d] = yc.get_rate(d)
            for nd in yc._nodes:
                node_zrates[yc.name][nd.date] = yc.get_zero_rate(nd.date)
        return fwd_rates, node_zrates

