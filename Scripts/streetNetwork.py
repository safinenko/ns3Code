import osmnx as ox
import pyproj
from pathlib import Path

# Name of the street network file
roadNetworkFile = Path('inputData/roadNetwork.graphml')

# Bounding box for the target region
boundingBox = [-95.826972, 29.963325, -95.657067, 30.082114]

# Projection from (lat, lon) to a flat cartesian (x, y) system.
_baseProjectionMap = pyproj.Proj('+proj=cea +lon=0 +lat_ts=37.5 '
                                 '+ellps=WGS84 +units=m +no_defs '
                                 '+x_0=11000000 '
                                 '+y_0=-3200000')

def fetchStreetNetwork():
    # Import the street network file (osmnx/networkx.MultiDiGraph object) if it
    # exists; else download it and project to a Cartesian coordinate system.

    if not Path(roadNetworkFile).is_file():
        assert False, 'No street network file found, uncomment to download OSM data'
        roadNetwork = ox.graph_from_bbox(boundingBox,
                                         network_type = 'drive_service')
        roadNetwork = ox.projection.project_graph(roadNetwork,
                                                  to_crs = _baseProjectionMap.crs)

        roadNetwork = ox.simplification.consolidate_intersections(
            roadNetwork,
            tolerance = 5,
            rebuild_graph = True,
            dead_ends = False,
            reconnect_edges = True
        )

        roadNetwork = ox.routing.add_edge_speeds(roadNetwork)
        roadNetwork = ox.routing.add_edge_travel_times(roadNetwork)

        ox.io.save_graphml(roadNetwork, filepath = roadNetworkFile)

    return ox.io.load_graphml(roadNetworkFile)


class StreetNetwork:
    def __init__(self):
        oxgraph = fetchStreetNetwork()

        # Re-project the network so that the lower left corner has the coordinates (0, 0)
        oldX, oldY = _baseProjectionMap(boundingBox[0], boundingBox[1])
        self.projectionMap = pyproj.Proj('+proj=cea +lon=0 +lat_ts=37.5 '
                                        '+ellps=WGS84 +units=m +no_defs '
                                        f'+x_0={11000000 - oldX} '
                                        f'+y_0={-3200000 - oldY}')
        self.oxgraph = ox.projection.project_graph(oxgraph,
                                                 to_crs = self.projectionMap.crs)
        self.nodes, self.edges = ox.convert.graph_to_gdfs(self.oxgraph)

        self.x_bounds, self.y_bounds = self.projectionMap(
            [boundingBox[0], boundingBox[2]],
            [boundingBox[1], boundingBox[3]]
        )

