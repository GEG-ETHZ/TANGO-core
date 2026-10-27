"""What each component type offers: the models drawn in the diagrams, and the external simulators a
connector could stand in with.

The well's ``lumped`` variant is still registered but no longer drawn: the lead developer retired it
from the picture (see .agent/FINDINGS.md). RAFT is the group's own open-source reservoir simulator and
the main reservoir connector target.
"""

PARTS = [
    ("surface", ["graph (TESPy)"], ["Aspen"]),
    ("well", ["numerical"], ["Moskito", "OLGA", "T2Well"]),
    ("reservoir", ["lumped"], ["RAFT", "CMG", "MOOSE", "Eclipse", "OPM", "tNAV"]),
    ("economic", [], []),
]
CONNECTOR = "connector"
