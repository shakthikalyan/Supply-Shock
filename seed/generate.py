"""
seed/generate.py
Deterministic supply-chain graph seeder for SupplyShock.

Run:
    python seed/generate.py [--host localhost] [--port 6379] [--graph supplyshock] [--wipe]

Planted surprise (the story):
    A single tier-2 capacitor supplier (SUP-T2-01, "CapTech Asia") feeds three
    tier-1 suppliers that look independent (ElecCore, ChipNation, PowerFlex).
    All three ship exclusively through Port Shanghai (PORT-01).
    When PORT-01 closes, 14 high-priority orders are fully blocked because every
    path for their critical parts runs through that single port.
    The "diversified" supply base is a single point of failure 4 hops from the
    event: Port → Supplier × 3 → Part → Product → Order.
"""

import argparse
import random
import sys
from datetime import date, timedelta

import falkordb

# ── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
rng = random.Random(SEED)

# ── Graph constants ──────────────────────────────────────────────────────────
GRAPH_NAME = "supplyshock"


# ── Helpers ──────────────────────────────────────────────────────────────────

def rdate(days_from_now: int) -> str:
    return (date.today() + timedelta(days=days_from_now)).isoformat()


def r(lo: float, hi: float, digits: int = 2) -> float:
    return round(rng.uniform(lo, hi), digits)


def ri(lo: int, hi: int) -> int:
    return rng.randint(lo, hi)


# ── Data definitions ─────────────────────────────────────────────────────────

PORTS = [
    {"id": "PORT-01", "name": "Shanghai",      "country": "CN", "status": "ok"},
    {"id": "PORT-02", "name": "Rotterdam",     "country": "NL", "status": "ok"},
    {"id": "PORT-03", "name": "Los Angeles",   "country": "US", "status": "ok"},
    {"id": "PORT-04", "name": "Singapore",     "country": "SG", "status": "ok"},
    {"id": "PORT-05", "name": "Hamburg",       "country": "DE", "status": "ok"},
    {"id": "PORT-06", "name": "Busan",         "country": "KR", "status": "ok"},
]

FACTORIES = [
    {"id": "FAC-01", "name": "Austin Assembly",   "region": "US"},
    {"id": "FAC-02", "name": "Munich Plant",      "region": "EU"},
    {"id": "FAC-03", "name": "Taipei Works",      "region": "APAC"},
    {"id": "FAC-04", "name": "Chennai Fab",       "region": "APAC"},
    {"id": "FAC-05", "name": "Monterrey Hub",     "region": "LATAM"},
    {"id": "FAC-06", "name": "Warsaw Center",     "region": "EU"},
    {"id": "FAC-07", "name": "Jakarta Plant",     "region": "APAC"},
    {"id": "FAC-08", "name": "Detroit Works",     "region": "US"},
]

# Tier-2 suppliers (upstream, share hidden dependency)
# The "planted" ones feed the three tier-1 choke-point suppliers
TIER2_SUPPLIERS = [
    {"id": "SUP-T2-01", "name": "CapTech Asia",      "country": "CN", "tier": 2, "reliability": 0.91, "status": "ok"},
    {"id": "SUP-T2-02", "name": "RawMat Corp",       "country": "TW", "tier": 2, "reliability": 0.95, "status": "ok"},
    {"id": "SUP-T2-03", "name": "ChemBase GmbH",     "country": "DE", "tier": 2, "reliability": 0.97, "status": "ok"},
    {"id": "SUP-T2-04", "name": "PolySource Ltd",    "country": "IN", "tier": 2, "reliability": 0.88, "status": "ok"},
    {"id": "SUP-T2-05", "name": "MetalPrime SA",     "country": "BR", "tier": 2, "reliability": 0.93, "status": "ok"},
    {"id": "SUP-T2-06", "name": "SiliconBase KR",    "country": "KR", "tier": 2, "reliability": 0.96, "status": "ok"},
]

# Tier-1 suppliers (three of them secretly depend on SUP-T2-01)
TIER1_CHOKE = [
    {"id": "SUP-01", "name": "ElecCore",    "country": "CN", "tier": 1, "reliability": 0.92, "status": "ok"},
    {"id": "SUP-02", "name": "ChipNation",  "country": "CN", "tier": 1, "reliability": 0.89, "status": "ok"},
    {"id": "SUP-03", "name": "PowerFlex",   "country": "CN", "tier": 1, "reliability": 0.94, "status": "ok"},
]

