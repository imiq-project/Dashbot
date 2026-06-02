"""Canonical list of FIWARE real-time entity types the agent may query.

Mostly IoT sensors (Weather, Parking, …) plus the OVGU Mensa, whose
`todaysMenu` attribute carries the live daily menu. Imported by
fiware_server and context_server.
"""

REALTIME_TYPES = frozenset({
    "Weather",
    "Parking",
    "AirQuality",
    "Traffic",
    "Room",
    "Vehicle",
    "WaterLevel",
    "DigitalTwin",
    "Mensa",  # not a sensor: live daily menu via `todaysMenu` (entity id Rest:MensaUni)
})
