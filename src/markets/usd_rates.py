import datetime as dtm
import logging

from common.chrono.tenor import Tenor
from data_api import cme_client, db_reader
from instruments.rate_curve_instrument import CurveInstrument, Deposit
from instruments.swaps.template import SwapTemplate
from instruments.vol_curve import VolCurve
from markets import usd_lib
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel
from models.config_context import ConfigContext
from models.data_context import DataContext

logger = logging.Logger(__name__)

CONFIG_CONTEXT: ConfigContext = None
RATE_VOL = 1.4/100
NUM_STEPS = 7
MIN_NODE_SPACE = 7


def get_futures_for_curve(value_date: dtm.date, fixing_code: str) -> list[CurveInstrument]:
    codes = db_reader.read_future_codes(fixing_code)
    instruments_crv = []
    for code in codes:
        instruments = CONFIG_CONTEXT.get_futures(code)
        settle_data = cme_client.get_future_settle_prices(code, value_date)
        # Skip futures on expiry date, we only use fixing rates till T
        instruments_active = [ins for ins in instruments if ins.expiry > value_date]
        for ins in instruments_active:
            price = settle_data.get(ins.name)
            if price:
                logger.info(f"Setting price for future {ins.name} to {price}")
                ins.data[value_date] = price
                instruments_crv.append(CurveInstrument(ins))
            else:
                logger.info(f"No price found for future {ins.name}. Skipping")
    instruments_crv.sort()
    return instruments_crv

def get_swaps_curve(date: dtm.date, code: str, cutoff: dtm.date = None) -> list[CurveInstrument]:
    swap_prices = cme_client.get_swap_data(code, date)
    swap_instruments = []
    for tenor, rate in swap_prices.items():
        ins = SwapTemplate(code, Tenor(tenor), name=f'{code}_{tenor}').to_trade(date)
        ins.set_data(date, rate)
        curve_ins = CurveInstrument(ins)
        if cutoff and ins.end_date <= cutoff:
            curve_ins.exclude_fit = True
        swap_instruments.append(curve_ins)
    swap_instruments.sort()
    return swap_instruments

def set_step_nodes(fut_instruments: list[CurveInstrument], step_dates: list[dtm.date]) -> dtm.date:
    dt_i = 0
    for ins in fut_instruments:
        if ins.underlier.expiry > step_dates[dt_i] and not ins.exclude_fit:
            dt_i += 1
            if dt_i >= len(step_dates):
                # Skip instrument with too few unknown fixings post step end
                if (ins.underlier.expiry - last_node).days < MIN_NODE_SPACE:
                    ins.exclude_fit = True
                break
            if ins.underlier.expiry > step_dates[dt_i]:
                logger.info(f"{ins.name} expiry does not fall between step dates")
                break
        last_node = step_dates[dt_i]
        ins.set_node(last_node)
    logger.warning(f'Setting step cutoff {last_node}')
    return last_node

def _init():
    global CONFIG_CONTEXT, DATA_CONTEXT
    CONFIG_CONTEXT = ConfigContext()
    for code in ['SR3']:
        CONFIG_CONTEXT.add_futures(code, db_reader.read_IMM_futures(code))
    for code in ['SR1', 'FF']:
        CONFIG_CONTEXT.add_futures(code, db_reader.read_serial_futures(code))
    effective_t = Tenor.bday(1, usd_lib.CALENDAR)
    meeting_dates_eff = [effective_t.get_date(dt) for dt in db_reader.read_meeting_dates('FED')]
    CONFIG_CONTEXT.add_meeting_nodes('FED', meeting_dates_eff)
    
    for row in db_reader.read_swap_conventions():
        CONFIG_CONTEXT.add_swap_convention(row)
    
    DATA_CONTEXT = DataContext()
    first_date = Tenor('-3m').get_date(dtm.date.today())
    for code in ['SOFR', 'EFFR']:
        DATA_CONTEXT.add_fixing_series(code, db_reader.read_fixings(code, from_date=first_date))


