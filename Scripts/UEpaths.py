from networkx import NetworkXNoPath
import osmnx as ox
import numpy as np
import pandas as pd
from .settings import minTravelDist, nMinutes, nUEs


weight = lambda d, kpi: min(attr.get(kpi, 1) for attr in d.values())
lengthFn = lambda d: min(attr['geometry'].length for attr in d.values())


def generatePts(streetNetwork):
    UEstart = streetNetwork.nodes[['x', 'y']].sample().iloc[0]
    UEend = streetNetwork.nodes[['x', 'y']].sample().iloc[0]
    if np.sqrt(sum((UEstart - UEend)**2)) > minTravelDist:
        return UEstart, UEend
    else:
        return generatePts(streetNetwork)


def generateRoute(streetNetwork, start = None):
    if start is None:
        start, end = generatePts(streetNetwork)
        start = start.name
    else:
        _, end = generatePts(streetNetwork)

    try:
        route = ox.routing._single_shortest_path(
            streetNetwork.oxgraph,
            start,
            end.name,
            weight = 'travel_time'
        )
    except NetworkXNoPath:
        return generateRoute(streetNetwork)
    
    return route


def generateAllRoutes(streetNetwork):
    # Generates random routes for UEs along the street network with the starting
    # and destination points being at least `minDist` meters far apart. Routes are
    # generated until the total simulation time is exhausted.
    allRoutes = []
    for i in range(nUEs):
        fullRoute = generateRoute(streetNetwork)
        totalTime = 0
        for u, v in zip(fullRoute[:-1], fullRoute[1:]):
            totalTime += weight(streetNetwork.oxgraph[u][v], 'travel_time')
        
        while totalTime < nMinutes * 60:
            route = generateRoute(streetNetwork, fullRoute[-1])
            routeTime = 0
            for u, v in zip(route[:-1], route[1:]):
                routeTime += weight(streetNetwork.oxgraph[u][v], 'travel_time')
            
            totalTime += routeTime
            fullRoute.extend(route[1:])
        
        allRoutes.append(fullRoute)

    return allRoutes


def convertPathsToTimeseries(UEroutes, streetNetwork):
    # Converts a collection of routes (consisting of OSM street network nodes) to
    # a uniform time-series of UE locations.
    UElocations = []

    for UE_ID, route in enumerate(UEroutes):
        segmentStartTime = 0
        directPathLocations = [tuple(streetNetwork.nodes.loc[route[0]][['x', 'y']])]
        directPathTimes = [0]

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

        previousTimes = list(np.arange(0, directPathTimes[0] -1))
        nextTimes = list(np.arange(directPathTimes[-1] + 1, nMinutes * 60 + 1))

        pathData = pd.DataFrame(
            index = previousTimes + directPathTimes + nextTimes,
            data = [directPathLocations[0]] * len(previousTimes)
                 + directPathLocations + [directPathLocations[-1]] * len(nextTimes),
            columns = ['x', 'y'])
        pathData['UE_ID'] = UE_ID + 1
        pathData.index.name = 'Time(s)'

        UElocations.append(pathData[pathData.index <= nMinutes * 60].copy())

    return UElocations
