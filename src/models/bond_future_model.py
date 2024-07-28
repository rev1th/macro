
from pydantic.dataclasses import dataclass
import pandas as pd

from common.base_class import NameDateClass
from instruments.bond_future import BondFuture
from models import rate_curve_builder

@dataclass
class BondFutureModel(NameDateClass):
    _instruments: list[BondFuture]
    _curve_name: str

    def get_summary(self):
        res = []
        curve = rate_curve_builder.get_rate_curve(self._curve_name, self.date)
        for bf in self._instruments:
            for bfb in bf.get_basket_metrics(curve):
                res.append((bf.name, self.date, bf.expiry, bf.data[self.date],
                            bfb.bond.display_name(), bfb.conversion_factor, 
                            bfb.delivery_date, bfb.net_basis, bfb.repo))
        return pd.DataFrame(res, columns=['Name', 'Date', 'Expiry', 'Price', 'Bond', 'Conversion Factor',
                                        'Delviery Date', 'Net Basis', 'Implied Repo'])
