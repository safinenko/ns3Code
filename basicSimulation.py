from ns import ns
import pandas as pd
import numpy as np
np.random.seed(34)

###############################################################################
# Import street network, topology, UEs
from Scripts.streetNetwork import StreetNetwork
from Scripts.networkTopo import fetchNetwork
from Scripts.UEpaths import generateAllRoutes, convertPathsToTimeseries
from Scripts.settings import nUEs, nMinutes, UeMeasurementsFilterPeriod

streetNetwork = StreetNetwork()
radioTowersX, radioTowersY = fetchNetwork()
UEroutes = generateAllRoutes(streetNetwork)
UElocations = convertPathsToTimeseries(UEroutes, streetNetwork)

# Store UE paths and tower locations
UElocationsDF = pd.concat(UElocations)
ue_lon, ue_lat = streetNetwork.projectionMap(
    UElocationsDF['x'], UElocationsDF['y'], inverse = True
)
UElocationsDF['lat'] = ue_lat
UElocationsDF['lon'] = ue_lon
UElocationsDF[['UE_ID', 'lat', 'lon']].to_csv('outputs/UE_locations.csv')

with open('outputs/tower_locations.csv', 'w') as f:
    f.write('lon,lat\n')
    for x, y in zip(radioTowersX, radioTowersY):
        lon, lat = streetNetwork.projectionMap(x, y, inverse = True)
        f.write(f'{lon},{lat}\n')

###############################################################################
# ns-3: configuration
ns.Config.SetDefault('ns3::LteUePhy::UeMeasurementsFilterPeriod',
                     ns.TimeValue(ns.MilliSeconds(UeMeasurementsFilterPeriod)))

# Output simulation configuration strings and parameters to file
# ns.Config.SetDefault('ns3::ConfigStore::Filename',
#                      ns.StringValue('output-attributes.txt'));
# ns.Config.SetDefault('ns3::ConfigStore::FileFormat',
#                      ns.StringValue('RawText'))
# ns.Config.SetDefault('ns3::ConfigStore::Mode',
#                      ns.StringValue ('Save'))

###############################################################################
# ns-3: eNBs setup
enb = ns.NodeContainer()
enb.Create(len(radioTowersX))

mobility_helper = ns.MobilityHelper()

position_allocator = ns.ListPositionAllocator()
for xPos, yPos in zip(radioTowersX, radioTowersY):
    position_allocator.Add(ns.Vector(xPos, yPos, 10.0))

mobility_helper.SetPositionAllocator(position_allocator)
mobility_helper.SetMobilityModel('ns3::ConstantPositionMobilityModel')
mobility_helper.Install(enb)

###############################################################################
# ns-3: UEs setup
ue = ns.NodeContainer()
ue.Create(nUEs)

mobility = ns.MobilityHelper()
mobility.SetMobilityModel('ns3::WaypointMobilityModel')
mobility.Install(ue)

for i in range(nUEs):
    WMmobility = ue.Get(i).GetObject[ns.MobilityModel]()
    for tStamp, _, xPos, yPos in UElocations[i].itertuples():
        WMmobility.AddWaypoint(ns.Waypoint(ns.Time(ns.Seconds(tStamp)),
                                           ns.Vector(xPos, yPos, 1.)))

###############################################################################
# ns-3: set up LTE network
ns.LogComponentEnableAll(ns.LOG_PREFIX_TIME)
ns.LogComponentEnable('LteEnbRrc', ns.LOG_LEVEL_INFO)

epc = ns.CreateObject[ns.PointToPointEpcHelper]()
lte = ns.CreateObject[ns.LteHelper]()

lte.SetEpcHelper(epc)
lte.SetHandoverAlgorithmType('ns3::A3RsrpHandoverAlgorithm')
lte.SetHandoverAlgorithmAttribute('Hysteresis', ns.DoubleValue(0.2))
lte.SetHandoverAlgorithmAttribute('TimeToTrigger', ns.TimeValue(ns.MilliSeconds(100)))

ns.Config.SetDefault('ns3::LteHelper::PathlossModel',
                     ns.StringValue('ns3::BuildingsPropagationLossModel'));


# Add handover info
edevs = lte.InstallEnbDevice(enb)
lte.AddX2Interface(enb)
udevs = lte.InstallUeDevice(ue)

