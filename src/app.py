
from dash import Dash, html, dash_table, dcc
from dash import callback, Output, Input, Patch, State
from dash.dash_table import Format
import datetime as dtm
import pandas as pd

from lib import plotter
from main import evaluate_rates, evaluate_bonds


_CACHED_DATA = {}
_GRAPH_STYLE = {'height': '100vh'}
_TABLE_KWARGS = dict(sort_action='native', sort_mode='multi', sort_by=[],
                filter_action='native')
_DIV_STYLE = {'textAlign': 'center'}

app = Dash(__name__)
app.layout = html.Div([
    html.H3('Macro Analytics App', style=_DIV_STYLE),
    html.Br(),
    html.Div([
        dcc.DatePickerSingle(
            id='val-date-picker',
            max_date_allowed=dtm.date.today(),
            clearable=True,
        ),
        html.Button('Reload Rates Curves', id='load_rates'),
        dcc.Loading(
            id='rates-curves-loading',
            type='default',
        ),
    ], style=_DIV_STYLE),
    dcc.Tabs(children=[
        dcc.Tab(children=html.Div(id='rates-curves'), label='Rates'),
        dcc.Tab(children=html.Div([
            html.Button('Reload Bonds Curves', id='load_bonds'),
            dcc.Loading(
                id='bonds-curves-loading',
                type='default',
            ),
            html.Div(id='bonds-curves'),
        ], style=_DIV_STYLE), label='Bonds'),
    ]),
])

@callback(
    Output(component_id='rates-curves', component_property='children'),
    Output(component_id='rates-curves-loading', component_property='children'),
    Input(component_id='val-date-picker', component_property='date'),
    Input(component_id='load_rates', component_property='n_clicks'),
    running=[(Output(component_id='load_bonds', component_property='disabled'), True, False)],
)
def load_rates(date_str: str, *_):
    value_date = dtm.date.fromisoformat(date_str) if date_str else None
    try:
        r_tabvals = []
        for ycg_arr in evaluate_rates(value_date):
            summary_df = pd.concat([ycg.get_calibration_summary() for ycg in ycg_arr])
            graph_info = ({}, {})
            for ycg in ycg_arr:
                graph_info_dt = ycg.get_graph_info()
                for id, value in enumerate(graph_info_dt):
                    graph_info[id].update(value)
            fig = plotter.get_rates_curve_figure(*graph_info)
            columns = [dict(id=col, name=col) for col in summary_df.columns]
            r_tabvals.append(dcc.Tab(children=[
                # html.Button('Refresh Curve', id='refresh'),
                dcc.Graph(figure=fig, style=_GRAPH_STYLE),
                dash_table.DataTable(
                    data=summary_df.to_dict('records'), columns=columns,
                    page_size=20, **_TABLE_KWARGS
                ),
            ], label=ycg.name))
        return dcc.Tabs(children=r_tabvals), None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='bonds-curves', component_property='children'),
    Output(component_id='bonds-curves-loading', component_property='children'),
    State(component_id='val-date-picker', component_property='date'),
    # Input(component_id='rates-curves', component_property='children'),
    Input(component_id='load_bonds', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_bonds(date_str: str, *_):
    value_date = dtm.date.fromisoformat(date_str) if date_str else None
    b_tabvals = []
    try:
        _CACHED_DATA['bonds-models'] = evaluate_bonds(value_date)
        for bcm in _CACHED_DATA['bonds-models']:
            fig = plotter.get_bonds_curve_figure(*bcm.get_graph_info())
            b_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=_GRAPH_STYLE),
                html.Div([dcc.DatePickerSingle(
                    id='bonds-val-date-picker',
                    min_date_allowed=bcm.date,
                    initial_visible_month=bcm.date,
                    clearable=True,
                )], style=_DIV_STYLE),
                dcc.Loading(
                    id='bonds-pricer-loading',
                    type='default',
                ),
                html.Div(id='bonds-pricer'),
            ], label=bcm.name))
        return dcc.Tabs(children=b_tabvals), None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='bonds-pricer', component_property='children'),
    Output(component_id='bonds-pricer-loading', component_property='children'),
    Input(component_id='bonds-val-date-picker', component_property='date'),
)
def recalc_bonds(date_str: str):
    patched_table = Patch()
    if date_str:
        trade_date = dtm.date.fromisoformat(date_str)
    else:
        trade_date = None
    try:
        measures_df = _CACHED_DATA['bonds-models'][0].get_measures(trade_date)
        columns = [dict(id=col, name=col) for col in measures_df.columns]
        for col in columns:
            if col['name'] == 'Yield':
                col.update(dict(type='numeric', format=dash_table.FormatTemplate.percentage(3)))
            elif col['name'].endswith('Price'):
                col.update(dict(type='numeric', format=Format.Format(precision=4, scheme=Format.Scheme.fixed)))
        patched_table = dash_table.DataTable(
            data=measures_df.to_dict('records'), columns=columns,
            page_size=50, editable=True, **_TABLE_KWARGS
        )
        return patched_table, None
    except Exception as ex:
        return patched_table, ex

if __name__ == '__main__':
    app.run()
