import dash
from dash import html, dcc
from dash import callback, Output, Input, Patch, State
import dash_ag_grid as dag
import datetime as dtm
import pandas as pd

from lib import plotter
from models.bond_curve_types import BondCurveWeightType
import main
from pages.config import *

dash.register_page(__name__, path='/')

layout = html.Div([
    html.Div([
        dcc.DatePickerRange(
            id='val-date-picker',
            clearable=True,
        ),
        html.Button('Reload Rates Curves', id='load_rates_curves'),
        dcc.Loading(
            id='rates-curves-status',
            type='default',
        ),
    ], style=DIV_STYLE),
    dcc.Tabs(children=[
        dcc.Tab(children=html.Div([
            dcc.Dropdown(['USD', 'CNY'], multi=True, id='rates-ccy-dropdown'),
            html.Div(id='rates-curves'),
        ]), label='Rates'),
        dcc.Tab(children=html.Div([
            html.Button('Reload Bond Futures', id='load_bond_futures'),
            dcc.Loading(
                id='bond-futures-status',
                type='default',
            ),
            html.Div(id='bond-futures'),
        ], style=DIV_STYLE), label='Bond Futures'),
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([bcwt.value for bcwt in BondCurveWeightType], id='bonds-weight-dropdown')
                ], style=DROPDOWN_STYLE),
                html.Button('Reload Bonds Curves', id='load_bonds_curves'),
            ], style=FORM_STYLE),
            dcc.Loading(
                id='bonds-curves-status',
                type='default',
            ),
            html.Div(id='bonds-curves'),
        ], style=DIV_STYLE), label='Bonds'),
    ]),
])

@callback(
    Output(component_id='val-date-picker', component_property='min_date_allowed'),
    Output(component_id='val-date-picker', component_property='max_date_allowed'),
    Output(component_id='val-date-picker', component_property='initial_visible_month'),
    Input(component_id='val-date-picker', component_property='n_clicks'),
)
def refresh_date(*_):
    current_date = dtm.date.today()
    return dtm.date(2024, 7, 15), current_date, current_date