# Other tier-1 suppliers (healthy, diverse ports)
TIER1_OTHER = [
    {"id": "SUP-04", "name": "NanoChip DE",   "country": "DE", "tier": 1, "reliability": 0.96, "status": "ok"},
    {"id": "SUP-05", "name": "TechParts US",  "country": "US", "tier": 1, "reliability": 0.98, "status": "ok"},
    {"id": "SUP-06", "name": "KoreaTech",     "country": "KR", "tier": 1, "reliability": 0.97, "status": "ok"},
    {"id": "SUP-07", "name": "IndiaMicro",    "country": "IN", "tier": 1, "reliability": 0.91, "status": "ok"},
    {"id": "SUP-08", "name": "EuroElec",      "country": "NL", "tier": 1, "reliability": 0.95, "status": "ok"},
    {"id": "SUP-09", "name": "JapanFab",      "country": "JP", "tier": 1, "reliability": 0.99, "status": "ok"},
    {"id": "SUP-10", "name": "USACircuit",    "country": "US", "tier": 1, "reliability": 0.97, "status": "ok"},
    {"id": "SUP-11", "name": "TaiwanIC",      "country": "TW", "tier": 1, "reliability": 0.96, "status": "ok"},
    {"id": "SUP-12", "name": "BrazilBoard",   "country": "BR", "tier": 1, "reliability": 0.87, "status": "ok"},
    {"id": "SUP-13", "name": "MexicoMold",    "country": "MX", "tier": 1, "reliability": 0.89, "status": "ok"},
    {"id": "SUP-14", "name": "PolandParts",   "country": "PL", "tier": 1, "reliability": 0.93, "status": "ok"},
    {"id": "SUP-15", "name": "SingaLogic",    "country": "SG", "tier": 1, "reliability": 0.95, "status": "ok"},
    {"id": "SUP-16", "name": "IsraelSemi",    "country": "IL", "tier": 1, "reliability": 0.98, "status": "ok"},
    {"id": "SUP-17", "name": "AussieMine",    "country": "AU", "tier": 1, "reliability": 0.94, "status": "ok"},
    {"id": "SUP-18", "name": "CzechChip",     "country": "CZ", "tier": 1, "reliability": 0.92, "status": "ok"},
    {"id": "SUP-19", "name": "ThaiPlastic",   "country": "TH", "tier": 1, "reliability": 0.86, "status": "ok"},
    {"id": "SUP-20", "name": "MalayBoard",    "country": "MY", "tier": 1, "reliability": 0.90, "status": "ok"},
    {"id": "SUP-21", "name": "VietFlex",      "country": "VN", "tier": 1, "reliability": 0.88, "status": "ok"},
    {"id": "SUP-22", "name": "SwissPrec",     "country": "CH", "tier": 1, "reliability": 0.99, "status": "ok"},
    {"id": "SUP-23", "name": "SpainCast",     "country": "ES", "tier": 1, "reliability": 0.91, "status": "ok"},
    {"id": "SUP-24", "name": "ArgentinaAlu",  "country": "AR", "tier": 1, "reliability": 0.85, "status": "ok"},
]

ALL_SUPPLIERS = TIER2_SUPPLIERS + TIER1_CHOKE + TIER1_OTHER

# Parts: first 12 are the "critical" ones that ONLY come from the choke suppliers
PARTS_CRITICAL = [
    {"sku": "CAP-4700UF",  "name": "Electrolytic Capacitor 4700uF",  "category": "capacitor",   "lead_time_days": 21},
    {"sku": "CAP-1000UF",  "name": "Electrolytic Capacitor 1000uF",  "category": "capacitor",   "lead_time_days": 18},
    {"sku": "CAP-470UF",   "name": "Ceramic Capacitor 470uF",        "category": "capacitor",   "lead_time_days": 14},
    {"sku": "CAP-100UF",   "name": "Ceramic Capacitor 100uF",        "category": "capacitor",   "lead_time_days": 14},
    {"sku": "MCU-ARM-M4",  "name": "ARM Cortex-M4 MCU",             "category": "mcu",         "lead_time_days": 45},
    {"sku": "MCU-RISC-V",  "name": "RISC-V 32-bit MCU",             "category": "mcu",         "lead_time_days": 38},
    {"sku": "PWR-MOSFET",  "name": "Power MOSFET 100V",             "category": "power",       "lead_time_days": 28},
    {"sku": "PWR-IGBT",    "name": "IGBT 600V Module",              "category": "power",       "lead_time_days": 35},
    {"sku": "PWR-DCDC",    "name": "DC-DC Converter Module",        "category": "power",       "lead_time_days": 22},
    {"sku": "IC-WIFI-BT",  "name": "WiFi+BT Combo IC",             "category": "wireless",    "lead_time_days": 30},
    {"sku": "IC-FLASH",    "name": "NOR Flash 256MB",               "category": "memory",      "lead_time_days": 19},
    {"sku": "IC-DRAM",     "name": "LPDDR4 DRAM 4GB",              "category": "memory",      "lead_time_days": 26},
]

