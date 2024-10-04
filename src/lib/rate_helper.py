import datetime as dtm

from common.chrono import get_bdate_series
from instruments.rate_curve import RateCurve
from instruments.fixing import RateFixing
from models.data_context import DataContext

def get_forecast_rate(from_date: dtm.date, to_date: dtm.date, curve: RateCurve, fixing: RateFixing = None) -> float:
    assert from_date <= to_date, f"Invalid period to calculate forecast rate {from_date}-{to_date}"
    context = DataContext()
    if from_date < curve.date:
        bdates = get_bdate_series(from_date, min(to_date, curve.date), curve._calendar)
        amount = 1
        for i in range(len(bdates)-1):
            amount *= (1 + context.get_fixing(fixing, bdates[i]) * curve.get_dcf(bdates[i], bdates[i+1]))
        
        if to_date <= curve.date:
            return (amount - 1) / curve.get_dcf(from_date, curve.date)
        else:
            amount *= (1 + curve.get_forward_rate(curve.date, to_date) * curve.get_dcf(curve.date, to_date))
            return (amount - 1) / curve.get_dcf(from_date, to_date)
    else:
        return curve.get_forward_rate(from_date, to_date)
