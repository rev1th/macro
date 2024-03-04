
from pydantic.dataclasses import dataclass
import datetime as dtm


# frozen=True generates hash function and makes it immutable
@dataclass(frozen=True)
class DataPoint:
    date: dtm.date
    value: float = 0
    
    # @property
    # def date(self):
    #     return self._date
    
    # @property
    # def value(self):
    #     return self._value

    def __lt__(self, other):
        return self.date < other.date

    def __eq__(self, other):
        return (self.date == other.date) and (self.value == other.value)

