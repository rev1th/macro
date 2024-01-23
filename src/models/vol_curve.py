
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import ClassVar
import datetime as dtm
import logging

from common.chrono import date_to_int
from lib.interpolator import Interpolator
from models.base_types import DataPoint, NamedDatedClass

logger = logging.Logger(__name__)


@dataclass
class VolCurve(NamedDatedClass):
    nodes_init: InitVar[list[tuple[dtm.date, float]]]
    interpolation_method: InitVar[str] = 'Step'

    _nodes: ClassVar[list[DataPoint]]
    _interpolator: ClassVar[Interpolator]
    
    def __post_init__(self, nodes_init, interpolation_method: str):
        assert len(nodes_init) > 0, "Cannot build vol curve without nodes"
        self._nodes = [DataPoint(nd[0], nd[1]) for nd in nodes_init]
        self._interpolator_class = Interpolator.fromString(interpolation_method)
        self._set_interpolator()
    
    def _set_interpolator(self) -> None:
        knots = [(date_to_int(nd.date), nd.value) for nd in self._nodes]
        self._interpolator = self._interpolator_class(knots)
    
    def update_node(self, date: dtm.date, value: float) -> None:
        for i, node in enumerate(self._nodes):
            if node.date == date:
                self._nodes[i] = DataPoint(date, value)
                self._set_interpolator()
                return
        raise Exception(f"Invalid date {date} to set node")
    
    def add_node(self, date: dtm.date, value: float) -> None:
        self._nodes.append(DataPoint(date, value))
        self._set_interpolator()
    
    def get_vol(self, date: dtm.date) -> float:
        return self._interpolator.get_value(date_to_int(date))
