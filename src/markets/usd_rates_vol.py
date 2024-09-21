import datetime as dtm

from common.models.data import OptionDataFlag
from volatility.instruments.option import CallOption, PutOption
from volatility.models.listed_options_construct import ListedOptionsConstruct, ModelStrikeSlice, ModelStrikeLine

import data_api.cme as cme_api
from markets import usd_lib
from models.context import ConfigContext
from models.curve_context import CurveContext
from instruments.rate_curve import RateCurve

def get_model(series: str, value_date: dtm.date, discount_curve: RateCurve):
    futures_map = {fut.name: fut for fut in ConfigContext().get_futures(series) if fut.expiry > value_date}
    option_contracts = cme_api.get_options_contracts(series)
    options_active = [row for row in option_contracts if row[2] > value_date]
    options_data = cme_api.get_option_settle_prices(series, [r[0] for r in options_active], value_date)
    option_matrix = []
    for opt_contract_code, fut_contract_code, expiry in options_active:
        if opt_contract_code not in options_data:
            continue
        future = futures_map[fut_contract_code]
        strike_slice = []
        for strike, strike_info in options_data[opt_contract_code].items():
            call_option = CallOption(future, expiry, strike, name=f'{opt_contract_code} C {strike}')
            put_option = PutOption(future, expiry, strike, name=f'{opt_contract_code} P {strike}')
            call_weight, put_weight = 0, 0
            if OptionDataFlag.CALL in strike_info:
                call_option.data[value_date], call_weight = strike_info[OptionDataFlag.CALL]
            if OptionDataFlag.PUT in strike_info:
                put_option.data[value_date], put_weight = strike_info[OptionDataFlag.PUT]
            strike_slice.append(ModelStrikeLine(strike, call_option, put_option, call_weight, put_weight))
        if strike_slice:
            option_matrix.append(ModelStrikeSlice(expiry, discount_curve.get_df(expiry), strike_slice))
    return ListedOptionsConstruct(value_date, option_matrix, name=f'{series}-Vol')

def construct(value_date: dtm.date = None):
    if not value_date:
        value_date = usd_lib.get_last_valuation_date()
    discount_curve = CurveContext().get_rate_curve('USD-SOFR', value_date)
    return [get_model('SR3', value_date, discount_curve)]
