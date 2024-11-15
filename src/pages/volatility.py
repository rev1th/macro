import dash
from dash import html, dcc, callback, Output, Input
import dash_ag_grid as dag
import datetime as dtm
import logging

from common.app import style
from volatility.lib import plotter as vol_plotter
from volatility.models.vol_types import VolatilityModelType
import main

logger = logging.Logger(__name__)
dash.register_page(__name__)

DIV_STYLE = style.get_div_style()
DROPDOWN_STYLE = style.get_dropdown_style()
FORM_STYLE = style.get_form_style()
GRAPH_STYLE = style.get_graph_style()
GRID_STYLE = style.get_grid_style()

layout = html.Div([
    dcc.Tabs(children=[
        dcc.Tab(children=html.Div([
            html.Div([
                dcc.DatePickerSingle(id='val-date-picker'),
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolatilityModelType], id='model-type-dropdown-1')
                ], style=DROPDOWN_STYLE),
                html.Button('Load Option Surfaces', id='load_options'),
            ], style=FORM_STYLE),
            dcc.Loading(
                id='option-surfaces-status',
                type='default',
            ),
            html.Div(id='option-surfaces'),
        ], style=DIV_STYLE), label='Listed Options'),
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolatilityModelType], id='model-type-dropdown-2')
                ], style=DROPDOWN_STYLE),
                html.Button('Load Vol Surfaces', id='load_vols'),
            ], style=FORM_STYLE),
            dcc.Loading(
                id='vol-surfaces-status',
                type='default',
            ),
            html.Div(id='vol-surfaces'),
        ], style=DIV_STYLE), label='FX'),
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
        tabvals = []
        for vsm in main.evaluate_option_surfaces(val_date):
            try:
                vs = vsm.build(model_type)
                vs_fig = vol_plotter.get_surface_figure(*vsm.get_vols_graph(vs))
                gr_fig = vol_plotter.get_surface_figure(*vsm.get_greeks_graph(vs), title='Greeks', mesh_ids=[])
                rows, colnames = vsm.get_calibration_summary(vs)
            except Exception as ex:
                print(f'Exception: {ex}')
                continue
            columns = [dict(field=col) for col in colnames]
            records = [dict(zip(colnames, row)) for row in rows]
            tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=vs_fig, style=GRAPH_STYLE),
                dcc.Graph(figure=gr_fig, style=GRAPH_STYLE),
                dag.AgGrid(
                    rowData=records, columnDefs=columns,
                    **GRID_STYLE
                ),
            ], label=vsm.name))
        return dcc.Tabs(children=tabvals), None
    except Exception as ex:
        logger.critical(f'Option surfaces loading failed: {ex}')
        return None, None

@callback(
    Output(component_id='vol-surfaces', component_property='children'),
    Output(component_id='vol-surfaces-status', component_property='children'),
    Input(component_id='model-type-dropdown-2', component_property='value'),
    Input(component_id='load_vols', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_vols(model_type: str, *_):
    try:
        tabvals = []
        for vsm in main.evaluate_vol_surfaces():
            vs = vsm.build(model_type)
            fig = vol_plotter.get_surface_figure(*vsm.get_vols_graph(vs))
            rows, colnames = vsm.get_calibration_summary(vs)
            columns = [dict(field=col) for col in colnames]
            for col in columns:
                if col['field'] in ('Delta', 'Quote', 'Error'):
                    col.update(dict(valueFormatter=style.get_grid_number_format(',.3%')))
            records = [dict(zip(colnames, row)) for row in rows]
            tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=GRAPH_STYLE),
                dag.AgGrid(
                    rowData=records, columnDefs=columns,
                    **GRID_STYLE
                ),
            ], label=vsm.name))
        return dcc.Tabs(children=tabvals), None
    except Exception as ex:
        logger.critical(f'FX vol surfaces loading failed: {ex}')
        return None, None
