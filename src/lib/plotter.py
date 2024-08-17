import pandas as pd
# import plotly.express as px
from common import plotter

RATE_FORMAT = ',.3%'
RATE_NAME_1 = 'Forward Rate (%)'
RATE_NAME_2 = 'Zero Rate (%)'
DATE_FORMAT = '%d-%b-%y'

def get_rates_curve_figure(fwd_curves: dict[str, dict[any, float]], zero_curves_nodes: dict[str, dict[any, float]]):
    fig = plotter.get_figure(fwd_curves, zero_curves_nodes, title='Yield Curve', mode2='lines',
                             x_name='Date', x_format=DATE_FORMAT,
                             y_name=RATE_NAME_1, y_format=RATE_FORMAT,
                             y2_name=RATE_NAME_2, y2_format=RATE_FORMAT)
    # fwd_curves_nodes = {}
    # for k, vc in zero_curves_nodes.items():
    #     fwd_points_i = {}
    #     for dt in vc.index:
    #         if dt in fwd_curves[k]:
    #             fwd_points_i[dt] = fwd_curves[k][dt]
    #     fwd_curves_nodes[k] = pd.Series(fwd_points_i)
    # plotter.add_traces(fig, fwd_curves_nodes, group=RATE_NAME_1, mode='markers', showlegend=False)
    return fig
    # data_df = pd.DataFrame(fwd_curve.items(), columns=[date_col] + point_cols).set_index([date_col])
    # fig = px.line(data_df, title='Fwd Rates')

def display_rates_curve(fwd_curves: dict[str, dict[any, float]], node_points: dict[str, dict[any, float]]) -> None:
    get_rates_curve_figure(fwd_curves, node_points).show()

def get_bonds_curve_figure(bond_data: dict[str, pd.DataFrame], bond_data2: pd.DataFrame = None):
    x_name = 'Maturity'
    y_name = 'Yield'
    t_name = 'Name'
    return plotter.get_figure(
        bond_data, data2=bond_data2, title='Bond Curve', text_col=t_name, mode=['lines', 'markers'],
        x_name=x_name, x_format='%d-%b-%y',
        y_name=y_name, y_format=',.4%',
        y2_name=y_name, y2_format=',.4%')

def display_bonds_curve(*args, **kwargs) -> None:
    get_bonds_curve_figure(*args, **kwargs).show()
