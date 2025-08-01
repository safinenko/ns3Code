import numpy as np
from scipy.spatial.distance import pdist


def generateTowers():
    radioTowersX = np.concat([
        np.random.randint(13000, 17000, size = 3),
        np.random.randint(1000, 10000, size = 2),
    ]).astype(float)
    radioTowersY = np.concat([
        np.random.randint(7000, 12000, size = 3),
        np.random.randint(1000, 18000, size = 2),
    ]).astype(float)

    return radioTowersX, radioTowersY


def fetchNetwork():
    # Ensure that there is a minimal distance between towers
    minDist = 1000 # meters

    minDistSatisfied = False
    while not minDistSatisfied:
        radioTowersX, radioTowersY = generateTowers()
        if min(pdist(list(zip(radioTowersX, radioTowersY)))) > minDist:
            minDistSatisfied = True

    return radioTowersX, radioTowersY
