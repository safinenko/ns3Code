import pandas as pd
import numpy as np
import re
from dash import Dash, dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go

from Scripts.streetNetwork import StreetNetwork


# Import street network, topology, UEs
streetNetwork = StreetNetwork()
UEroutes = pd.read_csv('outputs/UE_locations.csv', index_col = 'Time(s)')
radioTowers = pd.read_csv('outputs/tower_locations.csv')

# Import results from the simulation
UEmeasurements = pd.read_csv('outputs/rsrp_rsrq_trace.csv',
                             index_col = 'Time(s)',
                             dtype = {
                                'IMSI' : 'Int64',
                                'UE_NodeID' : 'Int64',
                                'UE_RNTI' : 'Int64',
                                'Status' : str,
                                'eNB_NodeID' : 'Int64',
                                'CellID' : 'Int64',
                                'RSRP' : float,
                                'RSRQ' : float
                             })

# Convert tower coordinates from Cartesian back to Lat/Lon for the map
tower_lon, tower_lat = streetNetwork.projectionMap(
    radioTowers['x'], radioTowers['y'], inverse = True
)
radioTowers['lat'] = tower_lat
radioTowers['lon'] = tower_lon

ue_lon, ue_lat = streetNetwork.projectionMap(
    UEroutes['x'], UEroutes['y'], inverse = True
)
UEroutes['lat'] = ue_lat
UEroutes['lon'] = ue_lon

# Parse logs
timeStampPattern = re.compile(r'^\+?(\d+\.\d+)s')
IMSIIDPattern = re.compile(r'IMSI\s+(\d+)')
RRCmessagePattern = re.compile(r'UeManager\s+(.*)')

logData = []

log_path = 'outputs/out.txt'
with open(log_path, 'r') as fileIn:
    for line in fileIn:
        if re.search(r' IMSI \d+ ', line):
            logData.append([
                float(timeStampPattern.match(line).group(1)),
                int(IMSIIDPattern.search(line).group(1)),
                RRCmessagePattern.search(line).group(1),
            ])

logs = pd.DataFrame(logData, columns = ['Time(s)', 'IMSI', 'Message'])
allMessageTypes = logs['Message'].unique()


# Time Slider
timeSlider = html.Div(
    className = 'slider-container',
    children = [
        html.Label('Simulation time', style = {'fontSize': '14px'}),
        dcc.Slider(
            id = 'time-slider',
            min = 0,
            max = UEroutes.index.max(),
            value = UEroutes.index[1],
            step = 10,
            marks = {i: f'{i//60} min' for i in range(int(UEroutes.index.min()),
                                                      int(UEroutes.index.max()) + 1, 300)}
    )],
    style = {'textAlign' : 'center', 'marginBottom' : '20px'}
)

checklist = dcc.Checklist(
    id = 'checkList',
    options = allMessageTypes,
    value = [q for q in allMessageTypes if 'HANDOVER' in q],
    className = 'checklist-container'
)


app = Dash(__name__, title = 'ns-3 visualizer', update_title = None)
app.layout = html.Div([
    html.H2('LTE handover simulation results',
            style = {'textAlign' : 'center', 'padding' : '0pt', 'fontSize' : '20px'}),
    html.Hr(),
    html.Div([
        html.Div([
            timeSlider,
            dcc.Interval(id = 'autoSlider', interval = 250, n_intervals = 0, disabled = True),
            html.Div([
                html.Div(html.Button('Autoplay', id = 'autoPlaySimulation',
                                     style = {'backgroundColor' : 'lightBlue'}),
                         style = {'position' : 'absolute', 'z-index' : '1002',
                                  'top' : '10px', 'left' : '10px'}),
                dcc.Graph(id = 'network-map-graph',
                          style = {'height' : '70vh'},
                          config = {'displayModeBar' : False})
                ], style = {'position' : 'relative'})
            ],
            style = {'width' : '45%', 'display' : 'inline-block', 'padding' : '10px',
                     'verticalAlign' : 'top'}),
        html.Div(
            id = 'right-column-content',
            style = {'width' : '50%', 'display' : 'inline-block',
                     'verticalAlign' : 'top', 'padding' : '16px'},
            children = [
                html.Div([
                    checklist,
                    html.Div(html.Button('Update shown RRC messages', id = 'RRCs-to-show',
                                         style = {'backgroundColor' : 'lightBlue'}),
                             style = {'textAlign' : 'center'}),
                ], className = 'slider-container'),
                dcc.Graph(id = 'signal-strength-graph',
                          config = {'displayModeBar' : False},
                          style = {'height' : '70vh'})
            ]
        )
    ]),
    dcc.Store(id = 'selected_ue', storage_type = 'memory'),
    dcc.Store(id = 'autoAnimate', storage_type = 'memory'),
    dcc.Store(id = 'listOfRRCs', storage_type = 'memory')
])



