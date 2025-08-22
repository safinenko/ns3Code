import re
import pandas as pd

# Parse logs
timeStampPattern = re.compile(r'^\+?(\d+\.\d+)s')
IMSIIDPattern = re.compile(r'IMSI\s+(\d+)')
RRCmessagePattern = re.compile(r'UeManager\s+(.*)')

def importLogData(outputDataPath, UEmeasurements):
    logData = []

    with open(outputDataPath / 'out.txt', 'r') as fileIn:
        for line in fileIn:
            if re.search(r' IMSI \d+ ', line):
                logData.append([
                    float(timeStampPattern.match(line).group(1)),
                    int(IMSIIDPattern.search(line).group(1)) - 1,
                    RRCmessagePattern.search(line).group(1),
                ])

    logs = pd.DataFrame(logData, columns = ['Time(s)', 'UE_ID', 'Message'])

    messageSequences = {
        ('CONNECTED_NORMALLY --> HANDOVER_PREPARATION',
        'HANDOVER_PREPARATION --> HANDOVER_LEAVING',
        'HANDOVER_JOINING --> HANDOVER_PATH_SWITCH',
        'HANDOVER_PATH_SWITCH --> CONNECTED_NORMALLY',
        'CONNECTED_NORMALLY --> CONNECTION_RECONFIGURATION',
        'CONNECTION_RECONFIGURATION --> CONNECTED_NORMALLY') : 'Handover',
        ('INITIAL_RANDOM_ACCESS --> CONNECTION_SETUP',
        'CONNECTION_SETUP --> ATTACH_REQUEST',
        'ATTACH_REQUEST --> CONNECTED_NORMALLY',
        'CONNECTED_NORMALLY --> CONNECTION_RECONFIGURATION',
        'CONNECTION_RECONFIGURATION --> CONNECTED_NORMALLY') : 'Initial Connection'}

    logs['RecognizedMessage'] = 'Uncategorized'
    for _, UElogs in logs[['Time(s)', 'Message', 'UE_ID']].groupby('UE_ID'):
        # We assume that messages within a 20 ms interval are from the same event
        singleEvent = UElogs['Time(s)'].diff().gt(0.03).cumsum()
        for _, subDF in UElogs.groupby(singleEvent):
            messageSequence = tuple(subDF['Message'])
            if messageSequence in messageSequences:
                logs.loc[subDF.index[-1], 'RecognizedMessage'] = messageSequences[messageSequence]
                logs.loc[subDF.index[:-1], 'RecognizedMessage'] = None

    stillUncategorized = (logs['RecognizedMessage'] == 'Uncategorized')
    logs.loc[stillUncategorized, 'RecognizedMessage'] = logs.loc[stillUncategorized, 'Message']

    HOs = logs[logs['RecognizedMessage'] == 'Handover']
    HOdata = []
    for _, row in HOs.iterrows():
        dataSlice = UEmeasurements[
            (UEmeasurements['UE_ID'] == row['UE_ID']) &
            (UEmeasurements.index < row['Time(s)'] + 5) & 
            (UEmeasurements.index > row['Time(s)'] - 5)
        ]

        dataSliceBefore = dataSlice.loc[(dataSlice.index < row['Time(s)'] - 1) &
                                        (dataSlice['Status'] == 'Serving'), 'eNB_ID'].unique()
        dataSliceAfter = dataSlice.loc[(dataSlice.index > row['Time(s)'] + 1) &
                                       (dataSlice['Status'] == 'Serving'), 'eNB_ID'].unique()

        if ((len(dataSliceBefore) == 1) and
            (len(dataSliceAfter) == 1) and
            (dataSliceBefore[0] != dataSliceAfter[0])
        ):
            HOdata.append((dataSlice, row['Time(s)']))

    return logs, HOdata