import hmac
import hashlib
import time
import requests

def validate_bybit_api_key(api_key, api_secret) -> bool:
    try:
        url = "https://api.bybit.com/v5/account/wallet-balance"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        params = {
            "accountType": "UNIFIED"
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        prehash = timestamp + api_key + recv_window + query_string
        signature = hmac.new(api_secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }

        response = requests.get(url, params=params, headers=headers)

        return response.status_code == 200 and response.json().get("retCode") == 0
    except Exception as e:
        print(f"❌ API validation error: {e}")
        return False
