# import pandas as pd
# import plotly.express as px
import plotly.graph_objects as go

def get_curve_figure(fwd_curves: dict[str, dict[any, float]], node_points: dict[str, dict[any, float]]):
    # data_df = pd.DataFrame(fwd_curve.items(), columns=[date_col] + point_cols).set_index([date_col])
    # fig = px.line(data_df, title='Fwd Rates')
    fig = go.Figure()
    for k, fc in fwd_curves.items():
        fig.add_trace(go.Scatter(
            x=list(fc.keys()),
            y=list(fc.values()),
            name=f'{k} - Forward Rates',
            legendgroup='G1',
            ))
        fig.add_trace(go.Scatter(
            x=list(node_points[k].keys()),
            y=[fc[p] for p in node_points[k] if p in fc],
            name=f'{k} - Forward Rate Node',
            mode='markers',
            legendgroup='G1',
            showlegend=False
            ))
        fig.add_trace(go.Scatter(
            x=list(node_points[k].keys()),
            y=list(node_points[k].values()),
            name=f'{k} - Zero Rates',
            mode='lines',
            legendgroup='G1',
            hoverinfo='skip',
            ))
    fig.update_layout(
        title_text='Yield Curve',
        xaxis=dict(
            tickformat='%d-%b-%y'
        ),
        yaxis=dict(
            title='Rate %',
            tickformat=',.3%'
        ),
    )
    return fig

def display_curves(fwd_curves: dict[str, dict[any, float]], node_points: dict[str, dict[any, float]]) -> None:
    get_curve_figure(fwd_curves, node_points).show()
