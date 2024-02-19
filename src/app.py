
from dash import Dash, html, dash_table, dcc
from dash import callback, Output, Input
from lib import plotter
from main import evaluate

app = Dash(__name__)

app.layout = html.Div([
    html.H3('My First App with Data, Graph'),
    html.Br(),
    html.Button('Load Curves', id='load_main'),
    html.Div(id='curve-plot'),
])

@callback(
    Output(component_id='curve-plot', component_property='children'),
    Input(component_id='load_main', component_property='n_clicks'),
    # background=True,
    # running=[
    #     (Output("refresh", "disabled"), True, False),
    # ],
)
def load_main(*_):
    tabvals = []
    for ycs in evaluate():
        table = ycs.get_calibration_summary()
        fig = plotter.get_rate_curve_figure(*ycs.get_graph_info())
        tabvals.append(dcc.Tab([
            html.Button('Refresh Curve', id='refresh'),
            dcc.Graph(figure=fig),
            dash_table.DataTable(data=table.to_dict('records'), page_size=20)
        ], label=ycs.name))
    return dcc.Tabs(children=tabvals)


if __name__ == '__main__':
    app.run()