@callback(
    Output(component_id='rates-curves', component_property='children'),
    Output(component_id='rates-curves-status', component_property='children'),
    State(component_id='val-date-picker', component_property='start_date'),
    Input(component_id='val-date-picker', component_property='end_date'),
    Input(component_id='rates-ccy-dropdown', component_property='value'),
    Input(component_id='load_rates_curves', component_property='n_clicks'),
    # running=[(Output(component_id='load_bonds_curves', component_property='disabled'), True, False)],
)
def load_rates_curves(start_date_str: str, end_date_str: str, ccys: list[str], *_):
    start_date = dtm.date.fromisoformat(start_date_str) if start_date_str else None
    end_date = dtm.date.fromisoformat(end_date_str) if end_date_str else None
    try:
        r_tabvals = []
        for ycg_arr in main.evaluate_rates_curves(start_date, end_date, ccys):
            graph_info = ({}, {})
            for ycg in ycg_arr:
                graph_info_dt = ycg.get_graph_info()
                for id, value in enumerate(graph_info_dt):
                    graph_info[id].update(value)
            fig = plotter.get_rates_curve_figure(*graph_info)
            nodes_df = pd.concat([ycg.get_nodes_summary() for ycg in ycg_arr])
            nodes_columns = [dict(field=col) for col in nodes_df.columns]
            for col in nodes_columns:
                if col['field'] in ('Rate', 'Change'):
                    col.update(dict(valueFormatter=get_grid_format(',.4%')))
            calibration_df = pd.concat([ycg.get_calibration_summary() for ycg in ycg_arr])
            calibration_columns = [dict(field=col) for col in calibration_df.columns]
            r_tabvals.append(dcc.Tab(children=[
                # html.Button('Refresh Curve', id='refresh'),
                dcc.Graph(figure=fig, style=GRAPH_STYLE),
                dag.AgGrid(
                    rowData=nodes_df.to_dict('records'), columnDefs=nodes_columns,
                    **AGGRID_KWARGS
                ),
                dag.AgGrid(
                    rowData=calibration_df.to_dict('records'), columnDefs=calibration_columns,
                    **AGGRID_KWARGS
                ),
            ], label=ycg.name))
        return dcc.Tabs(children=r_tabvals), None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='bonds-curves', component_property='children'),
    Output(component_id='bonds-curves-status', component_property='children'),
    State(component_id='val-date-picker', component_property='start_date'),
    State(component_id='val-date-picker', component_property='end_date'),
    # Input(component_id='rates-curves', component_property='children'),
    Input(component_id='bonds-weight-dropdown', component_property='value'),
    Input(component_id='load_bonds_curves', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_bonds_curves(start_date_str: str, end_date_str: str, weight_type: str, *_):
    start_date = dtm.date.fromisoformat(start_date_str) if start_date_str else None
    end_date = dtm.date.fromisoformat(end_date_str) if end_date_str else None
    b_tabvals = []
    try:
        for bcm_arr in main.evaluate_bonds_curves(start_date, end_date, weight_type=weight_type):
            graph_info = ({}, {})
            for bcm in bcm_arr:
                graph_info_dt = bcm.get_graph_info()
                for id, value in enumerate(graph_info_dt):
                    if value:
                        graph_info[id].update(value)
            fig = plotter.get_bonds_curve_figure(*graph_info)
            b_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=GRAPH_STYLE),
                html.Div([dcc.DatePickerSingle(
                    id='bonds-val-date-picker',
                    min_date_allowed=bcm.date,
                    initial_visible_month=bcm.date,
                    clearable=True,
                )], style=DIV_STYLE),
                dcc.Loading(
                    id='bonds-pricer-status',
                    type='default',
                ),
                # html.Div(id='bonds-pricer'),
            ], label=bcm.name))
        return dcc.Tabs(children=b_tabvals), None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='bonds-pricer', component_property='children'),
    Output(component_id='bonds-pricer-status', component_property='children'),
    Input(component_id='bonds-val-date-picker', component_property='date'),
    State(component_id='val-date-picker', component_property='end_date'),
)
def recalc_bonds(trade_date_str: str, curve_date_str: str):
    patched_table = Patch()
    trade_date = dtm.date.fromisoformat(trade_date_str) if trade_date_str else None
    curve_date = dtm.date.fromisoformat(curve_date_str) if curve_date_str else None
    try:
        measures_df = main.evaluate_bonds_roll(curve_date, trade_date)
        columns = [dict(field=col) for col in measures_df.columns]
        for col in columns:
            if col['field'] == 'Yield':
                col.update(dict(valueFormatter=get_grid_format(',.3%')))
            elif col['field'].endswith('Price'):
                col.update(dict(valueFormatter=get_grid_format(',.6f')))
        patched_table = dag.AgGrid(
            rowData=measures_df.to_dict('records'), columnDefs=columns,
            **AGGRID_KWARGS
        )
        return patched_table, None
    except Exception as ex:
        return patched_table, ex

@callback(
    Output(component_id='bond-futures', component_property='children'),
    Output(component_id='bond-futures-status', component_property='children'),
    State(component_id='val-date-picker', component_property='start_date'),
    State(component_id='val-date-picker', component_property='end_date'),
    Input(component_id='load_bond_futures', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_bond_futures(start_date_str: str, end_date_str: str, *_):
    start_date = dtm.date.fromisoformat(start_date_str) if start_date_str else None
    end_date = dtm.date.fromisoformat(end_date_str) if end_date_str else None
    try:
        bf_models = main.evaluate_bond_futures(start_date, end_date)
        measures_df = pd.concat([bfm.get_summary() for bfm in bf_models])
        columns = [dict(field=col) for col in measures_df.columns]
        for col in columns:
            if 'Repo' in col['field']:
                col.update(dict(valueFormatter=get_grid_format(',.3%')))
        table = dag.AgGrid(
            rowData=measures_df.to_dict('records'), columnDefs=columns,
            **AGGRID_KWARGS
        )
        return table, None
    except Exception as ex:
        return None, ex
