"""Manual smoke test for attachment upload flow.

Pytest may still collect modules under ``scratch/``; to avoid failing CI, the
script only executes when launched directly from the command line.
"""

import json
import pathlib
import requests


BASE = "http://localhost:8000"
EMAIL = "guest@example.com"
NAME = "Guest"
README_PATH = pathlib.Path(__file__).resolve().parents[1] / "README.md"


def main() -> None:
    print("Requesting OTP for", EMAIL)
    resp = requests.post(f"{BASE}/auth/request-otp", json={"email": EMAIL})
    print(resp.status_code, resp.text)
    resp.raise_for_status()
    code = resp.json().get("code")
    print("OTP code:", code)

    verify = requests.post(
        f"{BASE}/auth/verify-otp",
        json={"email": EMAIL, "code": code, "name": NAME},
    )
    print("Verify status:", verify.status_code, verify.text)
    verify.raise_for_status()
    token = verify.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("Launching accelerator session...")
    launch = requests.post(
        f"{BASE}/accelerators/enhance-documentation/sessions", headers=headers
    )
    print(launch.status_code, launch.text)
    launch.raise_for_status()
    session = launch.json()["session"]["session_id"]
    print("Session ID:", session)

    with README_PATH.open("rb") as fh:
        files = [("files", ("README.md", fh, "text/markdown"))]
        upload = requests.post(
            f"{BASE}/accelerators/sessions/{session}/attachments",
            headers=headers,
            files=files,
        )
        print("Upload status:", upload.status_code)
        print("Upload response:", upload.text)
        upload.raise_for_status()

    print("Success")


if __name__ == "__main__":
    main()
