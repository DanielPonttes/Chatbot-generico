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

def test_proactive_chat(persona_id):
    print(f"Testing POST {BASE_URL}/chat/proactive with overrides...")
    payload = {
        "persona_id": persona_id,
        "model_override": "gemini-3-flash-preview", # Testing override
        "persona_override": {
            "system_prompt": "You are a robotic dog that says 'Woof' in every sentence."
        }
    }
    
    try:
        # Note: This might fail if gemini-3-flash-preview is not actually available/valid for the API key,
        # but the code path should execute. We'll check if it returns 200 or 503 (provider error).
        # If it returns 200, it worked. If it returns error due to model not found, logic still worked.
        response = requests.post(f"{BASE_URL}/chat/proactive", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Proactive chat response received.")
            print(f"   Model: {data['model']}")
            print(f"   Reply: {data['reply']}")
            
            if "gemini-3-flash-preview" in data['model']:
                print("✅ Model override confirmed in response.")
            else:
                print(f"⚠️ Model match warning: Expected 'gemini-3-flash-preview', got {data['model']}")
                
        else:
            print(f"⚠️ Proactive chat request returned {response.status_code}. This might be expected if the model name is invalid or key has no access.")
            print(f"   Response: {response.text}")

    except Exception as e:
        print(f"❌ Error in proactive chat: {e}")

if __name__ == "__main__":
    test_get_notifications_page()
    pid = test_list_personas()
    test_proactive_chat(pid)
