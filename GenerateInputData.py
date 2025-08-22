import pandas as pd
import numpy as np

np.random.seed(34)

###############################################################################
# Import street network, topology, UEs
from Scripts.streetNetwork import StreetNetwork
from Scripts.UEpaths import generateAllRoutes, convertPathsToTimeseries
from Scripts.settings import nUEs, nMinutes, UeMeasurementsFilterPeriod
# from Scripts.buildings import generateBuildings

streetNetwork = StreetNetwork()

# Fetch eNB data
# frequencies = [1900, 850, 700, 1700]
radioTowers = pd.read_csv('inputData/networkTopo.csv')
radioTowersX, radioTowersY = streetNetwork.projectionMap(
    radioTowers['lon'], radioTowers['lat']
)

radioTowers['x'] = radioTowersX
radioTowers['y'] = radioTowersY
radioTowers.to_csv('inputData/networkTopo.csv', index = False)

UEroutes = generateAllRoutes(streetNetwork, (radioTowersX[0], radioTowersY[0]))
UElocations = convertPathsToTimeseries(UEroutes, streetNetwork)

# Store UE paths and tower locations
UElocationsDF = pd.concat(UElocations)
ue_lon, ue_lat = streetNetwork.projectionMap(
    UElocationsDF['x'], UElocationsDF['y'], inverse = True
)
UElocationsDF['lat'] = ue_lat
UElocationsDF['lon'] = ue_lon
UElocationsDF.to_csv('inputData/UE_locations.csv')
