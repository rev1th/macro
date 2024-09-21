
from pydantic.dataclasses import dataclass
from dataclasses import InitVar, field
from typing import ClassVar, Union, Optional
import datetime as dtm
import bisect
import logging
import numpy as np

from common.chrono import get_bdate_series, Compounding
from common.chrono.calendar import Calendar
from common.chrono.daycount import DayCount
from common.base_class import NameDateClass

from lib.interpolator import Interpolator
from instruments.base_types import DataPoint

logger = logging.Logger(__name__)


# https://stackoverflow.com/questions/53990296/how-do-i-make-a-python-dataclass-inherit-hash
@dataclass(frozen=True)
class RateCurveNode(DataPoint):
    pass

# __init__ cannot be overriden so we declare InitVar and assign __post_init__
# https://docs.python.org/3/library/dataclasses.html#init-only-variables
@dataclass
class RateCurve(NameDateClass):
    nodes_init: InitVar[list[tuple[dtm.date, float]]]
    interpolation_methods: InitVar[list[tuple[dtm.date | int | None, str]]] = field(kw_only=True, default=None)

    _daycount_type: DayCount = field(kw_only=True, default=DayCount.ACT360)
    _calendar: Optional[Calendar] = field(kw_only=True, default=None)

    _nodes: ClassVar[list[RateCurveNode]]
    _interpolators: ClassVar[list[tuple[dtm.date, Interpolator]]]

    def display_name(self) -> str:
        return f"{self.name}:{self.date.strftime('%d-%b')}"
    
    def __post_init__(self, nodes_init, interpolation_methods: list[str]):
        assert len(nodes_init) > 0, "Cannot build rate curve without nodes"
        assert nodes_init[0][0] > self.date, f"First node {nodes_init[0][0]} should be after valuation date {self.date}"
        self._nodes = [RateCurveNode(nd[0], nd[1]) for nd in nodes_init]
        self._interpolation_dates = [self.date]
        self._interpolator_classes = []
        if not interpolation_methods:
            interpolation_methods = [(None, 'Default')]
        for cto, im in interpolation_methods:
            self._interpolation_dates.append(self._get_cutoff_date(cto))
            args = []
            if im == 'FlatRate':
                args.append(self._daycount_type.get_unit_dcf())
            elif im == 'FlatRateBD':
                bdates = get_bdate_series(self._interpolation_dates[-2], self._interpolation_dates[-1], self._calendar)
                cached_dcfs = [self.get_val_dcf(d) for d in bdates]
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
        nodes = [RateCurveNode(self.date, 1)] + self._nodes
        for id, ic in enumerate(self._interpolator_classes):
            cto_d = self._interpolation_dates[id]
            cto_d_next = self._interpolation_dates[id+1]
            knots = [(self.get_val_dcf(nd.date), nd.value) for nd in nodes if cto_d <= nd.date and nd.date <= cto_d_next]
            if reset:
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
                self._nodes[i] = RateCurveNode(date, value)
                self._set_interpolators(reset=False)
                return
        raise Exception(f"Invalid date {date} to set node")

    def update_nodes(self, log_values: list[float]) -> None:
        assert len(self._nodes) == len(log_values), f"Inputs don't fit nodes {len(log_values)}"
        for i, node in enumerate(self._nodes):
            self._nodes[i] = RateCurveNode(node.date, np.exp(log_values[i]))
        self._set_interpolators(reset=False)
        return
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

    def get_val_dcf(self, to_date: dtm.date) -> float:
        return self.get_dcf(self.date, to_date)

    def get_df(self, date: dtm.date) -> float:
        assert date >= self.date, f"Cannot discount before valuation date {self.date}"
        if date == self.date:
            return 1
        
        for ctd, interpolator in self._interpolators:
            if not ctd or date < ctd:
                return interpolator.get_value(self.get_val_dcf(date))
        raise Exception("Unreachable code")

    def get_forward_rate(self, from_date: dtm.date, to_date: dtm.date) -> float:
        # assert from_date >= self.date, f"Forward start date {from_date} cannot be before valuation date {self.date}"

        from_df = self.get_df(from_date)
        to_df = self.get_df(to_date)
        return (from_df / to_df - 1) / self.get_dcf(from_date, to_date)
    
    def get_spot_rate(self, date: dtm.date, compounding: Compounding = Compounding.Daily) -> float:
        assert date > self.date, f"{date} should be after valuation date {self.date}"
        df = self.get_df(date)
        dcf = self.get_val_dcf(date)
        return compounding.get_rate(df, dcf, dcf_unit=self._daycount_type.get_unit_dcf())

@dataclass
class SpreadCurve(RateCurve):
    _base_curve: RateCurve
    
    def get_spread_df(self, date: dtm.date) -> float:
        return super().get_df(date)
    
    def get_df(self, date: dtm.date) -> float:
        return self._base_curve.get_df(date) * super().get_df(date)

    def get_spread_rate(self, date: dtm.date, compounding: Compounding = Compounding.Daily) -> float:
        df = self.get_spread_df(date)
        dcf = self.get_val_dcf(date)
        return compounding.get_rate(df, dcf, dcf_unit=self._daycount_type.get_unit_dcf())

@dataclass
class RollCurve:
    _base_curve: RateCurve
    _roll_date: dtm.date

    def __post_init__(self):
        assert self._base_curve.date <= self._roll_date, "Roll date should be after base curve valuation date"
    
    def get_df(self, _: dtm.date) -> float:
        """Gives discount factor from Rolled curve"""

@dataclass
class RollForwardCurve(RollCurve):
    _roll_df: ClassVar[float]

    def __post_init__(self):
        super().__post_init__()
        self._roll_df = self._base_curve.get_df(self._roll_date)
    
    def get_df(self, date: dtm.date) -> float:
        return self._base_curve.get_df(date) / self._roll_df

@dataclass
class RollSpotCurve(RollCurve):
    _date_delta: ClassVar[dtm.timedelta]

    def __post_init__(self):
        super().__post_init__()
        self._date_delta = self._roll_date - self._base_curve.date
    
    def get_df(self, date: dtm.date) -> float:
        return self._base_curve.get_df(date - self._date_delta)
