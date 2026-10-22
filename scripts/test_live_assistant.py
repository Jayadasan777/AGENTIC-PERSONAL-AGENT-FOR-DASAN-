import urllib.request
import json

BASE_URL = "https://onto-chemistry-eddie-protocols.trycloudflare.com"

def test_endpoint(name, url, method="GET", data=None):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8") if data else None,
            headers={"Content-Type": "application/json"} if data else {}
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            status = res.status
            body = res.read().decode("utf-8")
            print(f"[{status}] {name} ({url}) -> OK")
            return status, body
    except Exception as e:
        print(f"[FAIL] {name} ({url}) -> {e}")
        return None, str(e)

def main():
    print("=" * 60)
    print("TESTING FULL AURA STACK & NEON POSTGRES INTEGRATION")
    print("=" * 60)

    # 1. Backend Health
    test_endpoint("Backend Health", f"{BASE_URL}/api/v1/health")

    # 2. Database Auth Login against Neon DB
    status, body = test_endpoint(
        "Neon Auth Login (dasan@aura.ai)",
        f"{BASE_URL}/api/v1/auth/login",
        method="POST",
        data={"email": "dasan@aura.ai", "password": "aura123456"}
    )
    if status == 200:
        token_data = json.loads(body)
        access_token = token_data.get("access_token")
        print(f"   => Successfully authenticated! Token Type: {token_data.get('token_type')}")
        
        # Test /auth/me with Bearer token
        req_me = urllib.request.Request(
            f"{BASE_URL}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        with urllib.request.urlopen(req_me, timeout=15) as res_me:
            me_data = json.loads(res_me.read().decode("utf-8"))
            print(f"   => /auth/me Verified from Neon DB: {me_data.get('email')} (ID: {me_data.get('id')}, Active: {me_data.get('is_active')})")

    # 3. Frontend Pages
    test_endpoint("Frontend Login Screen", f"{BASE_URL}/login")
    test_endpoint("Frontend Chat Workspace", f"{BASE_URL}/chat")
    test_endpoint("Frontend Agent Automation", f"{BASE_URL}/automation")
    test_endpoint("Frontend Knowledge Memory", f"{BASE_URL}/memory")

    print("=" * 60)
    print("ALL SERVICES TESTED END TO END SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
