import dash
from dash import html, dcc, callback, Output, Input, State
import datetime as dtm
import pandas as pd

from common.app import plotter, style
from data_api import nyfed_client
from lib.plotter import DATE_FORMAT

dash.register_page(__name__)

layout = html.Div([
    dcc.Tab(children=html.Div([
        dcc.DatePickerSingle(id='from-date-picker'),
        html.Button('Reload Fixings', id='load-fixings'),
        dcc.Loading(
            id='load-fixings-status',
            type='default',
        ),
        html.Button('Update Fixings', id='update-fixings'),
        dcc.Loading(
            id='update-fixings-status',
            type='default',
        ),
        html.Div(id='fixings-curve'),
    ], style=style.get_div_style()), label='Fixings'),
])

@callback(
    Output(component_id='update-fixings-status', component_property='children'),
    Input(component_id='update-fixings', component_property='n_clicks'),
    prevent_initial_call=True,
)
def update_fixings(*_):
    nyfed_client.update()
    return None

@callback(
    Output(component_id='fixings-curve', component_property='children'),
    Output(component_id='load-fixings-status', component_property='children'),
    State(component_id='from-date-picker', component_property='date'),
    Input(component_id='load-fixings', component_property='n_clicks'),
)
def load_fixings(from_date_str: str, *_):
    from_date = dtm.date.fromisoformat(from_date_str) if from_date_str else dtm.date(2024, 1, 1)
    fix_data = {k: pd.Series(dict(v)) for k, v in nyfed_client.get(from_date).items()}
    fig = plotter.get_figure(fix_data, title='Rates', x_name='Date', x_format=DATE_FORMAT, y_name='Rate (%)')
    return [dcc.Graph(figure=fig, style=style.get_graph_style())], None
