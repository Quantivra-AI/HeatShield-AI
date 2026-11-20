"""API workflow smoke tests. Run from backend: python -m unittest app.test_api_smoke -v"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# BioTwin's provider SDK is optional for these non-LLM API workflow tests.
if "groq" not in sys.modules:
    groq_stub = types.ModuleType("groq")
    class AsyncGroq:  # pragma: no cover - only imported by router setup
        def __init__(self, *args, **kwargs):
            pass
    groq_stub.AsyncGroq = AsyncGroq
    sys.modules["groq"] = groq_stub

from fastapi.testclient import TestClient
from app import main


class HeatShieldAPISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="heatshield-api-test-")
        main.DB_PATH = Path(cls.tmp.name) / "test.db"
        cls.client = TestClient(main.app)

    def setUp(self):
        if main.DB_PATH.exists():
            main.DB_PATH.unlink()
        main.init_db()
        with main.get_db() as db:
            db.execute(
                "INSERT INTO app_users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                ("admin@heatshield.ai", "Test Administrator", main._hash_password("ChangeMe123!"), "admin")
            )
        login = self.client.post("/api/auth/login", json={
            "email": "admin@heatshield.ai", "password": "ChangeMe123!"
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.client.headers.update({
            "Authorization": f"Bearer {login.json()['access_token']}"
        })
        response = self.client.post("/api/worksites", json={
            "name": "Test Worksite", "city": "Test City",
            "industry": "Construction", "worker_count": 1
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.worksite_id = response.json()["id"]
        response = self.client.post("/api/zones", json={
            "worksite_id": self.worksite_id, "name": "Outdoor zone",
            "activity_type": "heavy_work", "exposure_category": "high",
            "worker_capacity": 10
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.zone_id = response.json()["id"]
        response = self.client.post("/api/workers", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "worker_code": "TST-001", "role": "worker"
        })
        self.assertEqual(response.status_code, 201, response.text)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_researcher_cannot_create_worksite(self):
        with main.get_db() as db:
            db.execute(
                "INSERT INTO app_users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                ("researcher@heatshield.ai", "Research User", main._hash_password("ResearchPass123!"), "researcher")
            )
        login = self.client.post("/api/auth/login", json={
            "email": "researcher@heatshield.ai", "password": "ResearchPass123!"
        })
        self.assertEqual(login.status_code, 200, login.text)
        response = self.client.post(
            "/api/worksites",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            json={"name": "Blocked", "city": "Test", "industry": "Construction", "worker_count": 1}
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_inactive_user_token_is_rejected(self):
        with main.get_db() as db:
            cursor = db.execute(
                "INSERT INTO app_users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                ("inactive@heatshield.ai", "Inactive User", main._hash_password("InactivePass123!"), "supervisor")
            )
            user_id = cursor.lastrowid
        login = self.client.post("/api/auth/login", json={
            "email": "inactive@heatshield.ai", "password": "InactivePass123!"
        })
        self.assertEqual(login.status_code, 200, login.text)
        with main.get_db() as db:
            db.execute("UPDATE app_users SET active = 0 WHERE id = ?", (user_id,))
        response = self.client.get(
            "/api/worksites",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"}
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_read_only_roles_can_view_but_not_mutate_operational_records(self):
        for role in ("executive", "health_safety"):
            email = f"{role}@heatshield.ai"
            with main.get_db() as db:
                db.execute(
                    "INSERT INTO app_users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                    (email, f"{role.title()} User", main._hash_password("RolePass123!"), role)
                )
            login = self.client.post("/api/auth/login", json={
                "email": email, "password": "RolePass123!"
            })
            self.assertEqual(login.status_code, 200, login.text)
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            self.assertEqual(self.client.get("/api/worksites", headers=headers).status_code, 200)
            self.assertEqual(self.client.get("/api/workers", headers=headers).status_code, 200)
            denied = self.client.post(
                "/api/worksites",
                headers=headers,
                json={"name": "Blocked", "city": "Test", "industry": "Construction", "worker_count": 1}
            )
            self.assertEqual(denied.status_code, 403, denied.text)

    def test_city_catalog_includes_abu_dhabi_with_uae_timezone(self):
        response = self.client.get("/api/cities")
        self.assertEqual(response.status_code, 200, response.text)
        cities = {item["id"]: item for item in response.json()["cities"]}
        self.assertIn("abu_dhabi", cities)
        self.assertEqual(cities["abu_dhabi"]["timezone"], "Asia/Dubai")

    def test_health_and_dashboard(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        summary = self.client.get("/api/dashboard/summary").json()
        self.assertEqual(summary["registered_worker_count"], 1)
        self.assertIsNone(summary["latest_exposure_record"])

    def test_missing_exposure_is_unknown(self):
        result = self.client.get("/api/risk/assessment", params={"worksite_id": self.worksite_id}).json()
        self.assertEqual(result["results"][0]["risk_band"], "unknown")
        self.assertIsNone(result["results"][0]["risk_score"])

    def test_demo_simulation_is_excluded_from_worker_risk_score(self):
        with main.get_db() as db:
            db.execute(
                """INSERT INTO exposure_records
                (worksite_id, zone_id, worker_code, exposure_minutes, source, risk_level,
                 air_temperature_c, relative_humidity_pct, measured_wbgt_c)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.worksite_id, self.zone_id, "TST-001", 120, "demo_simulation",
                 "critical", 45, 90, None)
            )
        response = self.client.get("/api/risk/assessment", params={"worksite_id": self.worksite_id})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["results"][0]
        self.assertEqual(result["assessment_status"], "excluded_demo_data")
        self.assertEqual(result["risk_band"], "unknown")
        self.assertIsNone(result["risk_score"])

    def test_measured_wbgt_requires_on_site_sensor(self):
        payload = {
            "worksite_id": self.worksite_id, "worker_code": "TST-001",
            "exposure_minutes": 30, "source": "weather_estimate",
            "risk_level": "moderate", "air_temperature_c": 32,
            "measured_wbgt_c": 28.5
        }
        self.assertEqual(self.client.post("/api/exposure-records", json=payload).status_code, 400)
        payload["source"] = "onsite_sensor"
        self.assertEqual(self.client.post("/api/exposure-records", json=payload).status_code, 201)

    def test_intervention_workflow(self):
        response = self.client.post("/api/interventions", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "intervention_type": "rest_break", "reason": "Scheduled preventive rest",
            "affected_crew_count": 1, "status": "recommended"
        })
        self.assertEqual(response.status_code, 201)
        intervention_id = response.json()["id"]
        approved = self.client.patch(f"/api/interventions/{intervention_id}/status?status=approved")
        self.assertEqual(approved.status_code, 200)
        completed = self.client.patch(f"/api/interventions/{intervention_id}/status?status=completed")
        self.assertEqual(completed.status_code, 200)
        invalid = self.client.patch(f"/api/interventions/{intervention_id}/status?status=dismissed")
        self.assertEqual(invalid.status_code, 409)

    def test_mesh_queue_and_sync(self):
        response = self.client.post("/api/mesh/offline-alerts", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "worker_code": "TST-001", "alert_type": "heat_exposure",
            "severity": "high", "message": "Supervisor review required"
        })
        self.assertEqual(response.status_code, 201)
        pending = self.client.get("/api/mesh/offline-alerts", params={"worksite_id": self.worksite_id}).json()
        self.assertEqual(pending["pending_alerts"], 1)
        synced = self.client.post("/api/mesh/sync", params={"worksite_id": self.worksite_id}).json()
        self.assertEqual(synced["synced_count"], 1)
        after = self.client.get("/api/mesh/offline-alerts", params={"worksite_id": self.worksite_id}).json()
        self.assertEqual(after["pending_alerts"], 0)

    def test_worker_and_exposure_entry_workflow(self):
        workers = self.client.get("/api/workers", params={"worksite_id": self.worksite_id}).json()["workers"]
        self.assertEqual(len(workers), 1)
        created = self.client.post("/api/workers", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "worker_code": "TST-002", "role": "welder"
        })
        self.assertEqual(created.status_code, 201, created.text)
        duplicate = self.client.post("/api/workers", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "worker_code": "TST-002", "role": "welder"
        })
        self.assertEqual(duplicate.status_code, 409)
        exposure = self.client.post("/api/exposure-records", json={
            "worksite_id": self.worksite_id, "zone_id": self.zone_id,
            "worker_code": "TST-002", "exposure_minutes": 45,
            "source": "weather_estimate", "risk_level": "moderate",
            "air_temperature_c": 33.5, "relative_humidity_pct": 60
        })
        self.assertEqual(exposure.status_code, 201, exposure.text)
        records = self.client.get("/api/exposure-records", params={"worksite_id": self.worksite_id}).json()["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["worker_code"], "TST-002")

    
    def test_vitals_endpoint_runs_dataset_screening(self):
        worker = self.client.post("/api/workers", json={
            "worksite_id": self.worksite_id,
            "zone_id": self.zone_id,
            "worker_code": "ML-TEST-001",
            "role": "welder"
        })
        self.assertEqual(worker.status_code, 201, worker.text)

        response = self.client.post("/api/biotwin/vitals", json={
            "worksite_id": self.worksite_id,
            "worker_code": "ML-TEST-001",
            "temperature_type": "core",
            "body_temperature_c": 37.2,
            "heart_rate_bpm": 110,
            "respiratory_rate_bpm": 20,
            "spo2_pct": 98,
            "systolic_bp_mmhg": 120,
            "diastolic_bp_mmhg": 80,
            "weight_kg": 70,
            "height_m": 1.75,
            "symptoms": "",
            "source": "clinical_device"
        })

        self.assertEqual(response.status_code, 201, response.text)

        result = response.json()
        screening = result["dataset_vital_screening"]

        self.assertEqual(screening["status"], "generated")
        self.assertEqual(screening["label"], "High Risk")
        self.assertEqual(screening["label_code"], 1)
        self.assertFalse(screening["clinical_diagnosis"])


    def test_zone_cannot_be_assigned_across_worksites(self):
        other = self.client.post("/api/worksites", json={
            "name": "Other Worksite", "city": "Other City",
            "industry": "Logistics", "worker_count": 2
        }).json()
        response = self.client.post("/api/workers", json={
            "worksite_id": other["id"], "zone_id": self.zone_id,
            "worker_code": "BAD-001", "role": "worker"
        })
        self.assertEqual(response.status_code, 400)

    def test_vitals_endpoint_generates_ai_supervisor_explanation_when_provider_available(self):
        import asyncio
        from types import SimpleNamespace
        original_client = sys.modules["groq"].AsyncGroq
        original_key = os.environ.get("GROQ_API_KEY")
        class FakeGroq:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=self)
            async def create(self, **kwargs):
                message = SimpleNamespace(content=(
                    "Assessment\nPossible heat-related health concern.\n"
                    "Why this needs attention\nThe supplied readings and symptoms warrant review.\n"
                    "Supervisor action\nMove worker to a cool area and arrange medical assessment.\n"
                    "Limitations\nNot a diagnosis."
                ))
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        sys.modules["groq"].AsyncGroq = FakeGroq
        os.environ["GROQ_API_KEY"] = "test-key"
        try:
            response = self.client.post("/api/biotwin/vitals", json={
                "worksite_id": self.worksite_id, "worker_code": "TST-001",
                "body_temperature_c": 38.2, "temperature_type": "oral",
                "heart_rate_bpm": 124, "respiratory_rate_bpm": 22,
                "spo2_pct": 97, "systolic_bp_mmhg": 128, "diastolic_bp_mmhg": 82,
                "symptoms": "dizziness and heavy sweating", "source": "manual_demo"
            })
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["ai_status"], "generated")
            self.assertIn("Possible heat-related health concern", response.json()["ai_assessment"])
            self.assertEqual(response.json()["respiratory_rate_bpm"], 22)
            self.assertEqual(response.json()["systolic_bp_mmhg"], 128)
            listed = self.client.get("/api/biotwin/vitals", params={"worksite_id": self.worksite_id})
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertTrue(listed.json()["readings"][0]["ai_assessment"])
        finally:
            sys.modules["groq"].AsyncGroq = original_client
            if original_key is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original_key

    def test_alert_rejects_unknown_worker(self):
        response = self.client.post("/api/mesh/offline-alerts", json={
            "worksite_id": self.worksite_id, "worker_code": "GHOST-9",
            "alert_type": "heat_exposure", "severity": "high",
            "message": "This should be rejected"
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
