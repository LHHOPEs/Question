import requests
import time

BOT_TOKEN = "8171774258:AAHsjYpqgCz3NTWbLmDLf6Sl2FrTtb3jJKo"
CHAT_ID = 5035183371  # CHAT_ID bạn vừa lấy được

url = "https://testnet.api.euclidprotocol.com/api/v1/routes?limit=10"
payload = {
    "external": True,
    "token_in": "mon",
    "token_out": "phrs",
    "amount_in": str(10**18),  # 1 MON
    "chain_uids": []
}

while True:
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

    # Đợi 5 phút rồi lặp lại
    time.sleep(300)
