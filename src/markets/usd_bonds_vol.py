import datetime as dtm

from common.models.data import OptionDataFlag
from volatility.instruments.option import CallOption, PutOption
from volatility.models.listed_options_construct import ListedOptionsConstruct, ModelStrikeSlice, ModelStrikeLine

from data_api import cme_client
from markets import usd_lib
from models.config_context import ConfigContext
from models.curve_context import CurveContext
from instruments.rate_curve import RateCurve

BOND_OPT_PRODS = ('ZT', 'ZF', 'ZN', 'ZB')

def get_model(series: str, value_date: dtm.date, discount_curve: RateCurve):
    if not ConfigContext().has_bond_futures(series):
        raise Exception(f'Futures not loaded for {series}')
    futures_map = {fut.name: fut for fut in ConfigContext().get_bond_futures(series)}
    option_contracts = cme_client.get_options_contracts(series)
    option_contracts_active = [row for row in option_contracts if row[2] > value_date]
    options_data = cme_client.get_option_settle_prices(series, value_date)
    option_matrix = []
    for opt_contract_code, fut_contract_code, expiry in option_contracts_active:
        future = futures_map[fut_contract_code]
        if value_date not in future.data or opt_contract_code not in options_data:
            continue
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
    return [get_model(code, value_date, discount_curve) for code in BOND_OPT_PRODS]
