
import httpx
import getpass

BASE_URL = "http://localhost:8000"

email = input("Admin email [admin@heatshield.ai]: ").strip()
if not email:
    email = "admin@heatshield.ai"

password = getpass.getpass("Admin password: ")

with httpx.Client(base_url=BASE_URL, timeout=20) as client:

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password}
    )
    login.raise_for_status()

    token = login.json()["access_token"]

    response = client.get(
        "/api/optimization/shift-rotation",
        params={"worksite_id": 2},
        headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()

    data = response.json()

    print("\n===== SHIFT ROTATION SAFETY CHECK =====")
    print("Eligible workers:", data.get("eligible_workers"))
    print("Excluded simulated:", data.get("excluded_simulated_workers"))
    print("Recommendations:", data.get("recommendations_generated"))

    passed = (
        data.get("excluded_simulated_workers") == 6
        and data.get("recommendations_generated") == 0
    )

    print("\nRESULT:", "PASS" if passed else "CHECK REQUIRED")
