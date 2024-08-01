import datetime as dtm

from instruments.rate_curve import RateCurve

class CurveContext(object):
    _rate_curves: dict[tuple[str, dtm.date], RateCurve] = {}
    _bond_curves: dict[tuple[str, dtm.date], RateCurve] = {}

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(CurveContext, cls).__new__(cls)
        return cls.instance
    
    def update_rate_curve(self, curve: RateCurve) -> None:
        self._rate_curves[(curve.name, curve.date)] = curve
    
    def get_rate_curve(self, name: str, date: dtm.date):
        return self._rate_curves[(name, date)]

    def get_rate_curve_last(self, name: str, date: dtm.date):
        last_date = None
        for n, d in self._rate_curves:
            if n == name and d <= date:
                if not last_date or last_date < d:
                    last_date = d
        return self._rate_curves[(name, last_date)]
    
    def update_bond_curve(self, curve: RateCurve) -> None:
        self._bond_curves[(curve.name, curve.date)] = curve
    
    def get_bond_curve(self, name: str, date: dtm.date):
        return self._bond_curves[(name, date)]
