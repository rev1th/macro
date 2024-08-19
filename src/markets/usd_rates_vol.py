import datetime as dtm

from common.models.data import OptionDataFlag
from volatility.instruments.option import CallOption, PutOption
from volatility.models.vol_surface_model import VolSurfaceModelListed

import data_api.cme as cme_api
from markets import usd_lib
from models.context import ConfigContext

def construct(val_date: dtm.date = None):
    if not val_date:
        val_date = usd_lib.get_last_valuation_date()
    series = 'SR3'
    futures_map = {fut.name: fut for fut in ConfigContext().get_futures(series) if fut.expiry > val_date}
    option_contracts = cme_api.get_options_contracts(series)
    options_data = cme_api.get_option_settle_prices(series, [r[0] for r in option_contracts], val_date)
    option_chain = dict()
    for opt_contract_code, fut_contract_code, expiry in option_contracts:
        if opt_contract_code not in options_data:
            continue
        future = futures_map[fut_contract_code]
        for strike, strike_info in options_data[opt_contract_code].items():
            call_opt = CallOption(future, expiry, strike)
            put_opt = PutOption(future, expiry, strike)
            if OptionDataFlag.CALL in strike_info:
                call_opt.data[val_date] = strike_info[OptionDataFlag.CALL]
            if OptionDataFlag.PUT in strike_info:
                put_opt.data[val_date] = strike_info[OptionDataFlag.PUT]
            option_chain[expiry, strike] = (call_opt, put_opt)
    return VolSurfaceModelListed(val_date, option_chain, name=f'{series}-Vol')
