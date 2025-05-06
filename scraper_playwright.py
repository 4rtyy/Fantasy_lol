import time
import json
from pathlib import Path
import undetected_chromedriver as uc
from threading import Thread
import os

CACHE_DIR = Path("cache")
SYSTEM_DIR = CACHE_DIR / "system"
PLAYERS_DIR = CACHE_DIR / "players"

for d in [CACHE_DIR, SYSTEM_DIR, PLAYERS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://www.ltafantasy.com/api"
TARGET_APIS = [
    f"{API_BASE}/market",
    f"{API_BASE}/player-stats"
]

# Configurações avançadas de indetectabilidade
temp_profile_path = Path("temp/chrome").resolve()
temp_profile_path.mkdir(parents=True, exist_ok=True)

options = uc.ChromeOptions()
options.add_argument(f"--user-data-dir={str(temp_profile_path)}")
options.add_argument("--profile-directory=Default")
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-infobars")
options.add_argument("--disable-extensions")
options.add_argument("--disable-popup-blocking")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--lang=pt-BR")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

driver = uc.Chrome(options=options, use_subprocess=True)


# Remove rastros JS comuns
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        window.chrome = { runtime: {} };
    """
})

driver.get("https://ltafantasy.com/pt")
print("🔐 Faça login manualmente e vá para https://ltafantasy.com/pt/market")

player_ids_expected = set()
player_ids_captured = set()
captured_urls = set()

def save_json_response(path: Path, body: str):
    try:
        parsed = json.loads(body)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar {path.name}: {e}")

def monitor_requests():
    global player_ids_expected, player_ids_captured
    while True:
        if "https://ltafantasy.com/pt/market" not in driver.current_url:
            time.sleep(1)
            continue

        logs = driver.get_log("performance")
        for entry in logs:
            message = entry.get("message", "")
            if not any(api in message for api in TARGET_APIS + ["/player-stats/"]):
                continue

            try:
                body_start = message.find('{')
                body = json.loads(message[body_start:])
                url = body["message"]["params"]["request"]["url"]
                if url in captured_urls:
                    continue
                captured_urls.add(url)

                if url == f"{API_BASE}/market":
                    path = SYSTEM_DIR / "market.json"
                    if not path.exists():
                        print("📥 market.json capturado")
                        response = driver.execute_cdp_cmd("Network.getResponseBody", {
                            "requestId": body["message"]["params"]["requestId"]
                        })
                        save_json_response(path, response["body"])

                elif url == f"{API_BASE}/player-stats":
                    path = SYSTEM_DIR / "player-stats.json"
                    if not path.exists():
                        print("📥 player-stats.json capturado")
                        response = driver.execute_cdp_cmd("Network.getResponseBody", {
                            "requestId": body["message"]["params"]["requestId"]
                        })
                        save_json_response(path, response["body"])
                        data = json.loads(response["body"])
                        player_ids_expected = {str(p["proPlayerId"]) for p in data if "proPlayerId" in p}
                        print(f"🎯 Total de jogadores esperados: {len(player_ids_expected)}")

                elif "/player-stats/" in url:
                    player_id = url.rsplit("/", 1)[-1].split("?")[0]
                    if player_id in player_ids_captured:
                        continue
                    path = PLAYERS_DIR / f"{player_id}.json"
                    print(f"📥 jogador {player_id} capturado")
                    response = driver.execute_cdp_cmd("Network.getResponseBody", {
                        "requestId": body["message"]["params"]["requestId"]
                    })
                    save_json_response(path, response["body"])
                    player_ids_captured.add(player_id)

                    if player_ids_expected and player_ids_captured == player_ids_expected:
                        print("✅ Todos os jogadores capturados com sucesso.")
                        driver.quit()
                        return
            except Exception:
                pass
        time.sleep(1)

monitor_thread = Thread(target=monitor_requests)
monitor_thread.start()
