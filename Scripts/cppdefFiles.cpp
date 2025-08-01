#include "ns3/core-module.h"

namespace ns3
{
    const Callback<void, uint16_t, uint16_t, double, double, bool, uint8_t>
    ReportUeMeasurements(void(*func)(uint16_t, uint16_t, double, double, bool, uint8_t))
    {
       return MakeCallback(func);
    }

    // Callback ConnectionEstablished and HandoverEndOk strings 
    const Callback<void, uint64_t, uint16_t, uint16_t>
    HandoverEndOkOrConnectionEstablished(void(*func)(uint64_t, uint16_t, uint16_t))
    {
       return MakeCallback(func);
    }
}
