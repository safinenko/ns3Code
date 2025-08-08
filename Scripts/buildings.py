from scipy.spatial.distance import pdist
import numpy as np
from .settings import nBuildings, buildingMinSize, buildingMaxSize

minDist = 25 + 2 * buildingMaxSize

def generateBuildings(count = 0):
    if count > 50:
        raise('Too many attempts!')

    buildingSizes = np.random.randint(buildingMinSize, buildingMaxSize, size = nBuildings).astype(float)
    xPts = np.random.randint(13000, 17000, size = nBuildings).astype(float)
    yPts = np.random.randint(7000, 12000, size = nBuildings).astype(float)
    heights = np.random.randint(15, 50, size = nBuildings).astype(float)

    if min(pdist(list(zip(xPts, yPts)))) > minDist:
        return buildingSizes, xPts, yPts, heights
    
    else:
        return generateBuildings(count + 1)

