import dash
from dash import Dash, html, dcc
from pages.config import DIV_STYLE


app = Dash(__name__, use_pages=True)
app.layout = html.Div([
    html.H3('Macro Analytics App', style=DIV_STYLE),
    html.Div(children=[
        dcc.Link(page['name'], href=page['relative_path'], style=DIV_STYLE)
        for page in dash.page_registry.values()
    ], style=DIV_STYLE),
    dash.page_container
])


if __name__ == '__main__':
    app.run()
