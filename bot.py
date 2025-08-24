from web3 import Web3
from eth_utils import to_hex
from eth_account import Account
from fake_useragent import FakeUserAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading, requests, random, time, os

RPC_URL = "https://testnet.rpc.intuition.systems/http"
EXPLORER = "https://testnet.explorer.intuition.systems/tx/"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

Account.enable_unaudited_hdwallet_features()

print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

def load_proxies(file_path="proxy.txt"):
    proxies = []
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                proxy = line.strip()
                if proxy:
                    proxies.append(proxy)
    return proxies

def load_wallets(file_path="wallets.txt"):
    wallets = []
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                wallet = line.strip()
                if wallet and wallet.startswith("0x") and len(wallet) == 42:
                    wallets.append(wallet)
                elif wallet and not wallet.startswith("#"):
                    safe_print(f"⚠️  Invalid wallet address format: {wallet}")
    else:
        safe_print(f"❌ File {file_path} not found!")
        return []
    
    safe_print(f"📋 Loaded {len(wallets)} destination wallets")
    return wallets

def get_random_wallet(wallets):
    if not wallets:
        safe_print("❌ No wallets available!")
        return None
    return random.choice(wallets)

def get_random_proxy(proxies):
    if not proxies:
        return None
    proxy = random.choice(proxies)
    return {"http": proxy, "https": proxy}

def generate_evm_wallet():
    private_key = os.urandom(32).hex()
    acct = Account.from_key(bytes.fromhex(private_key))
    return private_key, acct.address

def parse_faucet_response(resp_json: list):
    try:
        if isinstance(resp_json, list) and len(resp_json) > 0:
            item = resp_json[0]
            if "result" in item:
                data = item["result"].get("data", {}).get("json", {})
                if data.get("success") is True:
                    return {"type": "success", "tx": data.get("transactionHash")}
                else:
                    return {"type": "fail", "message": data.get("message", "Unknown error")}
            elif "error" in item:
                err = item["error"].get("json", {}) or {}
                msg = err.get("message", "Unknown error")
                code = err.get("data", {}).get("httpStatus") or err.get("code")
                return {"type": "error", "message": msg, "code": code}
    except Exception:
        pass
    return {"type": "invalid", "raw": resp_json}

def request_faucet(address, proxies, job_id, total_jobs, retries=5, delay=3):
    url = "https://testnet.hub.intuition.systems/api/trpc/faucet.requestFaucetFunds?batch=1"
    payload = {
        "0": {
            "json": {
                "rollupSubdomain": "intuition-testnet",
                "recipientAddress": address,
                "turnstileToken": "",
                "tokenRollupAddress": None
            },
            "meta": {
                "values": {
                    "tokenRollupAddress": ["undefined"]
                }
            }
        }
    }

    ua = FakeUserAgent()
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Origin": "https://testnet.hub.intuition.systems",
        "Referer": "https://testnet.hub.intuition.systems/",
        "User-Agent": ua.random
    }

    for attempt in range(1, retries + 1):
        proxy = get_random_proxy(proxies)
        try:
            response = requests.post(
                url, json=payload, headers=headers, proxies=proxy, timeout=30
            )

            try:
                resp_json = response.json()
            except ValueError:
                safe_print(f"[Job {job_id:2d}/{total_jobs}] ⚠️  Attempt {attempt}: Not JSON Response")
                resp_json = None

            if resp_json is not None:
                parsed = parse_faucet_response(resp_json)

                if parsed["type"] == "success":
                    return {"success": True, "transactionHash": parsed["tx"]}

                elif parsed["type"] == "fail":
                    msg = parsed.get("message", "Unknown error (no message)")
                    safe_print(f"[Job {job_id:2d}/{total_jobs}] ⚠️  Attempt {attempt}: Faucet failed → {msg}")

                elif parsed["type"] == "error":
                    msg = parsed.get("message", "Unknown error")
                    code = parsed.get("code")

                    if code == 429:
                        return {"success": False, "message": f"Rate limited: {msg}"}
                    
                    safe_print(f"[Job {job_id:2d}/{total_jobs}] ⛔ Attempt {attempt}: Server error → {msg} (code={code})")
                else:
                    safe_print(f"[Job {job_id:2d}/{total_jobs}] ⚠️  Attempt {attempt}: Invalid Response")

            else:
                safe_print(f"[Job {job_id:2d}/{total_jobs}] ⚠️  Attempt {attempt}: Empty or Invalid JSON")

        except requests.RequestException as e:
            safe_print(f"[Job {job_id:2d}/{total_jobs}] ⚠️  Attempt {attempt}: Network error → {str(e)[:50]}...")

        if attempt < retries:
            safe_print(f"[Job {job_id:2d}/{total_jobs}] ⏳ Retrying in {delay} seconds...")
            time.sleep(delay)

    return {"success": False, "message": f"Failed after {retries} retries"}