# Other parts with multiple supplier sources (not at risk)
PARTS_SAFE = [
    {"sku": "RES-100R",   "name": "Resistor 100 Ohm",              "category": "passive",     "lead_time_days": 7},
    {"sku": "RES-10K",    "name": "Resistor 10K Ohm",              "category": "passive",     "lead_time_days": 7},
    {"sku": "LED-RED",    "name": "Red LED 3mm",                   "category": "display",     "lead_time_days": 10},
    {"sku": "LED-BLUE",   "name": "Blue LED SMD",                  "category": "display",     "lead_time_days": 10},
    {"sku": "CONN-USB-C", "name": "USB-C Connector",               "category": "connector",   "lead_time_days": 12},
    {"sku": "CONN-RJ45",  "name": "RJ-45 Ethernet Jack",           "category": "connector",   "lead_time_days": 11},
    {"sku": "XTAL-8MHZ",  "name": "Crystal 8MHz",                  "category": "timing",      "lead_time_days": 16},
    {"sku": "XTAL-25MHZ", "name": "Crystal 25MHz",                 "category": "timing",      "lead_time_days": 16},
    {"sku": "SENS-TEMP",  "name": "Temperature Sensor I2C",        "category": "sensor",      "lead_time_days": 20},
    {"sku": "SENS-IMU",   "name": "6-Axis IMU Module",             "category": "sensor",      "lead_time_days": 24},
    {"sku": "DISP-OLED",  "name": "OLED Display 0.96\"",           "category": "display",     "lead_time_days": 25},
    {"sku": "ANT-PATCH",  "name": "Patch Antenna 2.4GHz",          "category": "antenna",     "lead_time_days": 14},
    # --- Additional safe parts ---
    {"sku": "CAP-SAFE-1", "name": "Tantalum Capacitor 10uF",       "category": "capacitor",   "lead_time_days": 15},
    {"sku": "IC-OPAMP",   "name": "Op-Amp Rail-to-Rail",           "category": "analog",      "lead_time_days": 12},
    {"sku": "IC-ADC-16",  "name": "16-bit ADC SPI",                "category": "analog",      "lead_time_days": 18},
    {"sku": "BATT-18650", "name": "Li-Ion Cell 18650",             "category": "energy",      "lead_time_days": 20},
    {"sku": "FUSE-SMD",   "name": "SMD Fuse 1A",                   "category": "protection",  "lead_time_days": 8},
    {"sku": "REG-LDO",    "name": "LDO Regulator 3.3V",            "category": "power",       "lead_time_days": 10},
    {"sku": "TRANS-ISO",  "name": "Isolation Transformer",         "category": "transformer", "lead_time_days": 30},
    {"sku": "COIL-10UH",  "name": "Power Inductor 10uH",          "category": "inductor",    "lead_time_days": 12},
    {"sku": "IC-ETH-PHY", "name": "Ethernet PHY Chip",             "category": "networking",  "lead_time_days": 22},
    {"sku": "RF-PA-2G",   "name": "RF Power Amplifier 2.4GHz",    "category": "rf",          "lead_time_days": 28},
    {"sku": "IC-GPS",     "name": "GPS Module u-blox",             "category": "sensor",      "lead_time_days": 35},
    {"sku": "IC-BLE-SOC", "name": "BLE SoC nRF52840",             "category": "wireless",    "lead_time_days": 32},
    {"sku": "CONN-HDMI",  "name": "HDMI Connector 2.0",           "category": "connector",   "lead_time_days": 14},
    {"sku": "IC-CAN-TX",  "name": "CAN Transceiver",               "category": "interface",   "lead_time_days": 16},
    {"sku": "IC-RS485",   "name": "RS-485 Transceiver",            "category": "interface",   "lead_time_days": 14},
    {"sku": "IC-SDCARD",  "name": "SD Card Controller",            "category": "storage",     "lead_time_days": 18},
    {"sku": "SEAL-IP67",  "name": "IP67 Gasket Set",               "category": "mechanical",  "lead_time_days": 22},
    {"sku": "PCB-4L-FR4", "name": "4-Layer PCB FR4",               "category": "substrate",   "lead_time_days": 40},
    {"sku": "HEAT-SINK",  "name": "Aluminium Heat Sink",           "category": "thermal",     "lead_time_days": 18},
    {"sku": "FAN-40MM",   "name": "40mm Cooling Fan",              "category": "thermal",     "lead_time_days": 15},
    {"sku": "ENC-PLAS",   "name": "ABS Plastic Enclosure",         "category": "mechanical",  "lead_time_days": 25},
    {"sku": "IC-EEPROM",  "name": "EEPROM 256Kbit",               "category": "memory",      "lead_time_days": 11},
    {"sku": "BUZZER-SMD", "name": "SMD Buzzer 3.3V",              "category": "audio",       "lead_time_days": 9},
    {"sku": "LED-RGB",    "name": "RGB LED SMD 5050",              "category": "display",     "lead_time_days": 11},
    {"sku": "SWITCH-TACT","name": "Tactile Pushbutton SMD",        "category": "input",       "lead_time_days": 8},
    {"sku": "RELAY-5V",   "name": "Relay Module 5V",              "category": "power",       "lead_time_days": 14},
    {"sku": "XFMR-PULSE", "name": "Pulse Transformer",            "category": "transformer", "lead_time_days": 20},
    {"sku": "CONN-DB9",   "name": "DB-9 Serial Connector",        "category": "connector",   "lead_time_days": 10},
    {"sku": "IC-LIN-TX",  "name": "LIN Transceiver",              "category": "interface",   "lead_time_days": 13},
    {"sku": "IC-USB-HUB", "name": "USB 3.0 Hub Controller",       "category": "interface",   "lead_time_days": 24},
    {"sku": "PCB-FPC",    "name": "Flexible PCB Connector",       "category": "connector",   "lead_time_days": 22},
    {"sku": "PWR-PMBUS",  "name": "PMBus Power Controller",       "category": "power",       "lead_time_days": 26},
    {"sku": "IC-PWRSAVE", "name": "Power Management IC",          "category": "power",       "lead_time_days": 19},
    {"sku": "IC-WDG",     "name": "Watchdog Timer IC",            "category": "logic",       "lead_time_days": 10},
    {"sku": "IC-ISOLATION","name":"Digital Isolator 4ch",         "category": "protection",  "lead_time_days": 17},
    {"sku": "IC-GAN-DRV", "name": "GaN Gate Driver",             "category": "power",       "lead_time_days": 33},
    {"sku": "IC-AFE",     "name": "Analog Front End IC",          "category": "analog",      "lead_time_days": 28},
    {"sku": "CAP-FILM",   "name": "Film Capacitor 10uF",          "category": "capacitor",   "lead_time_days": 16},
    {"sku": "COIL-1MH",   "name": "Common Mode Choke 1mH",       "category": "inductor",    "lead_time_days": 15},
    {"sku": "IC-THERM",   "name": "Thermal Management IC",       "category": "analog",      "lead_time_days": 21},
    {"sku": "SHIELD-EMI", "name": "EMI Shield Can",               "category": "mechanical",  "lead_time_days": 20},
]

