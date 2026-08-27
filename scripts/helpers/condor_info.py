#!/usr/bin/env python3
import htcondor2

collector = htcondor2.Collector()
slots = collector.query(
    htcondor2.AdType.Startd,
    projection=["Name", "Cpus", "Memory"],
)

schedd_ad = collector.locate(htcondor2.DaemonType.Schedd)

print(f"slots: {len(slots)}")
print(f"schedd: {schedd_ad['Name']}")