def get_balance(address):
    balance_wei = w3.eth.get_balance(address)
    return w3.from_wei(balance_wei, "ether")

def send_all_balance(private_key, from_address, to_address, job_id=0, total_jobs=0, max_retries=5):
    job_prefix = f"[Job {job_id:2d}/{total_jobs}]" if job_id > 0 else ""
    
    for attempt in range(1, max_retries + 1):
        try:
            balance = w3.eth.get_balance(from_address)
            if balance == 0:
                return {"success": False, "message": "Balance 0"}

            gas_price = w3.eth.gas_price
            gas_limit = 21000
            fee = gas_price * gas_limit
            tx_value = balance - fee

            if tx_value <= 0:
                return {"success": False, "message": "Insufficient funds for gas"}

            nonce = w3.eth.get_transaction_count(from_address, 'pending')
            
            tx = {
                "nonce": nonce,
                "to": w3.to_checksum_address(to_address),
                "value": tx_value,
                "gas": gas_limit,
                "gasPrice": gas_price,
                "chainId": w3.eth.chain_id,
            }

            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            raw_tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = to_hex(raw_tx_hash)

            time.sleep(2)
            
            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
                if receipt and receipt['status'] == 1:
                    return {"success": True, "tx_hash": tx_hash, "receipt": receipt}
                else:
                    safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Transaction failed (status=0)")
                    
            except Exception as receipt_error:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Receipt error → {str(receipt_error)[:50]}...")
                return {"success": True, "tx_hash": tx_hash, "warning": "Could not verify transaction"}

        except Exception as e:
            error_msg = str(e).lower()
            
            if "insufficient funds" in error_msg:
                return {"success": False, "message": "Insufficient funds for gas"}
            elif "nonce too low" in error_msg:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Nonce too low, retrying...")
                time.sleep(2)
                continue
            elif "replacement transaction underpriced" in error_msg:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Transaction underpriced, retrying with higher gas...")
                time.sleep(2)
                continue
            elif "transaction not found" in error_msg:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Transaction not found, retrying...")
                time.sleep(3)
                continue
            elif "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Network issue → {str(e)[:50]}...")
                time.sleep(random.randint(3, 6))
                continue
            else:
                safe_print(f"{job_prefix} ⚠️  Attempt {attempt}: Unexpected error → {str(e)[:50]}...")
                
        if attempt < max_retries:
            delay = random.randint(2, 5)
            safe_print(f"{job_prefix} ⏳ Retrying transfer in {delay} seconds...")
            time.sleep(delay)

    return {"success": False, "message": f"Transfer failed after {max_retries} attempts"}


