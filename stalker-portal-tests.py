import concurrent.futures
import json
import os
from urllib.parse import urlparse

import requests
from colorama import init, Fore, Style

from stalker_test import StalkerToM3U

init(autoreset=True)

# Konfiguracja
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "portals.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "working_portals.json")
TIMEOUT = 15  # Czas oczekiwania na odpowiedź w sekundach
MAX_THREADS = 3  # Liczba jednoczesnych połączeń
TEST_ONLY_POLISH = True  # Testuj tylko portale z polskimi kanałami

# Nagłówki udające urządzenie MAG (niezbędne dla Stalkera)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 roz/2.16.1.435 Safari/533.3",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "X-User-Agent": "Model: MAG250; Link: WiFi",
}


def clean_url(url):
    """Czyści URL i upewnia się, że prowadzi do API middleware."""
    if not url.startswith("http"):
        url = "http://" + url

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    return base + "/server/load.php"


def test_portal(portal_data):
    """Testuje pojedynczy portal."""
    raw_url = portal_data.get("url", "")
    mac = portal_data.get("mac", "")

    if not raw_url or not mac:
        return None

    api_url = clean_url(raw_url)

    params = {
        "type": "stb",
        "action": "handshake",
        "token": "",
        "JsHttpRequest": "1-xml",
    }

    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}

    try:
        response = requests.get(api_url, headers=HEADERS, params=params, cookies=cookies, timeout=TIMEOUT)

        data = response.json()

        # Analiza odpowiedzi Stalkera
        if "js" in data and "token" in data["js"]:
            token = data["js"]["token"]

            # Opcjonalnie: Drugie zapytanie o profil, aby pobrać datę wygaśnięcia
            # Wymaga użycia pobranego wyżej tokenu
            info = get_profile_info(api_url, mac, token)

            # Pobieramy rzeczywiste kanały z portalu
            channels = get_channels_from_portal(api_url, mac, token)

            return {
                "status": "WORKING",
                "url": raw_url,
                "mac": mac,
                "info": info,
                "channels": channels,
            }
        else:
            return {
                "status": "DEAD",
                "url": raw_url,
                "mac": mac,
                "reason": "Auth Failed",
            }

    except requests.exceptions.Timeout:
        return {"status": "TIMEOUT", "url": raw_url, "mac": mac}
    except requests.exceptions.ConnectionError:
        return {"status": "CONNECTION_ERROR", "url": raw_url, "mac": mac}
    except json.JSONDecodeError:
        return {"status": "INVALID_RESPONSE", "url": raw_url, "mac": mac}
    except Exception as e:
        return {"status": "ERROR", "url": raw_url, "mac": mac, "reason": str(e)}


def get_channels_from_portal(api_url, mac, token):
    """Pobiera rzeczywiste linki do kanałów z portalu Stalker."""
    try:
        headers = HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}"
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}

        c_resp = requests.get(
            api_url,
            headers=headers,
            params={
                "type": "itv",
                "action": "get_all_channels",
                "force_ch_link_check": "0",
                "JsHttpRequest": "1-xml",
            },
            cookies=cookies,
            timeout=7,
        )

        channels_data = c_resp.json().get("js", [])
        channels = []

        for ch in channels_data:
            ch_name = ch.get("name", "Unknown")
            ch_url = ch.get("cmd", "")

            if ch_url and "ffmpeg" not in ch_url and "http" in ch_url:
                channels.append({"name": ch_name, "url": ch_url})

        return channels

    except Exception as e:
        return []


def get_profile_info(api_url, mac, token):
    try:
        headers = HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}"
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}

        exp_resp = requests.get(
            api_url,
            headers=headers,
            params={
                "type": "account_info",
                "action": "get_main_info",
                "JsHttpRequest": "1-xml",
            },
            cookies=cookies,
            timeout=7,
        )
        exp_data = exp_resp.json().get("js", {})
        expires = exp_data.get("phone") or "N/A"

        # 2. Pobieramy profil, aby sprawdzić czy token żyje
        p_resp = requests.get(
            api_url,
            headers=headers,
            params={"type": "stb", "action": "get_profile", "JsHttpRequest": "1-xml"},
            cookies=cookies,
            timeout=7,
        )
        p_data = p_resp.json().get("js", {})

        # 3. Pobieramy gatunki (genres), by wyciągnąć ID kategorii PL
        g_resp = requests.get(
            api_url,
            headers=headers,
            params={"type": "itv", "action": "get_genres", "JsHttpRequest": "1-xml"},
            cookies=cookies,
            timeout=7,
        )
        genres = g_resp.json().get("js", [])

        has_pl = False
        pl_id = None
        keywords = ["poland", "polska", "polish", "|pl|", " pl "]

        for g in genres:
            name = str(g.get("title", "")).lower()
            if any(k in name for k in keywords):
                has_pl = True
                pl_id = g.get("id")
                break

        # 4. TEST REALNEGO DOSTĘPU: Pobieramy kanały dla konkretnej kategorii
        # Jeśli kategoria PL nie istnieje, bierzemy pierwszą lepszą (ID: 1 lub z listy)
        if pl_id:
            test_genre = pl_id
        elif genres and len(genres) > 0:
            test_genre = genres[0].get("id")
        else:
            test_genre = "0"

        c_resp = requests.get(
            api_url,
            headers=headers,
            params={
                "type": "itv",
                "action": "get_ordered_list",
                "genre": test_genre,
                "force_ch_link_check": "0",
                "JsHttpRequest": "1-xml",
            },
            cookies=cookies,
            timeout=7,
        )

        c_data = c_resp.json().get("js", {}).get("data", [])

        # Jeśli dostaliśmy listę kanałów (nawet 1), to portal DZIAŁA i MAC jest AKTYWNY
        is_active = len(c_data) > 0

        if is_active:
            return {
                "channels": 1,
                "has_pl": has_pl,
                "expires": expires,
                "summary": f"ACTIVE | PL: {'TAK' if has_pl else 'NIE'} | Exp: {expires}",
            }
        else:
            return {
                "channels": 0,
                "summary": "EXPIRED/EMPTY (No channels in categories)",
            }

    except Exception as e:
        return {
            "channels": 0,
            "summary": f"{Fore.YELLOW}AUTH ONLY{Style.RESET_ALL} (API Limited)",
        }


