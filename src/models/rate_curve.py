
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import ClassVar, Union, Optional
import datetime as dtm
import bisect
import logging
import numpy as np

from common.chrono import DayCount, get_bdate_series
from lib.interpolator import Interpolator
from models.base_types import DataPoint, NamedDatedClass, get_fixing

logger = logging.Logger(__name__)


# https://stackoverflow.com/questions/53990296/how-do-i-make-a-python-dataclass-inherit-hash
@dataclass(frozen=True)
class YieldCurveNode(DataPoint):

    @property
    def discountfactor(self):
        return self.value

# __init__ cannot be overriden so we declare InitVar and assign __post_init__
# https://docs.python.org/3/library/dataclasses.html#init-only-variables
@dataclass
class YieldCurve(NamedDatedClass):
    nodes_init: InitVar[list[tuple[dtm.date, float]]]
    interpolation_methods: InitVar[list[tuple[Optional[Union[dtm.date, int]], str]]] = [(None, 'Default')]

    _daycount_type: DayCount = DayCount.ACT360
    _calendar: str = ''

    _nodes: ClassVar[list[YieldCurveNode]]
    _interpolators: ClassVar[list[tuple[dtm.date, Interpolator]]]

    def __post_init__(self, nodes_init, interpolation_methods: list[str]):
        assert len(nodes_init) > 0, "Cannot build rate curve without nodes"
        assert nodes_init[0][0] > self.date, f"First node {nodes_init[0][0]} should be after valuation date {self.date}"
        self._nodes = [YieldCurveNode(nd[0], nd[1]) for nd in nodes_init]
        self._interpolation_dates = [self.date]
        self._interpolator_classes = []
        for cto, im in interpolation_methods:
            self._interpolation_dates.append(self._get_cutoff_date(cto))
            args = []
            if im == 'FlatRate':
                bdates = get_bdate_series(self._interpolation_dates[-2], self._interpolation_dates[-1], self._calendar)
                cached_dcfs = [self.get_dcf_d(d) for d in bdates]
                args.append(cached_dcfs)
            interp_cls = Interpolator.fromString(im)
            self._interpolator_classes.append((interp_cls, *args))
        self._interpolators = [None] * len(self._interpolator_classes)
        self._set_interpolators()

    def _get_cutoff_date(self, cutoff: Union[int, dtm.date]) -> dtm.date:
        if not cutoff:
            return dtm.date.max
        elif isinstance(cutoff, int):
            assert cutoff >= 0 and cutoff < len(self._nodes)
            return self._nodes[cutoff].date
        else:
            assert isinstance(cutoff, dtm.date), f"{cutoff} should be in date format"
            return cutoff
    
    def _set_interpolators(self, reset: bool = True) -> None:
        nodes = [YieldCurveNode(self.date, 1)] + self._nodes
        for id, ic in enumerate(self._interpolator_classes):
            cto_d = self._interpolation_dates[id]
            cto_d_next = self._interpolation_dates[id+1]
            knots = [(self.get_dcf_d(nd.date), nd.value) for nd in nodes if cto_d <= nd.date and nd.date <= cto_d_next]
            if reset or not hasattr(self._interpolators[id][1], 'update'):
                self._interpolators[id] = (cto_d_next, ic[0](knots, *ic[1:]))
            else:
                self._interpolators[id][1].update(knots)
    
    @property
    def nodes(self):
        return self._nodes

    def get_dcf_cached(self, date: dtm.date) -> float:
        try:
            return self._cached_dcfs[date][0]
        except KeyError:
            return self.get_dcf(date, self._bdates[bisect.bisect_left(self._bdates, date)])

    def get_bdates(self, from_date: dtm.date, to_date: dtm.date) -> list[dtm.date]:
        return [self._bdates[i] for i in range(self._cached_dcfs[from_date][1], self._cached_dcfs[to_date][1])]

    def get_next_bdate(self, date: dtm.date) -> float:
        try:
            return self._bdates[self._cached_dcfs[date][1]+1]
        except KeyError:
            return self._bdates[bisect.bisect_left(self._bdates, date)]

    def update_node(self, date: dtm.date, value: float) -> None:
        for i, node in enumerate(self._nodes):
            if node.date == date:
                self._nodes[i] = YieldCurveNode(date, value)
                self._set_interpolators(reset=False)
                return
        raise Exception(f"Invalid date {date} to set node")

    def update_nodes(self, log_values: list[float]) -> None:
        assert len(self._nodes) == len(log_values), f"Inputs don't fit nodes {len(log_values)}"
        for i, node in enumerate(self._nodes):
            self._nodes[i] = YieldCurveNode(node.date, np.exp(log_values[i]))
        self._set_interpolators(reset=False)
        return
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

    def get_dcf_d(self, to_date: dtm.date) -> float:
        return self.get_dcf(self.date, to_date)

    def get_df(self, date: dtm.date) -> float:
        assert date >= self.date, f"Cannot discount before valuation date {self.date}"
        if date == self.date:
            return 1
        
        for ctd, interpolator in self._interpolators:
            if not ctd or date < ctd:
                return interpolator.get_value(self.get_dcf_d(date))
        raise Exception("Unreachable code")

    def get_forward_rate(self, from_date: dtm.date, to_date: dtm.date) -> float:
        # assert from_date >= self.date, f"Forward start date {from_date} cannot be before valuation date {self.date}"

        from_df = self.get_df(from_date)
        to_df = self.get_df(to_date)
        return (from_df / to_df - 1) / self.get_dcf(from_date, to_date)

    def get_forecast_rate(self, from_date: dtm.date, to_date: dtm.date, underlying: str = None) -> float:
        assert from_date <= to_date, f"Invalid period to calculate forecast rate {from_date}-{to_date}"

        if from_date < self.date:
            bdates = get_bdate_series(from_date, min(to_date, self.date), self._calendar)
            amount = 1
            for i in range(len(bdates)-1):
                amount *= (1 + get_fixing(underlying, bdates[i]) * self.get_dcf(bdates[i], bdates[i+1]))
            
            if to_date <= self.date:
                return (amount - 1) / self.get_dcf(from_date, self.date)
            else:
                amount *= (1 + self.get_forward_rate(self.date, to_date) * self.get_dcf(self.date, to_date))
                return (amount - 1) / self.get_dcf(from_date, to_date)
        else:
            return self.get_forward_rate(from_date, to_date)
    
    def get_zero_rate(self, date: dtm.date) -> float:
        assert date > self.date, f"{date} should be after valuation date {self.date}"
        try:
            df = self.get_df(date)
            dcf_unit = self._daycount_type.get_unit_dcf()
            return (df ** (-dcf_unit / self.get_dcf_d(date)) - 1) / dcf_unit
            return -np.log(df) / self.get_dcf_d(date)
        except Exception as e:
            logger.critical(f"Failed to find zero rate for {date} {e}")
            return None