@app.callback(
    Output('autoAnimate', 'data'),
    Output('autoPlaySimulation', 'children'),
    Output('autoSlider', 'disabled'),
    Input('autoPlaySimulation', 'n_clicks'),
    State('autoAnimate', 'data'),)
def toggleAnimation(_, autoAnimate):
    if autoAnimate is None:
        return False, 'Autoplay Off', True
    else:
        if autoAnimate:
            return False, 'Autoplay Off', True
        else:
            return True, 'Autoplaying..', False


@app.callback(
    Output('network-map-graph', 'figure'),
    Output('time-slider', 'value'),
    Input('autoSlider', 'n_intervals'),
    Input('time-slider', 'value'),
    Input('selected_ue', 'data'),
    State('network-map-graph', 'figure'),
    State('autoAnimate', 'data'))
def update_map(autoSlide, selected_time, used_ID, mapData, autoAnimate):
    if callback_context.triggered_id == 'autoSlider':
        if autoAnimate:
            selected_time = min(UEroutes.index.max(), selected_time + 10)
            
        else:
            return no_update
    else:
        autoSlide = selected_time // 10

    return generateFigure(selected_time, used_ID, mapData)


def generateFigure(selected_time, used_ID, mapData):
    filtered_ue = UEroutes.loc[UEroutes.index == selected_time, ['lat', 'lon', 'UE_ID']]
    filtered_ue = filtered_ue.drop_duplicates()

    networkMap = go.Figure()

    closestMeasurements = UEmeasurements.iloc[
        np.where(abs(UEmeasurements.index - selected_time) == \
            (abs(UEmeasurements.index - selected_time)).min())[0]
    ]
    closestMeasurements = closestMeasurements[closestMeasurements['Status'] == 'Serving'].copy()

    ptsLon, ptsLat = [], []
    for UE_ID, subDF in filtered_ue.groupby('UE_ID'):
        closestMeasurements_UE = closestMeasurements[closestMeasurements['IMSI'] == UE_ID]
        for eNB_ID in closestMeasurements_UE['eNB_NodeID']:
            ptsLon.extend([radioTowers['lon'].loc[eNB_ID], subDF['lon'].iloc[0], None])
            ptsLat.extend([radioTowers['lat'].loc[eNB_ID], subDF['lat'].iloc[0], None])
    
    networkMap.add_trace(go.Scattermap(
        lat = ptsLat,
        lon = ptsLon,
        mode = 'lines',
        line = {'color' : 'blue', 'width' : 0.5},
        hoverinfo = 'none',
        name = 'Connection'
    ))

    networkMap.add_trace(go.Scattermap(
        lat = filtered_ue['lat'],
        lon = filtered_ue['lon'],
        mode = 'markers',
        marker = {'size' : 8, 'color' : 'magenta', 'symbol' : 'circle'},
        name = 'UE locations',
        customdata = filtered_ue['UE_ID'],
        hovertemplate = 'UE ID: %{customdata}<extra></extra>'
    ))

    networkMap.add_trace(go.Scattermap(
        lat = radioTowers['lat'],
        lon = radioTowers['lon'],
        mode = 'markers',
        marker = {'size' : 12, 'color' : 'blue', 'symbol' : 'triangle'},
        customdata = radioTowers.index,
        name = 'eNBs',
        hovertemplate = 'eNB ID: %{customdata}<extra></extra>'
    ))

    if used_ID is not None:
        networkMap.add_trace(go.Scattermap(
            lat = filtered_ue.loc[filtered_ue['UE_ID'] == used_ID, 'lat'],
            lon = filtered_ue.loc[filtered_ue['UE_ID'] == used_ID, 'lon'],
            mode = 'markers',
            marker = {'size' : 14, 'color' : 'red', 'symbol' : 'circle'},
            name = 'Selected UE',
            customdata = [f'{used_ID}']
        ))

    if mapData is not None:
        # for i in mapData['data']:
        #     print(i)
        mapCenter = mapData['layout']['map']
    else:
        mapCenter = {
            'style' : 'open-street-map',
            'center' : {'lon' : radioTowers['lon'].mean(),
                        'lat' : radioTowers['lat'].mean()},
            'zoom' : 11
        }

    networkMap.update_layout(
        margin = {'r' : 0, 't' : 0, 'l' : 0, 'b' : 0},
        map = mapCenter,
        legend = {'yanchor' : 'bottom', 'y' : 0.01,
                  'xanchor' : 'right', 'x' : 0.99}
    )

    return networkMap, selected_time


