
from dash import Dash, html, dash_table, dcc
from dash import callback, Output, Input, Patch, State
import dash_ag_grid as dag
import datetime as dtm
import pandas as pd

from lib import plotter
from volatility.lib import plotter as vol_plotter
from volatility.models.vol_types import VolSurfaceType
from models.bond_curve_types import BondCurveWeightType
import main


_GRAPH_STYLE = {'height': '100vh'}
_TABLE_KWARGS = dict(sort_action='native', sort_mode='multi', sort_by=[],
                filter_action='native')
_DIV_STYLE = {'textAlign': 'center'}
_AGGRID_OPTIONS = {
    'pagination': True, 'paginationPageSize': 50, 'animateRows': False,
    'enableCellTextSelection': True,
}
_AGGRID_KWARGS = dict(
    defaultColDef = {'filter': True},
    columnSize='sizeToFit',
    dashGridOptions=_AGGRID_OPTIONS,
    style={'height': 900},
)
_FORM_STYLE = {'justifyContent': 'center', 'display': 'flex'}
def get_grid_format(fmt: str):
    return {'function': f"params.value == null ? '' :  d3.format('{fmt}')(params.value)"}

app = Dash(__name__)
app.layout = html.Div([
    html.H3('Macro Analytics App', style=_DIV_STYLE),
    html.Br(),
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
    ], style=_DIV_STYLE),
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
        ], style=_DIV_STYLE), label='Bond Futures'),
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([bcwt.value for bcwt in BondCurveWeightType], id='bonds-weight-dropdown')
                ], style={'width': '15%'}),
                html.Button('Reload Bonds Curves', id='load_bonds_curves'),
            ], style=_FORM_STYLE),
            dcc.Loading(
                id='bonds-curves-status',
                type='default',
            ),
            html.Div(id='bonds-curves'),
        ], style=_DIV_STYLE), label='Bonds'),
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolSurfaceType], id='vol-type-dropdown')
                ], style={'width': '15%'}),
                html.Button('Reload Vol Curves', id='load_vols'),
            ], style=_FORM_STYLE),
            dcc.Loading(
                id='vol-curves-status',
                type='default',
            ),
            html.Div(id='vol-curves'),
        ], style=_DIV_STYLE), label='Vols'),
    ]),
])

@callback(
    Output(component_id='val-date-picker', component_property='min_date_allowed'),
    Output(component_id='val-date-picker', component_property='max_date_allowed'),
    Input(component_id='val-date-picker', component_property='n_clicks'),
)
def refresh_date(*_):
    current_date = dtm.date.today()
    return current_date - dtm.timedelta(7), current_date


@callback(
    Output(component_id='rates-curves', component_property='children'),
    Output(component_id='rates-curves-status', component_property='children'),
    Input(component_id='val-date-picker', component_property='start_date'),
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
    Output(component_id='bonds-curves-status', component_property='children'),
    State(component_id='val-date-picker', component_property='end_date'),
    # Input(component_id='rates-curves', component_property='children'),
    Input(component_id='bonds-weight-dropdown', component_property='value'),
    Input(component_id='load_bonds_curves', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_bonds_curves(date_str: str, weight_type: str, *_):
    value_date = dtm.date.fromisoformat(date_str) if date_str else None
    b_tabvals = []
    try:
        for bcm in main.evaluate_bonds_curves(value_date, weight_type=weight_type):
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
                    id='bonds-pricer-status',
                    type='default',
                ),
                html.Div(id='bonds-pricer'),
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
            **_AGGRID_KWARGS
        )
        return patched_table, None
    except Exception as ex:
        return patched_table, ex

@callback(
    Output(component_id='bond-futures', component_property='children'),
    Output(component_id='bond-futures-status', component_property='children'),
    Input(component_id='val-date-picker', component_property='start_date'),
    Input(component_id='val-date-picker', component_property='end_date'),
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
            **_AGGRID_KWARGS
        )
        return table, None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='vol-curves', component_property='children'),
    Output(component_id='vol-curves-status', component_property='children'),
    Input(component_id='vol-type-dropdown', component_property='value'),
    Input(component_id='load_vols', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_vols(vol_type: str, *_):
    try:
        v_tabvals = []
        for vsm in main.evaluate_vol_curves():
            vs = vsm.build(vol_type)
            fig = vol_plotter.get_vol_surface_figure(*vsm.get_graph_info(vs))
            v_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=_GRAPH_STYLE)
            ], label=vsm.name))
        return dcc.Tabs(children=v_tabvals), None
    except Exception as ex:
        return None, ex


if __name__ == '__main__':
    app.run()