def construct(value_date: dtm.date = None):
    last_close_date = usd_lib.get_last_trade_date()
    if not CONFIG_CONTEXT:
        _init()
        last_fixing_date = DATA_CONTEXT.get_fixing_series('SOFR').data.get_last_point()[0]
        if last_close_date > last_fixing_date:
            logger.warning(f"{last_close_date} is after the last available fixing {last_fixing_date}")
    if not value_date:
        value_date = last_close_date
    is_live = value_date > last_close_date
    
    meeting_nodes = [dt for dt in CONFIG_CONTEXT.get_meeting_nodes('FED') if dt > value_date][:NUM_STEPS]

    # SOFR - OIS
    fixing_name = 'SOFR'
    futs_crv = get_futures_for_curve(value_date, fixing_code=fixing_name)
    fut_cutoff = '5y' if is_live else '30m'
    fut_cutoff_date = Tenor(fut_cutoff).get_date(value_date)
    for fi in futs_crv:
        if fi.underlier.expiry > fut_cutoff_date:
            fi.exclude_fit = True
    step_cutoff = set_step_nodes(futs_crv, meeting_nodes)
    curve_instruments = futs_crv
    if futs_crv[0].node > meeting_nodes[0]:
        deposit = Deposit(meeting_nodes[0], name=fixing_name)
        deposit.data[value_date] = DataContext().get_fixing_series(fixing_name).get(value_date)
        curve_instruments = [CurveInstrument(deposit)] + futs_crv

    rate_vol_curve = VolCurve(value_date, [(value_date, RATE_VOL)], name=f'{fixing_name}-Vol')
    if not is_live:
        swaps = get_swaps_curve(value_date, 'USD_SOFR', cutoff=fut_cutoff_date)
        curve_instruments.extend(swaps)
    curve_defs = [RateCurveModel(curve_instruments,
                    _interpolation_methods = [(step_cutoff, 'LogLinear'), (None, 'LogCubic')],
                    _rate_vol_curve=rate_vol_curve, name=fixing_name)]

    # Fed fund
    fixing_name = 'EFFR'
    ff_futs_crv = get_futures_for_curve(value_date, fixing_code=fixing_name)
    ff_fut_cutoff = Tenor('13m').get_date(value_date)
    for fi in ff_futs_crv:
        if fi.underlier.expiry > ff_fut_cutoff:
            fi.exclude_fit = True
    ff_step_cutoff = set_step_nodes(ff_futs_crv, [dt for dt in meeting_nodes if dt <= step_cutoff])
    ff_curve_instruments = ff_futs_crv
    if ff_futs_crv[0].node > meeting_nodes[0]:
        ff_deposit = Deposit(meeting_nodes[0], name=fixing_name)
        ff_deposit.data[value_date] = DataContext().get_fixing_series(fixing_name).get(value_date)
        ff_curve_instruments = [CurveInstrument(ff_deposit)] + ff_futs_crv
    
    ff_rate_vol_curve = VolCurve(value_date, [(value_date, RATE_VOL)], name=f'{fixing_name}-Vol')
    if not is_live:
        ff_swaps = get_swaps_curve(value_date, code='USD_FF_SOFR', cutoff=ff_fut_cutoff)
        ff_curve_instruments.extend(ff_swaps)
        ff_interps = [(ff_step_cutoff, 'LogLinear'), (None, 'LogCubic')]
    else:
        ff_interps = [(None, 'LogLinear')]
    ff_curve_defs = [RateCurveModel(ff_curve_instruments,
                    _interpolation_methods=ff_interps,
                    _rate_vol_curve=ff_rate_vol_curve,
                    _collateral_curve_id='USD-SOFR', _spread_from='USD-SOFR', name=fixing_name)]
    
    return [
        RateCurveGroupModel(value_date, curve_defs, _calendar=usd_lib.CALENDAR, name='USD'),
        RateCurveGroupModel(value_date, ff_curve_defs, _calendar=usd_lib.CALENDAR, name='USD'),
    ]

