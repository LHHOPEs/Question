import os
import requests

# 🧠 Lấy token và chat_id từ GitHub Secrets (đã cài trong Settings > Secrets)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

url = "https://testnet.api.euclidprotocol.com/api/v1/routes?limit=10"
payload = {
    "external": True,
    "token_in": "mon",
    "token_out": "phrs",
    "amount_in": str(10**18),  # 1 MON
    "chain_uids": []
}

try:
    # Gọi API để lấy tỷ giá
    res = requests.post(url, json=payload)
    data = res.json()

    amount_in = int(payload["amount_in"])
    amount_out = int(data["paths"][0]["path"][0]["amount_out"])
    rate = amount_out / amount_in

    msg = f"1 MON ≈ {rate:.6f} PHRS"

    # Gửi tin nhắn sang Telegram
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

    print("Đã gửi:", msg)

except Exception as e:
    print("Lỗi:", e)
