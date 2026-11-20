
import getpass
import sys
import httpx

BASE_URL = "http://localhost:8000"
WORKSITE_ID = 2

passed = 0
failed = 0
warnings = 0


def report(name, success, detail=""):
    global passed, failed
    if success:
        passed += 1
        print(f"[PASS] {name} {detail}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


def warn(name, detail):
    global warnings
    warnings += 1
    print(f"[WARN] {name} {detail}")


def main():
    global passed, failed, warnings

    print("\n===================================")
    print("       HEATSHIELD API CHECK")
    print("===================================\n")

    email = input("Admin email [admin@heatshield.ai]: ").strip()
    if not email:
        email = "admin@heatshield.ai"

    password = getpass.getpass("Admin password: ")

    with httpx.Client(base_url=BASE_URL, timeout=20) as client:

        # 1. Backend health
        try:
            r = client.get("/api/health")
            report("Backend health", r.status_code == 200)
        except Exception as e:
            report("Backend connection", False, str(e))
            return

        # 2. Login
        try:
            r = client.post(
                "/api/auth/login",
                json={"email": email, "password": password}
            )
            if r.status_code != 200:
                report("Admin login", False, f"HTTP {r.status_code}: {r.text}")
                return

            token = r.json().get("access_token")
            if not token:
                report("Login token", False, "Token missing")
                return

            client.headers["Authorization"] = f"Bearer {token}"
            report("Admin login", True)

        except Exception as e:
            report("Admin login", False, str(e))
            return

        # Helper: authenticated GET
        def get(path, params=None):
            response = client.get(path, params=params)
            if response.status_code != 200:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )
            return response.json()

        # 3. Authentication check
        try:
            me = get("/api/auth/me")
            report("Authenticated session", bool(me.get("email")))
        except Exception as e:
            report("Authenticated session", False, str(e))

        # 4. Worksite
        try:
            data = get("/api/worksites")
            sites = data.get("worksites", [])
            site = next(
                (s for s in sites if s.get("id") == WORKSITE_ID),
                None
            )
            report("Abu Dhabi pilot worksite", site is not None)
        except Exception as e:
            site = None
            report("Worksite API", False, str(e))

        # 5. Zones
        try:
            data = get("/api/zones", {"worksite_id": WORKSITE_ID})
            zones = data.get("zones", [])
            report("Zones API", len(zones) == 2, f"({len(zones)} found)")
        except Exception as e:
            report("Zones API", False, str(e))

        # 6. Workers
        try:
            data = get("/api/workers", {"worksite_id": WORKSITE_ID})
            workers = data.get("workers", [])
            active = sum(1 for w in workers if w.get("active") == 1)
            report("Workers API", active == 6, f"({active} active)")
        except Exception as e:
            report("Workers API", False, str(e))

        # 7. Exposure records
        try:
            data = get(
                "/api/exposure-records",
                {"worksite_id": WORKSITE_ID, "limit": 100}
            )
            records = data.get("records", [])
            simulated = sum(
                1 for x in records
                if x.get("source") == "demo_simulation"
            )
            report(
                "Exposure API",
                len(records) == 6 and simulated == 6,
                f"({len(records)} records, {simulated} simulated)"
            )
        except Exception as e:
            report("Exposure API", False, str(e))

        # 8. Interventions
        try:
            data = get(
                "/api/interventions",
                {"worksite_id": WORKSITE_ID}
            )
            interventions = data.get("interventions", [])
            pending = sum(
                1 for x in interventions
                if x.get("status") == "recommended"
            )
            report(
                "Interventions API",
                len(interventions) == 2 and pending == 2,
                f"({len(interventions)} total, {pending} pending)"
            )
        except Exception as e:
            report("Interventions API", False, str(e))

        # 9. Dashboard
        try:
            data = get("/api/dashboard/summary")
            report(
                "Dashboard summary",
                "registered_worker_count" in data
                and "pending_intervention_count" in data
            )
            print(
                "     Dashboard:",
                "workers =", data.get("registered_worker_count"),
                "| zones =", data.get("zone_count"),
                "| pending =", data.get("pending_intervention_count")
            )
        except Exception as e:
            report("Dashboard summary", False, str(e))

        # 10. Risk assessment
        try:
            data = get(
                "/api/risk/assessment",
                {"worksite_id": WORKSITE_ID}
            )
            results = data.get("results", [])
            excluded = sum(
                1 for x in results
                if x.get("assessment_status") == "excluded_demo_data"
            )
            report(
                "Risk assessment simulation exclusion",
                len(results) == 6 and excluded == 6,
                f"({excluded}/6 excluded from assessment)"
            )
        except Exception as e:
            report("Risk assessment", False, str(e))

        # 11. BioShield Mesh
        try:
            data = get(
                "/api/mesh/status",
                {"worksite_id": WORKSITE_ID}
            )
            simulated = data.get("simulated_workers", 0)
            connected = data.get("connected_workers", 0)
            report(
                "BioShield Mesh simulation status",
                simulated == 6 and connected == 0,
                f"({simulated} simulated, {connected} connected)"
            )
        except Exception as e:
            report("BioShield Mesh", False, str(e))

        # 12. Shift rotation safety review
        try:
            data = get(
                "/api/optimization/shift-rotation",
                {"worksite_id": WORKSITE_ID}
            )
            recommendations = data.get("recommendations", [])
            if recommendations:
                warn(
                    "Shift rotation",
                    f"{len(recommendations)} recommendations generated "
                    "from data that includes simulations. Review before use."
                )
            else:
                report(
                    "Shift rotation API",
                    True,
                    "(No recommendations generated)"
                )
        except Exception as e:
            report("Shift rotation API", False, str(e))

        # 13. Offline alerts
        try:
            data = get(
                "/api/mesh/offline-alerts",
                {"worksite_id": WORKSITE_ID}
            )
            report(
                "Offline alerts API",
                "alerts" in data and "pending_alerts" in data
            )
        except Exception as e:
            report("Offline alerts API", False, str(e))

        # 14. BioTwin research registry
        try:
            data = get("/api/biotwin/research-catalog")
            report(
                "BioTwin research catalog",
                data.get("module") == "BioTwin"
                and "datasets" in data
            )
        except Exception as e:
            report("BioTwin research catalog", False, str(e))

        # 15. Cities
        try:
            data = get("/api/cities")
            report("Cities API", "cities" in data)
        except Exception as e:
            report("Cities API", False, str(e))

    print("\n===================================")
    print("           FINAL REPORT")
    print("===================================")
    print(f"PASSED:   {passed}")
    print(f"FAILED:   {failed}")
    print(f"WARNINGS: {warnings}")
    print("===================================")

    if failed:
        print("RESULT: REVIEW FAILED CHECKS")
    elif warnings:
        print("RESULT: API CHECKS PASSED WITH SAFETY WARNINGS")
    else:
        print("RESULT: ALL CHECKS PASSED")

    print("\nNo database records were created, updated or deleted.")


if __name__ == "__main__":
    main()
