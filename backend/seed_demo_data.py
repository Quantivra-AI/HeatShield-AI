import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
DB = ROOT / "heatshield.db"

if not DB.exists():
    raise SystemExit(f"Database not found: {DB}")

# Protect the existing database before making changes.
backup = DB.with_name(f"heatshield_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
shutil.copy2(DB, backup)
print(f"Backup created: {backup.name}")

conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = ON")

try:
    # Prevent duplicate demo records on repeated runs.
    existing = conn.execute(
        "SELECT id FROM worksites WHERE name = 'DEMO - Islamabad Construction Site'"
    ).fetchone()

    if existing:
        raise SystemExit("Demo dataset already exists. No records inserted.")

    now = datetime.now()
    stamp = lambda days=0: (now - timedelta(days=days)).isoformat(timespec="seconds")

    with conn:
        # 2 demo worksites
        sites = [
            ("DEMO - Islamabad Construction Site", "Islamabad", "Construction", 3),
            ("DEMO - Abu Dhabi Industrial Pilot", "Abu Dhabi", "Industrial", 3),
        ]
        site_ids = []
        for row in sites:
            cur = conn.execute(
                "INSERT INTO worksites (name, city, industry, worker_count) VALUES (?,?,?,?)",
                row
            )
            site_ids.append(cur.lastrowid)

        s1, s2 = site_ids

        # 4 zones
        zone_data = [
            (s1, "Outdoor Concrete Work", "heavy_outdoor_work", "high", 20),
            (s1, "Material Handling", "manual_handling", "moderate", 15),
            (s2, "Production Floor", "industrial_operations", "high", 25),
            (s2, "Loading and Dispatch", "loading", "moderate", 12),
        ]
        zone_ids = []
        for row in zone_data:
            cur = conn.execute(
                """INSERT INTO zones
                (worksite_id,name,activity_type,exposure_category,worker_capacity)
                VALUES (?,?,?,?,?)""", row
            )
            zone_ids.append(cur.lastrowid)

        z1, z2, z3, z4 = zone_ids

        # 6 synthetic workers
        workers = [
            (s1,z1,"DEMO-W001","Concrete Worker"),
            (s1,z1,"DEMO-W002","Site Supervisor"),
            (s1,z2,"DEMO-W003","Material Handler"),
            (s2,z3,"DEMO-W004","Production Operator"),
            (s2,z3,"DEMO-W005","Maintenance Worker"),
            (s2,z4,"DEMO-W006","Loading Assistant"),
        ]
        for row in workers:
            conn.execute(
                """INSERT INTO workers
                (worksite_id,zone_id,worker_code,role,active)
                VALUES (?,?,?,?,1)""", row
            )

        # Synthetic exposure history across both sites
        exposure_data = [
            (s1,z1,"DEMO-W001",150,"onsite_sensor","critical",39.5,62,31.2,"SYNTHETIC DEMO"),
            (s1,z1,"DEMO-W002",120,"weather_estimate","high",37.8,58,29.4,"SYNTHETIC DEMO"),
            (s1,z2,"DEMO-W003",90,"onsite_sensor","moderate",34.2,55,27.1,"SYNTHETIC DEMO"),
            (s1,z1,"DEMO-W001",110,"weather_estimate","high",38.1,60,30.1,"SYNTHETIC DEMO"),
            (s1,z2,"DEMO-W003",75,"onsite_sensor","low",31.5,48,24.8,"SYNTHETIC DEMO"),
            (s2,z3,"DEMO-W004",160,"onsite_sensor","critical",40.1,65,32.0,"SYNTHETIC DEMO"),
            (s2,z3,"DEMO-W005",100,"weather_estimate","high",37.2,57,28.8,"SYNTHETIC DEMO"),
            (s2,z4,"DEMO-W006",80,"onsite_sensor","moderate",34.8,52,26.5,"SYNTHETIC DEMO"),
            (s2,z3,"DEMO-W004",130,"weather_estimate","high",38.6,61,30.5,"SYNTHETIC DEMO"),
            (s2,z4,"DEMO-W006",60,"onsite_sensor","low",30.9,45,23.9,"SYNTHETIC DEMO"),
            (s1,z1,None,180,"weather_estimate","critical",40.0,68,32.5,"SYNTHETIC SITE-LEVEL DEMO"),
            (s2,z3,None,140,"weather_estimate","high",38.4,63,30.2,"SYNTHETIC SITE-LEVEL DEMO"),
        ]
        for i, row in enumerate(exposure_data):
            cur = conn.execute(
                """INSERT INTO exposure_records
                (worksite_id,zone_id,worker_code,exposure_minutes,source,
                 risk_level,air_temperature_c,relative_humidity_pct,
                 measured_wbgt_c,notes,recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (*row, stamp(i % 6))
            )

        # Synthetic vulnerability profiles - not real health records
        profiles = [
            (s1,"DEMO-W001","Heat sensitivity demo","heat_vulnerability"),
            (s1,"DEMO-W002","Hydration monitoring demo","hydration"),
            (s1,"DEMO-W003","Routine monitoring demo","general"),
            (s2,"DEMO-W004","Heat exposure monitoring demo","heat_vulnerability"),
            (s2,"DEMO-W005","Fatigue monitoring demo","fatigue"),
            (s2,"DEMO-W006","Routine monitoring demo","general"),
        ]
        for row in profiles:
            conn.execute(
                """INSERT INTO worker_health_demo_profiles
                (worksite_id,worker_code,profile_label,vulnerability_domain,demo_note)
                VALUES (?,?,?,?,?)""",
                (*row, "SYNTHETIC DEMO PROFILE - NOT A REAL WORKER OR DIAGNOSIS")
            )

        # Six synthetic vitals readings.
        # These are demonstration inputs, not real measurements.
        vitals = [
            (s1,"DEMO-W001",37.2,"core",104,22,97,126,82,78,1.75,"Synthetic demo reading","review"),
            (s1,"DEMO-W002",37.0,"core",82,17,98,120,78,72,1.72,"Synthetic demo reading","review"),
            (s1,"DEMO-W003",37.1,"core",88,19,97,118,76,65,1.68,"Synthetic demo reading","review"),
            (s2,"DEMO-W004",38.1,"core",132,25,94,138,88,82,1.78,"Synthetic demo reading","urgent"),
            (s2,"DEMO-W005",37.4,"core",101,21,96,128,84,75,1.73,"Synthetic demo reading","review"),
            (s2,"DEMO-W006",36.9,"core",79,16,99,116,74,68,1.70,"Synthetic demo reading","review"),
        ]
        for i, v in enumerate(vitals):
            (site,code,temp,temp_type,hr,rr,spo2,sysbp,diabp,weight,height,symptoms,level) = v
            bmi = weight / (height * height)
            reasons = "SYNTHETIC DEMO - supervisor review only"
            if level == "urgent":
                reasons = "SYNTHETIC DEMO - elevated example values; not a real emergency"
            conn.execute(
                """INSERT INTO worker_vitals_readings
                (worksite_id,worker_code,body_temperature_c,temperature_type,
                 heart_rate_bpm,respiratory_rate_bpm,spo2_pct,systolic_bp_mmhg,
                 diastolic_bp_mmhg,weight_kg,height_m,symptoms,source,
                 alert_level,alert_reason,ai_assessment,ai_status,ai_model,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (site,code,temp,temp_type,hr,rr,spo2,sysbp,diabp,weight,height,
                 symptoms,"manual_demo",level,reasons,
                 "Synthetic demonstration record. Verify all readings; not a clinical assessment.",
                 "demo_synthetic","synthetic_demo",stamp(i % 3))
            )

        # Recommended and completed interventions
        interventions = [
            (s1,z1,"hydration_reminder","SYNTHETIC DEMO: scheduled hydration reminder","recommended",3),
            (s1,z1,"rest_break","SYNTHETIC DEMO: example rest and shade break","approved",2),
            (s2,z3,"task_rotation","SYNTHETIC DEMO: rotate high-exposure tasks","recommended",3),
            (s2,z4,"shade_transition","SYNTHETIC DEMO: move break area to shade","completed",1),
        ]
        for row in interventions:
            conn.execute(
                """INSERT INTO interventions
                (worksite_id,zone_id,intervention_type,reason,status,affected_crew_count)
                VALUES (?,?,?,?,?,?)""", row
            )

        # Offline queue examples for mesh/sync demonstration
        alerts = [
            (s1,z1,"DEMO-W001","heat_exposure","high","SYNTHETIC DEMO: offline heat exposure alert","pending"),
            (s2,z3,"DEMO-W004","vitals_review","urgent","SYNTHETIC DEMO: offline vitals review alert","pending"),
            (s1,z2,"DEMO-W003","hydration","moderate","SYNTHETIC DEMO: offline hydration reminder","synced"),
        ]
        for row in alerts:
            conn.execute(
                """INSERT INTO offline_alert_queue
                (worksite_id,zone_id,worker_code,alert_type,severity,message,sync_status)
                VALUES (?,?,?,?,?,?,?)""", row
            )

    print("\nDEMO DATA INSERTED SUCCESSFULLY")
    for table in (
        "worksites","zones","workers","exposure_records",
        "worker_health_demo_profiles","worker_vitals_readings",
        "interventions","offline_alert_queue"
    ):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count}")

except Exception:
    conn.rollback()
    raise
finally:
    conn.close()

