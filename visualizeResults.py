import pandas as pd
import numpy as np
from pathlib import Path
from dash import Dash, dcc, html, Input, Output, State, no_update, callback_context, Patch
import plotly.graph_objects as go

from Scripts.visualizationHelp import importLogData

learning_episode = 0
learning_episode_runID = 0
updateInterval = 250 # time between updates for the autoplay button [ms]

# Import topology and UEs
UEroutes = pd.read_csv('inputData/UE_locations.csv', index_col = 'Time(s)')
radioTowers = pd.read_csv('inputData/networkTopo.csv')

# Import RSRP values from the simulation
outputDataPath = Path(f'outputs/ep_{learning_episode}/run_{learning_episode_runID}/')
assert outputDataPath.is_dir()

UEmeasurements = pd.read_csv(
    outputDataPath / 'rsrp_rsrq_trace.csv',
    index_col = 'Time(s)',
    usecols = ['Time(s)', 'UE_ID', 'Status', 'eNB_ID', 'RSRP', 'RSRQ'],
    dtype = {
        'UE_ID' : 'Int64',
        'Status' : str,
        'eNB_ID' : 'Int64',
        'RSRP' : float,
        'RSRQ' : float
    }
)

# Import and parse logs
logs, HOdata = importLogData(outputDataPath, UEmeasurements)
allMessageTypes = [msg for msg in logs['RecognizedMessage'].unique() if msg]


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
    value = list(set(['Handover', 'Initial Connection']) & set(allMessageTypes)),
    className = 'checklist-container'
)

autoPlayButton = html.Div(
    html.Button('Autoplay',
                id = 'autoPlaySimulation',
                style = {'backgroundColor' : 'lightBlue'}),
    style = {'position' : 'absolute', 'z-index' : '1002',
             'top' : '10px', 'left' : '10px'})


app = Dash(__name__, title = 'ns-3 visualizer', update_title = None)

###################################################################################################

def plotDataSlice(HO_ID):
    hoGraph = go.Figure()

    dataSlice, HOtime = HOdata[HO_ID]
    eNB_Before = dataSlice[(dataSlice.index < HOtime - 1) &
                           (dataSlice['Status'] == 'Serving')]['eNB_ID'].unique()[0]
    eNB_After = dataSlice[(dataSlice.index > HOtime + 1) &
                          (dataSlice['Status'] == 'Serving')]['eNB_ID'].unique()[0]

    beforeHO = dataSlice[dataSlice['eNB_ID'] == eNB_Before]
    hoGraph.add_trace(go.Scatter(
        x = beforeHO.index / 60,
        y = beforeHO['RSRP'],
        name = f'Source eNB RSRP [eNB ID: {eNB_Before}] (dBm)',
        line = {'color' : 'blue', 'width' : 1}))

    afterHO = dataSlice[dataSlice['eNB_ID'] == eNB_After]
    hoGraph.add_trace(go.Scatter(
        x = afterHO.index / 60,
        y = afterHO['RSRP'],
        name = f'Target eNB RSRP [eNB ID: {eNB_After}] (dBm)',
        line = {'color' : 'red', 'width' : 1}))

    intersection = beforeHO.index[np.where(beforeHO['RSRP'] < afterHO['RSRP'])[0][0]]

    hoGraph.update_layout(
        title_text = f'Difference : {HOtime - intersection:g} seconds',
        xaxis_title = 'Time (m)',
        yaxis = {'title' : 'RSRP (dBm)'},
        legend = {
            'orientation' : 'h',
            'yanchor' : 'bottom',
            'y' : -0.3,
            'xanchor' : 'left',
            'x' : 0
        }
    )

    bounds = [dataSlice['RSRP'].min() - 1, dataSlice['RSRP'].max() + 1]
    hoGraph.add_trace(go.Scatter(
        x = [HOtime / 60, HOtime / 60],
        y = bounds,
        name = 'HO time',
        line = {'color' : 'black', 'width' : 0.5, 'dash' : 'dash'}))


    hoGraph.add_trace(go.Scatter(
        x = [intersection / 60, intersection / 60],
        y = bounds,
        name = 'HO time',
        line = {'color' : 'black', 'width' : 0.5, 'dash' : 'dash'}))

    return hoGraph


