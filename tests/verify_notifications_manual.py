import requests
import json
import sys

BASE_URL = "http://localhost:8001"

def test_get_notifications_page():
    print(f"Testing GET {BASE_URL}/notifications...")
    try:
        response = requests.get(f"{BASE_URL}/notifications")
        if response.status_code == 200:
            print("✅ Notifications page loaded successfully.")
        else:
            print(f"❌ Failed to load notifications page. Status: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error connecting to server: {e}")
        sys.exit(1)

def test_list_personas():
    print(f"Testing GET {BASE_URL}/personas...")
    try:
        response = requests.get(f"{BASE_URL}/personas")
        if response.status_code == 200:
            personas = response.json()
            if len(personas) > 0:
                print(f"✅ Retrieved {len(personas)} personas.")
                return personas[0]['id']
            else:
                print("❌ No personas returned.")
                sys.exit(1)
        else:
            print(f"❌ Failed to list personas. Status: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error listing personas: {e}")
        sys.exit(1)

def test_list_target_profiles():
    print(f"Testing GET {BASE_URL}/target-profiles...")
    try:
        response = requests.get(f"{BASE_URL}/target-profiles")
        if response.status_code == 200:
            profiles = response.json()
            if len(profiles) > 0:
                print(f"✅ Retrieved {len(profiles)} target profiles.")
                return profiles[0]['id']
            else:
                print("❌ No target profiles returned.")
                sys.exit(1)
        else:
            print(f"❌ Failed to list target profiles. Status: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error listing target profiles: {e}")
        sys.exit(1)

def test_proactive_chat(persona_id, target_profile_id):
    print(f"Testing POST {BASE_URL}/chat/proactive with persona='{persona_id}' and target='{target_profile_id}'...")
    payload = {
        "persona_id": persona_id,
        "target_profile_id": target_profile_id,
        "model_override": "gemini-3-flash-preview"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/chat/proactive", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Proactive chat response received.")
            print(f"   Model: {data['model']}")
            print(f"   Reply: {data['reply']}")
        else:
            print(f"⚠️ Proactive chat request returned {response.status_code}. Response: {response.text}")

    except Exception as e:
        print(f"❌ Error in proactive chat: {e}")

if __name__ == "__main__":
    test_get_notifications_page()
    pid = test_list_personas()
    tid = test_list_target_profiles()
    test_proactive_chat(pid, tid)