ALL_PARTS = PARTS_CRITICAL + PARTS_SAFE

# Products built from those parts
PRODUCTS = [
    {"sku": "PROD-IOT-01",  "name": "IoT Edge Gateway Pro"},
    {"sku": "PROD-IOT-02",  "name": "Industrial Sensor Node"},
    {"sku": "PROD-EV-01",   "name": "EV Battery Management System"},
    {"sku": "PROD-EV-02",   "name": "EV Onboard Charger"},
    {"sku": "PROD-IND-01",  "name": "Industrial PLC Module"},
    {"sku": "PROD-IND-02",  "name": "Servo Drive Controller"},
    {"sku": "PROD-MED-01",  "name": "Medical Monitor Board"},
    {"sku": "PROD-NET-01",  "name": "Network Switch ASIC Board"},
    {"sku": "PROD-NET-02",  "name": "5G Small Cell RF Unit"},
    {"sku": "PROD-AUTO-01", "name": "ADAS Compute Module"},
]

CUSTOMERS = [
    "Acme Corp", "GlobalTech", "FutureMachines", "NovaDrive", "HorizonMed",
    "AlphaNet", "BetaLogic", "ConnectEU", "PrecisionDE", "ApexAU",
    "NeuraLink Systems", "Volt Industries", "MechaPro", "SkyWave Telecom", "OmegaElec",
]