def run_job(index, total_jobs, proxies, wallets):
    job_prefix = f"[Job {index:2d}/{total_jobs}]"
    
    dest_address = get_random_wallet(wallets)
    if not dest_address:
        safe_print(f"{job_prefix} ❌ No destination wallet available!")
        return False
    
    safe_print(f"\n{job_prefix} 🚀 Starting job...")
    priv, addr = generate_evm_wallet()
    safe_print(f"{job_prefix} 🔑 From Address: {addr}")
    safe_print(f"{job_prefix} 🎯 To Address: {dest_address}")

    safe_print(f"{job_prefix} 💧 Requesting faucet...")
    result = request_faucet(addr, proxies, index, total_jobs)

    if result.get("success"):
        faucet_tx = result.get("transactionHash")
        safe_print(f"{job_prefix} ✅ Faucet Requested Successfully!")
        safe_print(f"{job_prefix} 📝 Explorer: {EXPLORER}{faucet_tx}")

        wait_time = random.randint(5, 10)
        safe_print(f"{job_prefix} ⏳ Waiting {wait_time}s to check balance...")
        time.sleep(wait_time)

        bal = 0
        for attempt in range(1, 4):
            bal = get_balance(addr)
            if bal > 0:
                break
            safe_print(f"{job_prefix} ⚠️  Balance still 0 (attempt {attempt}/3), retrying in 5s...")
            time.sleep(5)

        safe_print(f"{job_prefix} 💰 Balance: {bal:.6f} tTRUST")

        if bal > 0:
            safe_print(f"{job_prefix} 📤 Transferring to {dest_address[:10]}...")
            transfer_result = send_all_balance(priv, addr, dest_address, index, total_jobs)
            
            if transfer_result["success"]:
                safe_print(f"{job_prefix} 🎉 Faucet Transfered Successfully!")
                safe_print(f"{job_prefix} 📝 Explorer: {EXPLORER}{transfer_result['tx_hash']}")
                return True
            else:
                safe_print(f"{job_prefix} ❌ Transfer Faucet failed: {transfer_result['message']}")
        else:
            safe_print(f"{job_prefix} ❌ Balance still 0 after 3 attempts, skipping transfer")
    else:
        safe_print(f"{job_prefix} ❌ Request Faucet FAILED: {result.get('message')}")

    safe_print(f"{job_prefix} ❌ Job completed with failure")
    return False

if __name__ == "__main__":
    safe_print("\n" + "="*70)
    safe_print("           🚰 INTUITION TESTNET FAUCET AUTO BOT  🚰")
    safe_print("="*70)
    
    if not w3.is_connected():
        safe_print("❌ Failed to connect to RPC. Check network/RPC_URL.")
        exit(1)

    proxies = load_proxies("proxy.txt")
    wallets = load_wallets("wallets.txt")
    
    safe_print(f"📋 Loaded {len(proxies)} proxies")
    
    if not wallets:
        safe_print("❌ No destination wallets loaded! Please check wallets.txt")
        exit(1)

    total_runs = int(input("🔢 Enter number of loops: "))
    max_threads = int(input("🧵 Enter number of threads: "))

    safe_print(f"\n🚀 Starting {total_runs} jobs with {max_threads} threads...")
    safe_print("="*60)

    total_success = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(run_job, i+1, total_runs, proxies, wallets) for i in range(total_runs)]
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            success = future.result()
            if success:
                total_success += 1
            
            progress = (completed / total_runs) * 100
            safe_print(f"\n📊 Progress: {completed}/{total_runs} ({progress:.1f}%) | Success: {total_success}")

    end_time = time.time()
    duration = end_time - start_time

    rate = (total_success / total_runs * 100) if total_runs > 0 else 0

    safe_print("\n" + "="*60)
    safe_print("                    📊 FINAL SUMMARY")
    safe_print("="*60)
    safe_print(f"✅ Total Success    : {total_success}")
    safe_print(f"📢 Total Jobs       : {total_runs}")
    safe_print(f"❌ Failed Jobs      : {total_runs - total_success}")
    safe_print(f"📊 Success Rate     : {rate:.2f}%")
    safe_print(f"⏱️  Duration        : {duration:.2f} seconds")
    safe_print(f"⚡ Average per job  : {duration/total_runs:.2f} seconds")
    safe_print("="*60)