def main():
    print(f"{Fore.CYAN}--- Stalker Portal Tester ---\n")

    if TEST_ONLY_POLISH:
        print(f"{Fore.YELLOW}TRYB FILTROWANIA: Testowane są tylko portale z polskimi kanałami{Style.RESET_ALL}\n")

    try:
        with open(INPUT_FILE, "r") as f:
            portals = json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}Błąd: Nie znaleziono pliku {INPUT_FILE}")
        return

    working_portals = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_portal = {executor.submit(test_portal, p): p for p in portals}

        for future in concurrent.futures.as_completed(future_to_portal):
            res = future.result()
            if not res:
                continue

            url = res.get("url")
            status = res.get("status")

            if status == "WORKING":
                info = res.get("info", {})
                if isinstance(info, dict):
                    # Zmiana: obsługa 'Active' jako 1 lub rzeczywistej liczby
                    ch_count = info.get("channels", 0)
                    if isinstance(ch_count, str):
                        ch_count = 1

                    pl_tag = f"{Fore.GREEN}[PL!]{Style.RESET_ALL}" if info.get("has_pl") else "[NO-PL]"

                    if ch_count > 0:
                        # Sprawdź czy testujemy tylko portale z polskimi kanałami
                        if TEST_ONLY_POLISH and not info.get("has_pl"):
                            print(f"[{Fore.YELLOW}SKIP{Style.RESET_ALL}] {url} (Brak polskich kanałów)")
                            continue

                        clean_summary = info.get("summary", "")
                        colored_summary = clean_summary.replace("ACTIVE", f"{Fore.GREEN}ACTIVE{Style.RESET_ALL}")

                        print(f"[{Fore.GREEN}HIT{Style.RESET_ALL}] {pl_tag} {url} | {colored_summary}")
                        working_portals.append(res)
                    else:
                        print(f"[{Fore.YELLOW}EMPTY{Style.RESET_ALL}] {url} (Brak kanałów)")
                else:
                    print(f"[{Fore.CYAN}AUTH{Style.RESET_ALL}] {url} (Tylko logowanie)")
            elif status == "CONNECTION_ERROR":
                pass
            else:
                print(f"[{Fore.RED}{status}{Style.RESET_ALL}] {url}")

    # --- ZAPIS JSON ---
    with open(OUTPUT_FILE, "w") as f:
        json.dump(working_portals, f, indent=4)

    # --- TESTOWANIE STRUMIENI ---
    if working_portals:
        print(f"\n{Fore.YELLOW}Testowanie strumieni z {len(working_portals)} portali...{Style.RESET_ALL}")

        verified_portals = []

        for i, p in enumerate(working_portals):
            portal_name = urlparse(p["url"]).netloc
            mac = p["mac"]

            print(f"[{i+1}/{len(working_portals)}] Testowanie: {portal_name}")

            # Szybkie testowanie 3 losowych kanałów
            converter = StalkerToM3U(p["url"], mac)
            channels = converter.get_channels()

            if channels:
                print(f"  Znaleziono {len(channels)} kanałów")
                is_working = converter.test_random_channels(channels, num_tests=3, polish_only=True)

                if is_working:
                    print(f"  {Fore.GREEN}[OK] Portal dziala poprawnie{Style.RESET_ALL}")
                    verified_portals.append(p)
                else:
                    print(f"  {Fore.RED}[FAIL] Portal nie przeszedł testu strumieni{Style.RESET_ALL}")
            else:
                print(f"  {Fore.RED}[FAIL] Nie udalo sie pobrac kanalow{Style.RESET_ALL}")

        # Zastąp working_portals zweryfikowanymi
        working_portals = verified_portals

    # --- GENEROWANIE LISTY POLSKA_HITY.txt (PO testowaniu strumieni) ---
    polska_list = [p for p in working_portals if isinstance(p["info"], dict) and p["info"].get("has_pl")]
    if polska_list:
        with open(os.path.join(SCRIPT_DIR, "POLSKA_HITY.txt"), "w", encoding="utf-8") as f:
            f.write("=== DZIAŁAJĄCE PORTALE Z POLSKIMI KANAŁAMI ===\n\n")
            for p in polska_list:
                f.write(f"URL: {p['url']}\nMAC: {p['mac']}\nINFO: {p['info'].get('summary')}\n")
                f.write("-" * 40 + "\n")

    print(f"\n{Fore.CYAN}=== ZAKOŃCZONO TESTOWANIE PORTALI ==={Style.RESET_ALL}")
    print(f"Znaleziono {len(working_portals)} działających portali")

    # Zapisz tylko zweryfikowane portale
    with open(OUTPUT_FILE, "w") as f:
        json.dump(working_portals, f, indent=4)

    print(f"Zapisano do: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
