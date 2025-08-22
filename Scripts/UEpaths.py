from networkx import NetworkXNoPath
import osmnx as ox
import numpy as np
import pandas as pd
from .settings import minTravelDist, nMinutes, nUEs


weight = lambda d, kpi: min(attr.get(kpi, 1) for attr in d.values())
lengthFn = lambda d: min(attr['geometry'].length for attr in d.values())


def generateRandomBoundaryPoint(streetNetwork):
    # Generate a random point on the boundary of the domain
    if np.random.choice([True, False]):
        x = np.random.choice(streetNetwork.x_bounds)
        y = np.random.uniform(*streetNetwork.y_bounds)
    else:
        x = np.random.uniform(*streetNetwork.x_bounds)
        y = np.random.choice(streetNetwork.y_bounds)
    return (x, y)


def generatePts(streetNetwork, target = None, toTarget = True):
    if toTarget:
        nearTargetPt = streetNetwork.nodes[['x', 'y']].sample(1)
        while sum(((nearTargetPt - target)**2).values[0]) > 500**2:
            nearTargetPt = streetNetwork.nodes[['x', 'y']].sample(1)
        pointIndex = nearTargetPt.index[0]

    else:
        randomPts = generateRandomBoundaryPoint(streetNetwork)
        pointIndex = ox.distance.nearest_nodes(streetNetwork.oxgraph, *randomPts)
        pointIndex = streetNetwork.nodes.loc[pointIndex, ['x', 'y']].name

    return pointIndex


def generateRoute(streetNetwork, start = None, targetSite = None, toTarget = True):
    if start is None:
        start = generatePts(streetNetwork, toTarget = False)
        end = generatePts(streetNetwork, target = targetSite, toTarget = True)
        toTarget = False
    else:
        end = generatePts(streetNetwork, target = targetSite, toTarget = toTarget)

    try:
        route = ox.routing._single_shortest_path(
            streetNetwork.oxgraph,
            start,
            end,
            weight = 'travel_time'
        )
    except NetworkXNoPath:
        return None

    return route


def generateAllRoutes(streetNetwork, targetSite):
    # Generates random routes for UEs along the street network with the starting
    # and destination points being at least `minDist` meters far apart. Individual routes
    # are generated until their total run time exceeds total simulation time.
    allRoutes = []
    for i in range(nUEs):
        fullRoute = generateRoute(streetNetwork, targetSite = targetSite, toTarget = True)
        toTarget = False
        totalTime = 0
        for u, v in zip(fullRoute[:-1], fullRoute[1:]):
            totalTime += weight(streetNetwork.oxgraph[u][v], 'travel_time')
        
        while totalTime < nMinutes * 60:
            route = generateRoute(streetNetwork, fullRoute[-1], targetSite = targetSite,
                                  toTarget = toTarget)
            while route is None:
                fullRoute = fullRoute[:-1]
                route = generateRoute(streetNetwork, fullRoute[-1], targetSite = targetSite,
                                      toTarget = toTarget)
            
            routeTime = 0
            for u, v in zip(route[:-1], route[1:]):
                routeTime += weight(streetNetwork.oxgraph[u][v], 'travel_time')
            
            totalTime += routeTime
            fullRoute.extend(route[1:])
            toTarget = not toTarget
        
        allRoutes.append(fullRoute)

    return allRoutes


def convertPathsToTimeseries(UEroutes, streetNetwork):
    # Converts a collection of routes (consisting of OSM street network nodes) to
    # a uniform time-series of UE locations.
    UElocations = []

    for UE_ID, route in enumerate(UEroutes):
        segmentStartTime = 0
        directPathLocations = []
        directPathTimes = []

        for u, v in zip(route[:-1], route[1:]):
            segmentTravelTime = weight(streetNetwork.oxgraph[u][v], 'travel_time')
            for tStamp in np.arange(np.ceil(segmentStartTime),
                                    segmentStartTime + segmentTravelTime):
                fraction = (tStamp - segmentStartTime) / segmentTravelTime
                newCoord = np.ravel(
                    streetNetwork.oxgraph[u][v][0]['geometry'].interpolate(
                        fraction,
                        normalized = True
                    ).xy
                )

                directPathTimes.append(tStamp)
                directPathLocations.append(newCoord)
            segmentStartTime += segmentTravelTime

        directPathTimes.append(tStamp + 1)
        directPathLocations.append(tuple(streetNetwork.nodes.loc[route[-1]][['x', 'y']]))

        previousTimes = list(np.arange(0, directPathTimes[0] - 1))
        nextTimes = list(np.arange(directPathTimes[-1] + 1, nMinutes * 60 + 1))

        pathData = pd.DataFrame(
            index = previousTimes + directPathTimes + nextTimes,
            data = [directPathLocations[0]] * len(previousTimes)
                 + directPathLocations + [directPathLocations[-1]] * len(nextTimes),
            columns = ['x', 'y'])
        pathData['UE_ID'] = UE_ID
        pathData.index.name = 'Time(s)'

        UElocations.append(pathData[pathData.index <= nMinutes * 60].copy())

    return UElocations
