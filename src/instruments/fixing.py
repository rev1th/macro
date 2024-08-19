import logging
from pydantic.dataclasses import dataclass
from enum import StrEnum
import datetime as dtm

from common.models.base_instrument import BaseInstrument
from common.models.data_series import DataSeries

logger = logging.Logger(__name__)


@dataclass
class Fixing(BaseInstrument):
    pass


class RateFixingType(StrEnum):
    RFR = 'RFR'
    IBOR = 'IBOR'


class FixingCurve(DataSeries):

    def get(self, date: dtm.date):
        try:
            return self[date]
        except KeyError:
            if date > self.get_last_point()[0]:
                logger.error(f"{date} is after the last available point {self.get_last_point()[0]}")
                return self.peekitem(-1)[1]
            elif date < self.get_first_point()[0]:
                raise Exception(f"{date} is before the first available point {self.get_first_point()[0]}")
            else:
                return self.get_latest_value(date)

    def get_last_value(self) -> float:
        return self.get_last_point()[1]