@app.callback(
    Output('signal-strength-graph', 'figure'),
    Output('selected_ue', 'data'),
    Output('listOfRRCs', 'data'),
    Input('network-map-graph', 'clickData'),
    Input('selected_ue', 'data'),
    State('checkList', 'value'),
    Input('RRCs-to-show', 'n_clicks'))
def update_signal_graph(clickData, used_ID, listOfRRCs, _):
    fig = go.Figure()

    if clickData is None:
        fig.update_layout(
            xaxis = {'visible' : False},
            yaxis = {'visible' : False},
            annotations = [{
                'text' : 'Click a UE on the map to see its signal strength',
                'xref' : 'paper',
                'yref' : 'paper',
                'showarrow' : False,
                'font' : {'size': 16}
            }]
        )
        return fig, used_ID, listOfRRCs

    if clickData['points'][0]['curveNumber'] == 1:
        UE_ID = clickData['points'][0]['pointNumber'] + 1

        servingCellMeasurements = UEmeasurements[(UEmeasurements['IMSI'] == UE_ID) &
                                                 (UEmeasurements['Status'] == 'Serving')]

        allServing = UEmeasurements[
            (UEmeasurements['IMSI'] == UE_ID) &
            UEmeasurements['eNB_NodeID'].isin(servingCellMeasurements['eNB_NodeID'].unique())]
        for eNB_ID, subDF in allServing.groupby('eNB_NodeID'):
            subDF2 = subDF.reset_index() \
                          .sort_values(['Time(s)', 'RSRP']) \
                          .groupby('Time(s)').tail(1)
            fig.add_trace(go.Scatter(
                x = subDF2['Time(s)'] / 60,
                y = subDF2['RSRP'],
                name = f'eNB {eNB_ID} RSRP (dBm)',
                line = {'color' : 'blue', 'width' : 1}))

        servingCellMeasurements2 = servingCellMeasurements.reset_index() \
                                                          .sort_values(['Time(s)', 'RSRP']) \
                                                          .groupby('Time(s)').tail(1)

        fig.add_trace(go.Scatter(
            x = servingCellMeasurements2['Time(s)'] / 60,
            y = servingCellMeasurements2['RSRQ'],
            name = 'Serving RSRQ (dB)', yaxis = 'y2', visible = 'legendonly'))

        # Add RSRP and RSRQ traces with two different y-axes
        fig.add_trace(go.Scatter(
            x = servingCellMeasurements2['Time(s)'] / 60,
            y = servingCellMeasurements2['RSRP'],
            name = 'Serving RSRP (dBm)',
            line = {'color' : 'red', 'width' : 3}))

        # Update layout for two y-axes
        bounds = [allServing['RSRP'].min() - 2, allServing['RSRP'].max() + 2]
        fig.update_layout(
            title_text = f'Signal Strength for UE {UE_ID}',
            xaxis_title = 'Time (m)',
            yaxis = {'title' : 'RSRP (dBm)', 'range' : bounds},
            yaxis2 = {'title' : 'RSRQ (dB)', 'overlaying' : 'y', 'side' : 'right'},
            legend = {
                'orientation' : 'h',
                'yanchor' : 'bottom',
                'y' : -0.3,
                'xanchor' : 'left',
                'x' : 0
            }
        )

        for RRCmessage in listOfRRCs:
            tStamps = logs.loc[(logs['IMSI'] == UE_ID) & (logs['Message'] == RRCmessage),
                               'Time(s)']
            if len(tStamps) > 0:
                xs = []
                ys = []
                for tStamp in tStamps:
                    xs.extend([tStamp / 60, tStamp / 60, None])
                    ys.extend([*bounds, None])
                
                fig.add_trace(go.Scatter(
                    x = xs, y = ys,
                    name = RRCmessage,
                    line = {'color' : 'black', 'width' : 0.5, 'dash' : 'dash'}
                ))

        return fig, UE_ID, listOfRRCs
    else:
        return no_update, used_ID, listOfRRCs


if __name__ == '__main__':
    app.run(debug = True)