@app.callback(
    Output('HOstat', 'figure'),
    Input('HOselect', 'value'))
def updateHOgraph(x):
    return plotDataSlice(int(x))


###################################################################################################

def generateFigure(selected_time, used_ID):
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
        closestMeasurements_UE = closestMeasurements[closestMeasurements['UE_ID'] == UE_ID]
        for eNB_ID in closestMeasurements_UE['eNB_ID']:
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

    eNBmarkerSettings = {'size' : 12, 'color' : 'black', 'symbol' : 'star'}

    networkMap.add_trace(go.Scattermap(
        lat = radioTowers['lat'],
        lon = radioTowers['lon'],
        mode = 'markers',
        marker = eNBmarkerSettings,
        customdata = radioTowers.index,
        legendgroup = 'eNBsG',
        hovertemplate = 'eNB ID: %{customdata}<extra></extra>',
        showlegend = False
    ))
    networkMap.add_trace(go.Scatter(
        x = [None],
        y = [None],
        mode = 'markers',
        marker = eNBmarkerSettings,
        legendgroup = 'eNBsG',
        name = 'eNBs'
        ))

    networkMap.add_trace(go.Scattermap(
        lat = [None],
        lon = [None],
        mode = 'markers',
        marker = {'size' : 14, 'color' : 'red', 'symbol' : 'circle'},
        name = 'Selected UE',
        showlegend = False,
    ))

    mapCenter = {
        'style' : 'open-street-map',
        'center' : {'lon' : radioTowers['lon'].mean(),
                    'lat' : radioTowers['lat'].mean()},
        'zoom' : 11
    }

    networkMap.update_layout(
        margin = {'r' : 0, 't' : 0, 'l' : 0, 'b' : 0},
        map = mapCenter,
        legend_tracegroupgap = 0,
        legend = {'yanchor' : 'bottom', 'y' : 0.01,
                  'xanchor' : 'right', 'x' : 0.99}
    )

    return networkMap, selected_time


def updateFigure(selected_time, used_ID):
    filtered_ue = UEroutes.loc[UEroutes.index == selected_time, ['lat', 'lon', 'UE_ID']]
    filtered_ue = filtered_ue.drop_duplicates()

    closestMeasurements = UEmeasurements.iloc[
        np.where(abs(UEmeasurements.index - selected_time) == \
            (abs(UEmeasurements.index - selected_time)).min())[0]
    ]
    closestMeasurements = closestMeasurements[closestMeasurements['Status'] == 'Serving'].copy()

    ptsLon, ptsLat = [], []
    for UE_ID, subDF in filtered_ue.groupby('UE_ID'):
        closestMeasurements_UE = closestMeasurements[closestMeasurements['UE_ID'] == UE_ID]
        for eNB_ID in closestMeasurements_UE['eNB_ID']:
            ptsLon.extend([radioTowers['lon'].loc[eNB_ID], subDF['lon'].iloc[0], None])
            ptsLat.extend([radioTowers['lat'].loc[eNB_ID], subDF['lat'].iloc[0], None])

    patch_figure = Patch()
    patch_figure['data'][0]['lon'] = ptsLon
    patch_figure['data'][0]['lat'] = ptsLat

    patch_figure['data'][1]['lon'] = filtered_ue['lon']
    patch_figure['data'][1]['lat'] = filtered_ue['lat']

    if used_ID is not None:
        patch_figure['data'][4]['lon'] = filtered_ue.loc[filtered_ue['UE_ID'] == used_ID, 'lon']
        patch_figure['data'][4]['lat'] = filtered_ue.loc[filtered_ue['UE_ID'] == used_ID, 'lat']
        patch_figure['data'][4]['customdata'] = [f'{used_ID}']
        patch_figure['data'][4]['showlegend'] = True

    return patch_figure, selected_time


