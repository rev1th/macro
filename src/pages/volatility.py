import dash
from dash import html, dcc
from dash import callback, Output, Input
import dash_ag_grid as dag
import datetime as dtm

from volatility.lib import plotter as vol_plotter
from volatility.models.vol_types import VolatilityModelType
from pages import config
import main

dash.register_page(__name__)

layout = html.Div([
    dcc.Tabs(children=[
        dcc.Tab(children=html.Div([
            html.Div([
                dcc.DatePickerSingle(id='val-date-picker'),
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolatilityModelType], id='model-type-dropdown-1')
                ], style=config.DROPDOWN_STYLE),
                html.Button('Load Option Surfaces', id='load_options'),
            ], style=config.FORM_STYLE),
            dcc.Loading(
                id='option-surfaces-status',
                type='default',
            ),
            html.Div(id='option-surfaces'),
        ], style=config.DIV_STYLE), label='Listed Options'),
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolatilityModelType], id='model-type-dropdown-2')
                ], style=config.DROPDOWN_STYLE),
                html.Button('Load Vol Surfaces', id='load_vols'),
            ], style=config.FORM_STYLE),
            dcc.Loading(
                id='vol-surfaces-status',
                type='default',
            ),
            html.Div(id='vol-surfaces'),
        ], style=config.DIV_STYLE), label='FX'),
    ]),
])

@callback(
    Output(component_id='option-surfaces', component_property='children'),
    Output(component_id='option-surfaces-status', component_property='children'),
    Input(component_id='val-date-picker', component_property='date'),
    Input(component_id='model-type-dropdown-1', component_property='value'),
    Input(component_id='load_options', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_options(val_date_str: str, model_type: str, *_):
    try:
        val_date = dtm.date.fromisoformat(val_date_str) if val_date_str else None
        v_tabvals = []
        for vsm in main.evaluate_option_surfaces(val_date):
            vs = vsm.build(model_type, beta=0)
            fig = vol_plotter.get_vol_surface_figure(*vsm.get_vols_graph(vs))
            rows, colnames = vsm.get_calibration_summary(vs)
            columns = [dict(field=col) for col in colnames]
            records = [dict(zip(colnames, row)) for row in rows]
            v_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=config.GRAPH_STYLE),
                dag.AgGrid(
                    rowData=records, columnDefs=columns,
                    **config.AGGRID_KWARGS
                ),
            ], label=vsm.name))
        return dcc.Tabs(children=v_tabvals), None
    except Exception as ex:
        return None, ex

@callback(
    Output(component_id='vol-surfaces', component_property='children'),
    Output(component_id='vol-surfaces-status', component_property='children'),
    Input(component_id='model-type-dropdown-2', component_property='value'),
    Input(component_id='load_vols', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_vols(model_type: str, *_):
    try:
        v_tabvals = []
        for vsm in main.evaluate_vol_surfaces():
            vs = vsm.build(model_type)
            fig = vol_plotter.get_vol_surface_figure(*vsm.get_vols_graph(vs))
            rows, colnames = vsm.get_calibration_summary(vs)
            columns = [dict(field=col) for col in colnames]
            for col in columns:
                if col['field'] in ('Quote', 'Error'):
                    col.update(dict(valueFormatter=config.get_grid_format(',.3%')))
            records = [dict(zip(colnames, row)) for row in rows]
            v_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=config.GRAPH_STYLE),
                dag.AgGrid(
                    rowData=records, columnDefs=columns,
                    **config.AGGRID_KWARGS
                ),
            ], label=vsm.name))
        return dcc.Tabs(children=v_tabvals), None
    except Exception as ex:
        return None, ex
