import datetime as dtm

from instruments.fixing import Fixing, FixingCurve

class DataContext(object):
    _fixings: dict[str, FixingCurve] = {}
    
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(DataContext, cls).__new__(cls)
        return cls.instance
    
    def add_fixing_curve(self, code: str, fixing_curve: FixingCurve) -> None:
        self._fixings[code] = fixing_curve
    
    def get_fixings(self, code: str):
        return self._fixings[code]
    
    def get_fixing(self, fix: Fixing, date: dtm.date) -> float:
        return self._fixings[fix.name].get(date)
