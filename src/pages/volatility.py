import dash
from dash import html, dcc
from dash import callback, Output, Input

from volatility.lib import plotter as vol_plotter
from volatility.models.vol_types import VolatilityModelType
from pages import config
import main

dash.register_page(__name__)

layout = html.Div([
    dcc.Tabs(children=[
        dcc.Tab(children=html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown([vst.value for vst in VolatilityModelType], id='model-type-dropdown-1')
                ], style=config.DROPDOWN_STYLE),
                html.Button('Reload Option Surfaces', id='load_options'),
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
                html.Button('Reload Vol Surfaces', id='load_vols'),
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
    Input(component_id='model-type-dropdown-1', component_property='value'),
    Input(component_id='load_options', component_property='n_clicks'),
    prevent_initial_call=True,
)
def load_options(model_type: str, *_):
    try:
        v_tabvals = []
        for vsm in main.evaluate_option_surfaces():
            vs = vsm.build(model_type, beta=0)
            fig = vol_plotter.get_vol_surface_figure(*vsm.get_graph_info(vs))
            v_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=config.GRAPH_STYLE)
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
            fig = vol_plotter.get_vol_surface_figure(*vsm.get_graph_info(vs))
            v_tabvals.append(dcc.Tab(children=[
                dcc.Graph(figure=fig, style=config.GRAPH_STYLE)
            ], label=vsm.name))
        return dcc.Tabs(children=v_tabvals), None
    except Exception as ex:
        return None, ex