ns.InternetStackHelper().Install(ue)
epc.AssignUeIpv4Address(udevs)

for i in range(nUEs):
    lte.Attach(udevs.Get(i))


# ns.Config.SetDefault("ns3::UdpClient::Interval", ns.TimeValue(ns.MilliSeconds(10)));
# ns.Config.SetDefault("ns3::UdpClient::MaxPackets", ns.UintegerValue(1000000));
# ns.Config.SetDefault("ns3::LteHelper::UseIdealRrc", ns.BooleanValue(True));
# lte.SetEnbDeviceAttribute('DlEarfcn', ns.UintegerValue(100));   # 2120 MHz
# lte.SetEnbDeviceAttribute('UlEarfcn', ns.UintegerValue(18100)); # 1930 MHz


# edevs = lte.InstallEnbDevice(enb)
# lte.AddX2Interface(enb)
# udevs = lte.InstallUeDevice(ue)

# ns.InternetStackHelper().Install(ue)
# epc.AssignUeIpv4Address(udevs)

# bearer = ns.EpsBearer(ns.EpsBearer.GBR_CONV_VOICE)
# lte.ActivateDedicatedEpsBearer(udevs.Get(0), bearer, tft)


###############################################################################
# ns-3: set up callbacks
ns.cppyy.cppdef(open('Scripts/cppdefFiles.cpp', 'r').read())

RSRP_RSRQ_writer = open('outputs/rsrp_rsrq_trace.csv', 'w')
RSRP_RSRQ_writer.write('Time(s),IMSI,UE_NodeID,UE_RNTI,Status,eNB_NodeID,CellID,RSRP,RSRQ\n')


RNTItoIMSI = {}
cellIDtoNodeID = {}
IMSItoNodeID = {}

for i in range(nUEs):
    IMSItoNodeID[udevs.Get(i).GetImsi()] = ue.Get(i).GetId()

for i in range(enb.GetN()):
    enbDevice = edevs.Get(i).GetObject[ns.LteEnbNetDevice]()
    cellID = enbDevice.GetCellId()
    nodeID = enb.Get(i).GetId()
    cellIDtoNodeID[cellID] = nodeID


def RSRP_RSRQ_callback(RNTI, cell_id, rsrp, rsrq, is_serving, cc_id):
    '''
    This function is called for every UE measurement report. It distinguishes between
    serving and neighbor cell measurements.
    '''

    IMSI = RNTItoIMSI.get(RNTI, np.nan) # Use 0 or another invalid IMSI if not found
    if not np.isnan(IMSI):
        ue_node_id = IMSItoNodeID.get(IMSI, np.nan)
        enb_node_id = cellIDtoNodeID.get(cell_id, np.nan)
        status = 'Serving' if is_serving else 'Neighbor'
        # Write the enriched data, including the permanent IMSI
        RSRP_RSRQ_writer.write(
            f'{ns.Simulator.Now().GetSeconds()},{IMSI},{ue_node_id},'
            f'{RNTI},{status},{enb_node_id},{cell_id},{rsrp:.03f},{rsrq:.03f}\n'
        )


UEMeasureTraceCallback = ns.ReportUeMeasurements(RSRP_RSRQ_callback)
ns.Config.ConnectWithoutContext(
    '/NodeList/*/DeviceList/*/$ns3::LteUeNetDevice'
    '/ComponentCarrierMapUe/*/LteUePhy/ReportUeMeasurements',
    UEMeasureTraceCallback
)


def UEconnectionEstablishedCallBackP(IMSI, target_cellID, RNTI):
    # Update the map with the initial RNTI for this IMSI
    RNTItoIMSI[RNTI] = IMSI

UEconnectionEstablishedcallback = ns.HandoverEndOkOrConnectionEstablished(
    UEconnectionEstablishedCallBackP
)
ns.Config.ConnectWithoutContext(
    '/NodeList/*/DeviceList/*/LteUeRrc/ConnectionEstablished',
    UEconnectionEstablishedcallback
)


ns.Simulator.Stop(ns.Seconds(60 * nMinutes))
ns.Simulator.Run()
ns.Simulator.Destroy()

RSRP_RSRQ_writer.close()