# ── Seeder class ─────────────────────────────────────────────────────────────

class GraphSeeder:
    def __init__(self, host: str, port: int, graph_name: str):
        self.client = falkordb.FalkorDB(host=host, port=port)
        self.graph_name = graph_name
        self.graph = self.client.select_graph(graph_name)

    def wipe(self):
        try:
            self.client.connection.execute_command("GRAPH.DELETE", self.graph_name)
            print(f"  [wipe] deleted graph '{self.graph_name}'")
        except Exception:
            pass  # doesn't exist yet

    def run(self, query: str, params: dict = None):
        self.graph.query(query, params or {})

    def seed(self):
        print("Seeding nodes...")
        self._seed_ports()
        self._seed_factories()
        self._seed_suppliers()
        self._seed_parts()
        self._seed_products()

        print("Seeding edges...")
        self._seed_sub_supplies()      # tier-2 → tier-1 hidden dependencies
        self._seed_ships_via()         # supplier → port (choke suppliers ALL → PORT-01)
        self._seed_routes_to()         # port → factory
        self._seed_supplies_critical() # choke suppliers → critical parts
        self._seed_supplies_safe()     # diverse suppliers → safe parts
        self._seed_used_in()           # part → product
        self._seed_assembles()         # factory → product
        self._seed_orders()            # orders
        print("Done. Graph seeded successfully.")

    # ── Node seeders ─────────────────────────────────────────────────────────

    def _seed_ports(self):
        for p in PORTS:
            self.run(
                "CREATE (:Port {id: $id, name: $name, country: $country, status: $status})",
                p,
            )
        print(f"  created {len(PORTS)} ports")

    def _seed_factories(self):
        for f in FACTORIES:
            self.run(
                "CREATE (:Factory {id: $id, name: $name, region: $region})",
                f,
            )
        print(f"  created {len(FACTORIES)} factories")

    def _seed_suppliers(self):
        for s in ALL_SUPPLIERS:
            self.run(
                "CREATE (:Supplier {id:$id, name:$name, country:$country, "
                "tier:$tier, reliability:$reliability, status:$status})",
                s,
            )
        print(f"  created {len(ALL_SUPPLIERS)} suppliers")

    def _seed_parts(self):
        for p in ALL_PARTS:
            self.run(
                "CREATE (:Part {sku:$sku, name:$name, category:$category, "
                "lead_time_days:$lead_time_days})",
                p,
            )
        print(f"  created {len(ALL_PARTS)} parts")

    def _seed_products(self):
        for p in PRODUCTS:
            self.run("CREATE (:Product {sku:$sku, name:$name})", p)
        print(f"  created {len(PRODUCTS)} products")

    # ── Edge seeders ──────────────────────────────────────────────────────────

    def _seed_sub_supplies(self):
        """
        THE PLANTED SURPRISE:
        SUP-T2-01 (CapTech Asia) sub-supplies all three choke tier-1 suppliers.
        Other tier-2 suppliers sub-supply a few tier-1 non-choke suppliers.
        """
        # Planted hidden dependency
        for t1_id in ["SUP-01", "SUP-02", "SUP-03"]:
            self.run(
                "MATCH (t2:Supplier {id:'SUP-T2-01'}), (t1:Supplier {id:$t1}) "
                "CREATE (t2)-[:SUB_SUPPLIES]->(t1)",
                {"t1": t1_id},
            )

        # Other tier-2 → tier-1 relationships (less critical)
        pairs = [
            ("SUP-T2-02", "SUP-11"), ("SUP-T2-02", "SUP-06"),
            ("SUP-T2-03", "SUP-04"), ("SUP-T2-03", "SUP-08"),
            ("SUP-T2-04", "SUP-07"), ("SUP-T2-04", "SUP-19"),
            ("SUP-T2-05", "SUP-12"), ("SUP-T2-05", "SUP-24"),
            ("SUP-T2-06", "SUP-09"), ("SUP-T2-06", "SUP-16"),
        ]
        for t2_id, t1_id in pairs:
            self.run(
                "MATCH (t2:Supplier {id:$t2}), (t1:Supplier {id:$t1}) "
                "CREATE (t2)-[:SUB_SUPPLIES]->(t1)",
                {"t2": t2_id, "t1": t1_id},
            )
        print("  created SUB_SUPPLIES edges (planted surprise wired)")

    def _seed_ships_via(self):
        """
        Choke suppliers (SUP-01, 02, 03) ship ONLY through PORT-01 (Shanghai).
        Other suppliers use multiple ports.
        """
        # Planted choke: all three tier-1 choke suppliers only use Shanghai
        for sup_id in ["SUP-01", "SUP-02", "SUP-03"]:
            self.run(
                "MATCH (s:Supplier {id:$sid}), (p:Port {id:'PORT-01'}) "
                "CREATE (s)-[:SHIPS_VIA {transit_days:$td}]->(p)",
                {"sid": sup_id, "td": ri(3, 5)},
            )

        # Other suppliers: each gets 1-2 ports, never PORT-01 for the safe set
        other_ports = ["PORT-02", "PORT-03", "PORT-04", "PORT-05", "PORT-06"]
        for s in TIER1_OTHER:
            ports_used = rng.sample(other_ports, k=rng.randint(1, 2))
            for port_id in ports_used:
                self.run(
                    "MATCH (s:Supplier {id:$sid}), (p:Port {id:$pid}) "
                    "CREATE (s)-[:SHIPS_VIA {transit_days:$td}]->(p)",
                    {"sid": s["id"], "pid": port_id, "td": ri(2, 12)},
                )

        print("  created SHIPS_VIA edges (choke suppliers pinned to Shanghai)")

    def _seed_routes_to(self):
        """Port → Factory routes with cost and transit_days."""
        routes = [
            # Shanghai feeds US and APAC factories
            ("PORT-01", "FAC-01", 18, 450), ("PORT-01", "FAC-03", 5, 120),
            ("PORT-01", "FAC-04", 8, 200), ("PORT-01", "FAC-07", 6, 160),
            # Rotterdam feeds EU
            ("PORT-02", "FAC-02", 3, 80),  ("PORT-02", "FAC-06", 4, 100),
            ("PORT-02", "FAC-08", 12, 300),
            # Los Angeles feeds US
            ("PORT-03", "FAC-01", 4, 90),  ("PORT-03", "FAC-05", 5, 110),
            ("PORT-03", "FAC-08", 6, 140),
            # Singapore feeds APAC
            ("PORT-04", "FAC-03", 3, 70),  ("PORT-04", "FAC-04", 4, 95),
            ("PORT-04", "FAC-07", 2, 60),
            # Hamburg feeds EU
            ("PORT-05", "FAC-02", 2, 55),  ("PORT-05", "FAC-06", 3, 75),
            # Busan feeds APAC
            ("PORT-06", "FAC-03", 2, 65),  ("PORT-06", "FAC-07", 4, 100),
        ]
        for port_id, fac_id, transit, cost in routes:
            self.run(
                "MATCH (p:Port {id:$pid}), (f:Factory {id:$fid}) "
                "CREATE (p)-[:ROUTES_TO {transit_days:$td, cost:$cost, capacity:$cap}]->(f)",
                {"pid": port_id, "fid": fac_id, "td": transit, "cost": cost,
                 "cap": ri(800, 2000)},
            )
        print(f"  created {len(routes)} ROUTES_TO edges")

    def _seed_supplies_critical(self):
        """
        Critical parts are ONLY supplied by the three choke tier-1 suppliers.
        Each choke supplier owns a subset of the 12 critical parts.
        """
        assignments = {
            "SUP-01": ["CAP-4700UF", "CAP-1000UF", "CAP-470UF", "CAP-100UF"],
            "SUP-02": ["MCU-ARM-M4", "MCU-RISC-V", "IC-WIFI-BT", "IC-FLASH", "IC-DRAM"],
            "SUP-03": ["PWR-MOSFET", "PWR-IGBT", "PWR-DCDC"],
        }
        for sup_id, skus in assignments.items():
            for sku in skus:
                self.run(
                    "MATCH (s:Supplier {id:$sid}), (p:Part {sku:$sku}) "
                    "CREATE (s)-[:SUPPLIES {cost:$cost, lead_time_days:$ltd, "
                    "share:1.0, capacity:$cap}]->(p)",
                    {"sid": sup_id, "sku": sku,
                     "cost": r(50, 250), "ltd": ri(14, 45),
                     "cap": ri(200, 600)},
                )
        print("  created SUPPLIES edges for critical parts (single-source)")

    def _seed_supplies_safe(self):
        """Safe parts have 2–4 diverse suppliers."""
        other_sup_ids = [s["id"] for s in TIER1_OTHER]
        for part in PARTS_SAFE:
            suppliers = rng.sample(other_sup_ids, k=rng.randint(2, 4))
            shares = _split_shares(len(suppliers))
            for sup_id, share in zip(suppliers, shares):
                self.run(
                    "MATCH (s:Supplier {id:$sid}), (p:Part {sku:$sku}) "
                    "CREATE (s)-[:SUPPLIES {cost:$cost, lead_time_days:$ltd, "
                    "share:$share, capacity:$cap}]->(p)",
                    {"sid": sup_id, "sku": part["sku"],
                     "cost": r(5, 120), "ltd": ri(7, 30),
                     "share": share, "cap": ri(500, 3000)},
                )
        print(f"  created SUPPLIES edges for {len(PARTS_SAFE)} safe parts")

    def _seed_used_in(self):
        """
        Each product uses 3-6 safe parts + 1-3 critical parts (the planted trap).
        Products PROD-IOT-01..PROD-EV-02 use critical parts, rest use only safe.
        """
        critical_skus = [p["sku"] for p in PARTS_CRITICAL]
        safe_skus = [p["sku"] for p in PARTS_SAFE]

        # Products that use critical parts (these become at-risk)
        critical_products = PRODUCTS[:6]
        safe_products = PRODUCTS[6:]

        for prod in critical_products:
            # 1-3 critical parts
            crit = rng.sample(critical_skus, k=rng.randint(1, 3))
            safe = rng.sample(safe_skus, k=rng.randint(3, 5))
            for sku in crit + safe:
                self.run(
                    "MATCH (p:Part {sku:$sku}), (prod:Product {sku:$psku}) "
                    "CREATE (p)-[:USED_IN {qty:$qty}]->(prod)",
                    {"sku": sku, "psku": prod["sku"], "qty": ri(1, 8)},
                )

        for prod in safe_products:
            safe = rng.sample(safe_skus, k=rng.randint(4, 7))
            for sku in safe:
                self.run(
                    "MATCH (p:Part {sku:$sku}), (prod:Product {sku:$psku}) "
                    "CREATE (p)-[:USED_IN {qty:$qty}]->(prod)",
                    {"sku": sku, "psku": prod["sku"], "qty": ri(1, 6)},
                )
        print(f"  created USED_IN edges ({len(critical_products)} at-risk products)")

    def _seed_assembles(self):
        """Each factory assembles 1-4 products."""
        prod_skus = [p["sku"] for p in PRODUCTS]
        fac_ids = [f["id"] for f in FACTORIES]
        assigned = set()

        for i, prod_sku in enumerate(prod_skus):
            fac = fac_ids[i % len(fac_ids)]
            self.run(
                "MATCH (f:Factory {id:$fid}), (p:Product {sku:$psku}) "
                "CREATE (f)-[:ASSEMBLES]->(p)",
                {"fid": fac, "psku": prod_sku},
            )
            assigned.add(prod_sku)
        print(f"  created ASSEMBLES edges")

    def _seed_orders(self):
        """
        300 orders total. The first 14 are HIGH-priority orders containing
        at-risk products → these are the ones the demo shows going from 14 → 0.
        """
        at_risk_prod_skus = [p["sku"] for p in PRODUCTS[:6]]
        safe_prod_skus = [p["sku"] for p in PRODUCTS[6:]]

        order_idx = 1

        # 14 high-priority at-risk orders
        for i in range(14):
            oid = f"ORD-{order_idx:04d}"
            customer = rng.choice(CUSTOMERS)
            value = round(rng.uniform(50_000, 500_000), 2)
            due = rdate(rng.randint(7, 45))
            prod_sku = at_risk_prod_skus[i % len(at_risk_prod_skus)]
            fac_id = FACTORIES[i % len(FACTORIES)]["id"]
            self.run(
                "MATCH (prod:Product {sku:$psku}), (f:Factory {id:$fid}) "
                "CREATE (o:Order {id:$oid, customer:$cust, value:$val, "
                "due_date:$due, priority:'HIGH', status:'pending'}) "
                "CREATE (o)-[:CONTAINS]->(prod) "
                "CREATE (o)-[:FULFILLED_BY]->(f)",
                {"oid": oid, "cust": customer, "val": value,
                 "due": due, "psku": prod_sku, "fid": fac_id},
            )
            order_idx += 1

        # 36 medium-priority at-risk orders (partially exposed)
        for i in range(36):
            oid = f"ORD-{order_idx:04d}"
            customer = rng.choice(CUSTOMERS)
            value = round(rng.uniform(10_000, 100_000), 2)
            due = rdate(rng.randint(14, 90))
            prod_sku = at_risk_prod_skus[i % len(at_risk_prod_skus)]
            fac_id = FACTORIES[i % len(FACTORIES)]["id"]
            self.run(
                "MATCH (prod:Product {sku:$psku}), (f:Factory {id:$fid}) "
                "CREATE (o:Order {id:$oid, customer:$cust, value:$val, "
                "due_date:$due, priority:'MEDIUM', status:'pending'}) "
                "CREATE (o)-[:CONTAINS]->(prod) "
                "CREATE (o)-[:FULFILLED_BY]->(f)",
                {"oid": oid, "cust": customer, "val": value,
                 "due": due, "psku": prod_sku, "fid": fac_id},
            )
            order_idx += 1

        # 250 safe orders (not at risk)
        for i in range(250):
            oid = f"ORD-{order_idx:04d}"
            customer = rng.choice(CUSTOMERS)
            value = round(rng.uniform(5_000, 200_000), 2)
            due = rdate(rng.randint(21, 120))
            prod_sku = rng.choice(safe_prod_skus)
            fac_id = rng.choice(FACTORIES)["id"]
            priority = rng.choice(["LOW", "LOW", "MEDIUM"])
            self.run(
                "MATCH (prod:Product {sku:$psku}), (f:Factory {id:$fid}) "
                "CREATE (o:Order {id:$oid, customer:$cust, value:$val, "
                "due_date:$due, priority:$pri, status:'pending'}) "
                "CREATE (o)-[:CONTAINS]->(prod) "
                "CREATE (o)-[:FULFILLED_BY]->(f)",
                {"oid": oid, "cust": customer, "val": value,
                 "due": due, "psku": prod_sku, "fid": fac_id, "pri": priority},
            )
            order_idx += 1

        print(f"  created {order_idx - 1} orders (14 HIGH-priority at-risk)")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _split_shares(n: int) -> list[float]:
    """Split 1.0 into n random shares that sum to 1.0."""
    if n == 1:
        return [1.0]
    cuts = sorted(rng.random() for _ in range(n - 1))
    cuts = [0.0] + cuts + [1.0]
    return [round(cuts[i + 1] - cuts[i], 3) for i in range(n)]


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SupplyShock graph seeder")
    parser.add_argument("--host",  default="localhost")
    parser.add_argument("--port",  type=int, default=6379)
    parser.add_argument("--graph", default=GRAPH_NAME)
    parser.add_argument("--wipe",  action="store_true",
                        help="Delete existing graph before seeding")
    args = parser.parse_args()

    print(f"Connecting to FalkorDB at {args.host}:{args.port} ...")
    seeder = GraphSeeder(host=args.host, port=args.port, graph_name=args.graph)

    if args.wipe:
        seeder.wipe()

    seeder.seed()
    print(f"\nGraph '{args.graph}' is ready. Planted surprise:")
    print("  SUP-T2-01 -> SUP-01/02/03 -> 12 critical parts -> 6 products -> 14 HIGH orders")
    print("  All three choke suppliers ship exclusively through PORT-01 (Shanghai)")
    print("  Closing PORT-01 blocks all 14 HIGH-priority orders.")


if __name__ == "__main__":
    main()