@app.callback(
    Output('network-map-graph', 'figure'),
    Output('time-slider', 'value'),
    Output('autoAnimate', 'data'),
    Output('autoPlaySimulation', 'children'),
    Output('autoSlider', 'disabled'),
    Output('signal-strength-graph', 'figure', allow_duplicate = True),
    Input('autoPlaySimulation', 'n_clicks'),
    Input('autoSlider', 'n_intervals'),
    Input('time-slider', 'value'),
    Input('selected_ue', 'data'),
    State('autoAnimate', 'data'),
    State('checkList', 'value'),
    Input('network-map-graph', 'clickData'),
    prevent_initial_call = True)
def update_map(_, autoSlide, selected_time, used_ID, autoAnimate, listOfRRCs, clickData):
    if autoAnimate is None:
        autoAnimate = False
    if callback_context.triggered_id == 'autoPlaySimulation':
        if autoAnimate:
            returnVars = False, 'Autoplay Off', True
        else:
            # Check if we reached the last record
            selected_time = min(UEroutes.index.max(), selected_time)
            if selected_time == UEroutes.index.max():
                returnVars = False, 'Autoplay Off', True
            returnVars = True, 'Autoplaying..', False

        return no_update, selected_time, *returnVars, updateGraph(clickData, used_ID, selected_time, listOfRRCs, 'a')[0]


    if callback_context.triggered_id == 'autoSlider':
        if autoAnimate:
            selected_time = min(UEroutes.index.max(), selected_time + 10)
            if selected_time == UEroutes.index.max():
                autoAnimate = False
            
            if clickData is not None and clickData['points'][0]['curveNumber'] == 1:
                UE_ID = clickData['points'][0]['pointNumber']
                patchIndex = UEmeasurements.loc[UEmeasurements['UE_ID'] == UE_ID, 'eNB_ID'].nunique() + 2

                for RRCmessage in listOfRRCs:
                    tStamps = logs.loc[(logs['UE_ID'] == UE_ID) & (logs['RecognizedMessage'] == RRCmessage),
                                    'Time(s)']
                    if len(tStamps) > 0:
                        patchIndex += 1

                patch_figure = Patch()
                patch_figure['data'][patchIndex]['x'] = [selected_time / 60, selected_time / 60]
                patch_figure['data'][patchIndex + 1]['x'] = [selected_time / 60, selected_time / 60]

                return *updateFigure(selected_time, used_ID), \
                    autoAnimate, 'Autoplaying..' if autoAnimate else 'Autoplay Off', not autoAnimate, \
                    patch_figure

        else:
            return no_update
    else:
        autoSlide = selected_time // 10

    return *updateFigure(selected_time, used_ID), \
           autoAnimate, 'Autoplaying..' if autoAnimate else 'Autoplay Off', not autoAnimate, \
           updateGraph(clickData, used_ID, selected_time, listOfRRCs, 'a')[0]


###################################################################################################

