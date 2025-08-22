#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/mobility-module.h"
#include "ns3/lte-module.h"
#include "ns3/internet-module.h"
#include "ns3/config-store.h"

using namespace ns3;
using std::cout, std::endl;

const unsigned int nUEs = 15;
const unsigned int nMinutes = 20;
const unsigned int UeMeasurementsFilterPeriod = 200; // ms


std::ofstream RSRP_RSRQ_writer;
std::map<uint16_t, uint32_t> cellIDtoNodeID;


void ReportUeMeasurements(const unsigned int UE_ID,
                          const uint16_t /*RNTI*/,
                          const uint16_t cellId,
                          const double rsrp,
                          const double rsrq,
                          const bool cell_is_servingCell,
                          const uint8_t /*cc_id*/)
{
    const auto eNBfound = cellIDtoNodeID.find(cellId);
    const auto eNB_ID = ((eNBfound != cellIDtoNodeID.end()) ? eNBfound->second : -1);

    RSRP_RSRQ_writer << Simulator::Now().GetSeconds() << ","
                     << UE_ID << ","
                     << (cell_is_servingCell ? "Serving" : "Neighbor") << ","
                     << eNB_ID << ","
                     << rsrp << ","
                     << rsrq << endl;
}


int main(int argc, char *argv[])
{
    Config::SetDefault("ns3::LteUePhy::UeMeasurementsFilterPeriod",
                       TimeValue(MilliSeconds(UeMeasurementsFilterPeriod)));

    // const double networkHysteresis = 3.0;
    // const double networkTimeToTrigger = 256;
    double fairfieldHysteresis = 0.1;
    double fairfieldTimeToTrigger = 100;
    unsigned int learning_episode = 0;
    unsigned int learning_episode_runID = 0;
    CommandLine cmd;
    cmd.AddValue("Hysteresis", "A3 Handover hysteresis parameter", fairfieldHysteresis);
    cmd.AddValue("TimeToTrigger", "A3 Handover time to trigger parameter", fairfieldTimeToTrigger);
    cmd.AddValue("episode", "Learning: episode number", learning_episode);
    cmd.AddValue("runID", "Learning: run ID for episode", learning_episode_runID);
    cmd.Parse(argc, argv);

    std::vector<int> eNB_IDs;
    std::vector<double> eNB_ID_x;
    std::vector<double> eNB_ID_y;

    std::ifstream eNB_locations_file("inputData/networkTopo.csv");
    std::string line;
    std::getline(eNB_locations_file, line); 

    while (std::getline(eNB_locations_file, line))
    {
        std::stringstream ss(line);
        std::string field;

        std::getline(ss, field, ',');
        eNB_IDs.push_back(std::stoi(field));
        std::getline(ss, field, ','); // Skip lat column
        std::getline(ss, field, ','); // Skip lon column

        std::getline(ss, field, ',');
        eNB_ID_x.push_back(std::stod(field));
        std::getline(ss, field, ',');
        eNB_ID_y.push_back(std::stod(field));
    }
    eNB_locations_file.close();

    NodeContainer enb_nodes;
    enb_nodes.Create(eNB_IDs.size());
    MobilityHelper eNB_mobility;
    Ptr<ListPositionAllocator> enbPositionAlloc = CreateObject<ListPositionAllocator>();
    for (unsigned int i = 0; i < eNB_IDs.size(); i++)
    {
        Vector enbPosition(eNB_ID_x[i], eNB_ID_y[i], 20.0);
        enbPositionAlloc->Add(enbPosition);
    }
    eNB_mobility.SetPositionAllocator(enbPositionAlloc);
    eNB_mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    eNB_mobility.Install(enb_nodes);

    // UEs
    NodeContainer ueNodes;
    ueNodes.Create(nUEs);
    MobilityHelper UE_mobility;
    UE_mobility.SetMobilityModel("ns3::WaypointMobilityModel");
    UE_mobility.Install(ueNodes);

    std::ifstream UE_locations_file("inputData/UE_locations.csv");
    std::getline(UE_locations_file, line); 

    std::vector<std::vector<double>> UEs_times(nUEs);
    std::vector<std::vector<double>> UEs_x(nUEs);
    std::vector<std::vector<double>> UEs_y(nUEs);

    while (std::getline(UE_locations_file, line))
    {
        std::stringstream ss(line);
        std::getline(ss, line, ',');
        const double time = std::stod(line);
        std::getline(ss, line, ',');
        const double x = std::stod(line);
        std::getline(ss, line, ',');
        const double y = std::stod(line);
        std::getline(ss, line, ',');
        const uint32_t UE_ID = std::stoi(line);

        UEs_times[UE_ID].push_back(time);
        UEs_x[UE_ID].push_back(x);
        UEs_y[UE_ID].push_back(y);
    }

    for (unsigned int UE_ID = 0; UE_ID < UEs_times.size(); UE_ID++)
    {
        Ptr<WaypointMobilityModel> waypoints = 
                ueNodes.Get(UE_ID)->GetObject<WaypointMobilityModel>();
        for (unsigned int i = 0; i < UEs_times[UE_ID].size(); i++)
            waypoints->AddWaypoint(Waypoint(Seconds(UEs_times[UE_ID][i]),
                                   Vector(UEs_x[UE_ID][i], UEs_y[UE_ID][i], 1.0)));
    }

    // ns-3: set up LTE network
    LogComponentEnableAll(LOG_PREFIX_TIME);
    LogComponentEnable("LteEnbRrc", LOG_LEVEL_INFO);

    Ptr<LteHelper> lteHelper = CreateObject<LteHelper>();
    Ptr<PointToPointEpcHelper> epcHelper = CreateObject<PointToPointEpcHelper>();
    lteHelper->SetEpcHelper(epcHelper);

    lteHelper->SetEnbDeviceAttribute("DlEarfcn", UintegerValue(100));    // 2120 MHz
    lteHelper->SetEnbDeviceAttribute("UlEarfcn", UintegerValue(18100));  // 1930 MHz

    lteHelper->SetFadingModel("ns3::TraceFadingLossModel");
    std::string fadingFilePath = "../../src/lte/model/fading-traces/";
    if (!std::filesystem::is_directory(fadingFilePath))
    {
        cout << fadingFilePath << endl;
        throw std::invalid_argument("Path to fading trace file is not correct");
    }

    lteHelper->SetFadingModelAttribute("TraceFilename",
        StringValue(fadingFilePath + "fading_trace_EVA_60kmph.fad"));
    lteHelper->SetFadingModelAttribute("TraceLength", TimeValue(Seconds(10)));
    lteHelper->SetFadingModelAttribute("SamplesNum", UintegerValue(10000));
    lteHelper->SetFadingModelAttribute("WindowSize", TimeValue(Seconds(0.5)));
    lteHelper->SetFadingModelAttribute("RbNum", UintegerValue(100));

    Config::SetDefault("ns3::LteEnbPhy::TxPower", DoubleValue(40));
    Config::SetDefault("ns3::LteUePhy::TxPower", DoubleValue(23));

    lteHelper->SetHandoverAlgorithmType("ns3::A3RsrpHandoverAlgorithm");

    // Add handover info
    NetDeviceContainer enbLteDevs = lteHelper->InstallEnbDevice(enb_nodes);
    NetDeviceContainer ueLteDevs = lteHelper->InstallUeDevice(ueNodes);
    lteHelper->AddX2Interface(enb_nodes);

    lteHelper->SetHandoverAlgorithmAttribute("Hysteresis", DoubleValue(fairfieldHysteresis));
    lteHelper->SetHandoverAlgorithmAttribute("TimeToTrigger",
                                             TimeValue(MilliSeconds(fairfieldTimeToTrigger)));

    InternetStackHelper ISH;
    ISH.Install(ueNodes);
    epcHelper->AssignUeIpv4Address(ueLteDevs);

    for (unsigned int UE_ID = 0; UE_ID < nUEs; UE_ID++)
        lteHelper->Attach(ueLteDevs.Get(UE_ID));

    for (unsigned int eNB_ID = 0; eNB_ID < eNB_IDs.size(); eNB_ID++)
    {
        Ptr<LteEnbNetDevice> enbDevice = enbLteDevs.Get(eNB_ID)->GetObject<LteEnbNetDevice>();
        const uint16_t cellID = enbDevice->GetCellId();
        const uint32_t nodeID = enb_nodes.Get(eNB_ID)->GetId();
        cellIDtoNodeID[cellID] = nodeID;
    }

    // Set up callbacks
    std::string prefixPath = "outputs/ep_" + std::to_string(learning_episode)
                           + "/run_" + std::to_string(learning_episode_runID);
    if (!std::filesystem::is_directory(prefixPath))
    {
        cout << prefixPath << endl;
        throw std::invalid_argument("Output path does not exist");
    }

    // Report UE measurement by UE_ID
    RSRP_RSRQ_writer.open(prefixPath + "/rsrp_rsrq_trace.csv", std::ios::out);
    RSRP_RSRQ_writer << "Time(s),UE_ID,Status,eNB_ID,RSRP,RSRQ" << endl;

    for (unsigned int UE_ID = 0; UE_ID < nUEs; UE_ID++)
    {
        Ptr<LteUeNetDevice> ueDevice = ueLteDevs.Get(UE_ID)->GetObject<LteUeNetDevice>();
        Ptr<LteUePhy> ueRrc = ueDevice->GetPhy();
        ueRrc->TraceConnectWithoutContext("ReportUeMeasurements",
                                          MakeBoundCallback(&ReportUeMeasurements, UE_ID));
    }

    // Simulator::Stop(Seconds(10));
    Simulator::Stop(Seconds(60) * nMinutes);
    Simulator::Run();
    Simulator::Destroy();

    RSRP_RSRQ_writer.close();
}
