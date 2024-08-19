import dash
from dash import html, dcc
from dash import callback, Output, Input

from volatility.lib import plotter as vol_plotter
from volatility.models.vol_types import VolSurfaceType
from pages import config
import main

dash.register_page(__name__)

layout = html.Div([
    dcc.Tab(children=html.Div([
        html.Div([
            html.Div([
                dcc.Dropdown([vst.value for vst in VolSurfaceType], id='vol-type-dropdown')
            ], style=config.DROPDOWN_STYLE),
            html.Button('Reload Vol Curves', id='load_vols'),
        ], style=config.FORM_STYLE),
        dcc.Loading(
            id='vol-curves-status',
            type='default',
        ),
        html.Div(id='vol-curves'),
    ], style=config.DIV_STYLE), label='Vols'),
])

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
                dcc.Graph(figure=fig, style=config.GRAPH_STYLE)
            ], label=vsm.name))
        return dcc.Tabs(children=v_tabvals), None
    except Exception as ex:
        return None, ex