def updateGraph(clickData, used_ID, selected_time, listOfRRCs, _):
    if clickData is None:
        fig = go.Figure()
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
        return fig, None

    if clickData['points'][0]['curveNumber'] == 1:
        UE_ID = clickData['points'][0]['pointNumber']
        servingCellMeasurements = UEmeasurements[(UEmeasurements['UE_ID'] == UE_ID) &
                                                 (UEmeasurements['Status'] == 'Serving')]

        fig = go.Figure()

        for eNB_ID, subDF in UEmeasurements[UEmeasurements['UE_ID'] == UE_ID].groupby('eNB_ID'):
            subDF2 = subDF.reset_index() \
                          .sort_values(['Time(s)', 'RSRP']) \
                          .groupby('Time(s)').tail(1)
            if eNB_ID in servingCellMeasurements['eNB_ID'].unique():
                fig.add_trace(go.Scatter(
                    x = subDF2['Time(s)'] / 60,
                    y = subDF2['RSRP'],
                    name = f'eNB {eNB_ID} RSRP (dBm)',
                    line = {'color' : 'blue', 'width' : 1})
                )
            else:
                fig.add_trace(go.Scatter(
                    x = subDF2['Time(s)'] / 60,
                    y = subDF2['RSRP'],
                    name = f'eNB {eNB_ID} RSRP (dBm)',
                    visible = 'legendonly',
                    line = {'color' : 'orange', 'width' : 0.5})
                )


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
        allServing = UEmeasurements[
            (UEmeasurements['UE_ID'] == UE_ID) &
            UEmeasurements['eNB_ID'].isin(servingCellMeasurements['eNB_ID'].unique())]
        bounds = [allServing['RSRP'].min() - 2, allServing['RSRP'].max() + 2]
        fig.update_layout(
            title_text = f'Signal Strength for UE {UE_ID}',
            xaxis_title = 'Time (m)',
            yaxis = {'title' : 'RSRP (dBm)', 'range' : bounds},
            xaxis = {'range' : [0, UEroutes.index.max() / 60]},
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
            tStamps = logs.loc[(logs['UE_ID'] == UE_ID) & (logs['RecognizedMessage'] == RRCmessage),
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

        fig.add_trace(go.Scatter(
            x = [selected_time / 60, selected_time / 60],
            y = bounds,
            showlegend = False,
            line = {'color' : 'green', 'width' : 0.5, 'dash' : 'dot'}
        ))
        fig.add_annotation(text = 'Simulation time',
                           xref = 'paper', yref = 'paper',
                           x = selected_time / UEroutes.index.max(), y = 1, 
                           showarrow = False,
                           xanchor = 'center', yanchor = 'bottom',
                           font = {'size' : 10})

        return fig, UE_ID
    else:
        return no_update, used_ID


@app.callback(
    Output('signal-strength-graph', 'figure', allow_duplicate = True),
    Output('selected_ue', 'data'),
    Input('network-map-graph', 'clickData'),
    Input('selected_ue', 'data'),
    State('time-slider', 'value'),
    State('checkList', 'value'),
    Input('RRCs-to-show', 'n_clicks'),
    prevent_initial_call = True)
def update_signal_graph(*args):
    return updateGraph(*args)

###################################################################################################


app.layout = html.Div([
    html.H2('LTE handover simulation results',
            style = {'textAlign' : 'center', 'padding' : '0pt', 'fontSize' : '20px'}),
    html.Hr(),
    html.Div([
        html.Div([
            timeSlider,
            dcc.Interval(id = 'autoSlider', interval = updateInterval,
                         n_intervals = 0, disabled = True),
            html.Div([
                autoPlayButton,
                dcc.Graph(id = 'network-map-graph',
                          style = {'height' : '70vh'},
                          config = {'displayModeBar' : False},
                          figure = generateFigure(UEroutes.index[1], None)[0])
            ], style = {'position' : 'relative'})
        ],

        style = {'width' : '45%', 'display' : 'inline-block', 'padding' : '5px',
                 'verticalAlign' : 'top'}),
        html.Div([
            html.Div([
                checklist,
                html.Div(
                    html.Button('Update shown RRC messages', id = 'RRCs-to-show',
                                style = {'backgroundColor' : 'lightBlue'}),
                    style = {'textAlign' : 'center'}),
                ],
                className = 'slider-container'),

                dcc.Tabs([
                    dcc.Tab(label = 'RSRP/RSRQ', children = [
                        dcc.Graph(id = 'signal-strength-graph',
                                  config = {'displayModeBar' : False},
                                  style = {'height' : '60vh'})
                    ]),
                    dcc.Tab(label = 'HO Stats', children = [
                        dcc.Dropdown([f'{i}' for i in range(len(HOdata))], '0', id = 'HOselect'),
                        dcc.Graph(id = 'HOstat',
                                  config = {'displayModeBar' : False},
                                  style = {'height' : '60vh'},
                                  figure = plotDataSlice(0) if len(HOdata) > 0 else None)
                    ]),
                ])
            ],             
            style = {'width' : '50%', 'display' : 'inline-block',
                     'verticalAlign' : 'top', 'padding' : '5px'}
        )
    ]),
    dcc.Store(id = 'selected_ue', storage_type = 'memory'),
    dcc.Store(id = 'autoAnimate', storage_type = 'memory'),
    dcc.Store(id = 'listOfRRCs', storage_type = 'memory')
])


server = app.server

if __name__ == '__main__':
    app.run(debug = False)
