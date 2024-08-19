
GRAPH_STYLE = {'height': '100vh'}
# _TABLE_KWARGS = dict(sort_action='native', sort_mode='multi', sort_by=[],
#                 filter_action='native')
DIV_STYLE = {'textAlign': 'center', 'padding-left':'1em'}
_AGGRID_OPTIONS = {
    'pagination': True, 'paginationPageSize': 50, 'animateRows': False,
    'enableCellTextSelection': True,
}
AGGRID_KWARGS = dict(
    defaultColDef = {'filter': True},
    columnSize='sizeToFit',
    dashGridOptions=_AGGRID_OPTIONS,
    style={'height': 900},
)
FORM_STYLE = {'justifyContent': 'center', 'display': 'flex'}
DROPDOWN_STYLE = {'width': '15%'}

def get_grid_format(fmt: str):
    return {'function': f"params.value == null ? '' :  d3.format('{fmt}')(params.value)"}
