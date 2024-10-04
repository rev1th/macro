import datetime as dtm

from instruments.fixing import RateFixing, InflationIndex

class DataContext(object):
    _fixings: dict[str, RateFixing] = {}
    _inflation_index: dict[str, InflationIndex] = {}
    
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(DataContext, cls).__new__(cls)
        return cls.instance
    
    def add_fixing_series(self, code: str, fixing: RateFixing) -> None:
        self._fixings[code] = fixing
    
    def get_fixing_series(self, code: str):
        return self._fixings[code]
    
    def get_fixing(self, fix: RateFixing, date: dtm.date) -> float:
        return self._fixings[fix.name].get(date)
    
    def add_inflation_series(self, code: str, index: InflationIndex) -> None:
        self._inflation_index[code] = index
    
    def get_inflation_series(self, code: str):
        return self._inflation_index[code]
