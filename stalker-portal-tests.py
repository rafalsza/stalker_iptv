import concurrent.futures
import json
import os
from urllib.parse import urlparse

import requests
from colorama import init, Fore, Style

from stalker_test import StalkerToM3U

init(autoreset=True)

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "data/portals.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "data/working_portals.json")
TIMEOUT = 15  # Response timeout in seconds
MAX_THREADS = 3  # Number of concurrent connections
TEST_ONLY_POLISH = True  # Test only portals with Polish channels

HEADERS = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 roz/2.16.1.435 Safari/533.3",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "X-User-Agent": "Model: MAG250; Link: WiFi",
}


def clean_url(url):
    """Clean URL and ensure it points to API middleware."""
    if not url.startswith("http"):
        url = "http://" + url

    # Remove /c/ path if present
    url = url.replace("/c/", "/")
    
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    return base + "/server/load.php"


def test_portal(portal_data):
    """Test a single portal."""
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

        # Analyze Stalker response
        if "js" in data and "token" in data["js"]:
            token = data["js"]["token"]

            # Optional: Second profile request to get expiration date
            # Requires using the token obtained above
            
            # Get actual channels from portal
            channels = get_channels_from_portal(api_url, mac, token)
            info = get_profile_info(api_url, mac, token, channels)

            return {
                "status": "WORKING",
                "url": raw_url,
                "mac": mac,
                "info": info,
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
    """Get actual channel links from Stalker portal."""
    try:
        headers = HEADERS.copy()
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}

        c_resp = requests.get(
            api_url,
            headers=headers,
            params={
                "type": "itv",
                "action": "get_all_channels",
                "force_ch_link_check": "0",
                "JsHttpRequest": "1-xml",
                "token": token,
            },
            cookies=cookies,
            timeout=7,
        )

        channels_data = c_resp.json().get("js", [])
        
        # Handle new response structure where channels are in js.data
        if isinstance(channels_data, dict) and "data" in channels_data:
            channels_data = channels_data["data"]
        elif not isinstance(channels_data, list):
            channels_data = []
            
        channels = []

        for ch in channels_data:
            ch_name = ch.get("name", "Unknown")
            ch_url = ch.get("cmd", "")

            # Accept channels with ffmpeg URLs since that's what Stalker portals use now
            if ch_url and "http" in ch_url:
                channels.append({"name": ch_name, "url": ch_url})

        return channels

    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, AttributeError):
        return []


def get_account_info(api_url, headers, cookies):
    """Get account information and expiration date."""
    try:
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
        return exp_data.get("phone") or "N/A"
    except (requests.RequestException, ValueError, KeyError):
        return "N/A"


def get_genres_info(api_url, headers, cookies, token=None):
    """Get genre information and check for Polish channel availability."""
    try:
        params = {
            "type": "itv", 
            "action": "get_genres", 
            "JsHttpRequest": "1-xml"
        }
        if token:
            params["token"] = token
            
        g_resp = requests.get(
            api_url,
            headers=headers,
            params=params,
            cookies=cookies,
            timeout=7,
        )
        genres = g_resp.json().get("js", [])

        has_pl, pl_id = check_polish_channels(genres)
        return genres, has_pl, pl_id
    except (requests.RequestException, ValueError, KeyError) as e:
        return [], False, None


def check_polish_channels(genres):
    """Check if portal has Polish channels."""
    keywords = ["poland", "polska", "polish", "|pl|", " pl "]

    for g in genres:
        name = str(g.get("title", "")).lower()
        if any(k in name for k in keywords):
            return True, g.get("id")

    return False, None


def get_profile_info(api_url, mac, token, channels=None):
    try:
        headers = HEADERS.copy()
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}

        # 1. Get account information
        expires = get_account_info(api_url, headers, cookies)

        # 2. Get profile to check if token is alive
        try:
            requests.get(
                api_url,
                headers=headers,
                params={"type": "stb", "action": "get_profile", "JsHttpRequest": "1-xml", "token": token},
                cookies=cookies,
                timeout=7,
            )
            # Profile request made to validate token is alive
        except requests.RequestException:
            pass

        # 3. Get genre information
        genres, has_pl, _ = get_genres_info(api_url, headers, cookies, token)

        # 4. Use actual channel count if available, check if portal has any channels
        if channels is not None:
            channel_count = len(channels)
            is_active = channel_count > 0
        else:
            is_active = len(genres) > 0
            channel_count = 0

        if is_active:
            return {
                "channels": channel_count,
                "has_pl": has_pl,
                "expires": expires,
                "summary": f"ACTIVE | PL: {'YES' if has_pl else 'NO'} | Exp: {expires} | Channels: {channel_count}",
            }
        else:
            return {
                "channels": 0,
                "summary": "EXPIRED/EMPTY (No channels in categories)",
            }

    except Exception:
        return {
            "channels": 0,
            "summary": f"{Fore.YELLOW}AUTH ONLY{Style.RESET_ALL} (API Limited)",
        }


def test_portal_streams(portal_result):
    """Test streams for a working portal and return success status."""
    print(f"{Fore.YELLOW}=> Testing streams...{Style.RESET_ALL}")
    converter = StalkerToM3U(portal_result["url"], portal_result["mac"])
    channels = converter.get_channels()

    if not channels:
        print(f"  {Fore.RED}[FAIL] Failed to get channels{Style.RESET_ALL}")
        return False

    print(f"  Found {len(channels)} channels")
    is_working = converter.test_random_channels(channels, num_tests=3, polish_only=True)

    if is_working:
        print(f"  {Fore.GREEN}[OK] Portal works correctly{Style.RESET_ALL}")
        return True
    else:
        print(f"  {Fore.RED}[FAIL] Portal failed stream test{Style.RESET_ALL}")
        return False


def process_portal_result(res, working_portals):
    """Process a single portal test result and update working_portals list."""
    url = res.get("url")
    mac = res.get("mac", "")
    status = res.get("status")

    if status != "WORKING":
        if status == "CONNECTION_ERROR":
            return
        print(f"[{Fore.RED}{status}{Style.RESET_ALL}] {url} | MAC: {mac}")
        return

    info = res.get("info", {})
    if not isinstance(info, dict):
        print(f"[{Fore.CYAN}AUTH{Style.RESET_ALL}] {url} | MAC: {mac} (Authentication only)")
        return

    ch_count = info.get("channels", 0)
    if ch_count == 0:
        print(f"[{Fore.YELLOW}EMPTY{Style.RESET_ALL}] {url} | MAC: {mac} (No channels)")
        return

    # Check Polish filter
    if TEST_ONLY_POLISH and not info.get("has_pl"):
        print(f"[{Fore.YELLOW}SKIP{Style.RESET_ALL}] {url} | MAC: {mac} (No Polish channels)")
        return

    pl_tag = f"{Fore.GREEN}[PL!]{Style.RESET_ALL}" if info.get("has_pl") else "[NO-PL]"
    clean_summary = info.get("summary", "")
    colored_summary = clean_summary.replace("ACTIVE", f"{Fore.GREEN}ACTIVE{Style.RESET_ALL}")

    print(f"[{Fore.GREEN}HIT{Style.RESET_ALL}] {pl_tag} {url} | MAC: {mac} | {colored_summary}")

    # Test streams
    if test_portal_streams(res):
        working_portals.append(res)


def save_results(working_portals):
    """Save test results to JSON and Polish portals list."""
    # Save JSON
    with open(OUTPUT_FILE, "w") as f:
        json.dump(working_portals, f, indent=4)

    # Save Polish portals list
    polish_list = [p for p in working_portals if isinstance(p["info"], dict) and p["info"].get("has_pl")]
    if polish_list:
        with open(os.path.join(SCRIPT_DIR, "data/POLISH_HITS.txt"), "w", encoding="utf-8") as f:
            f.write("=== WORKING PORTALS WITH POLISH CHANNELS ===\n\n")
            for p in polish_list:
                f.write(f"URL: {p['url']}\nMAC: {p['mac']}\nINFO: {p['info'].get('summary')}\n")
                f.write("-" * 40 + "\n")


def print_summary(working_portals):
    """Print final test summary."""
    print(f"\n{Fore.CYAN}=== PORTAL TESTING COMPLETED ==={Style.RESET_ALL}")
    print(f"Found {len(working_portals)} working portals (with immediate stream testing)")
    print(f"Saved to: {OUTPUT_FILE}")


def main():
    print(f"{Fore.CYAN}--- Stalker Portal Tester ---\n")

    if TEST_ONLY_POLISH:
        print(f"{Fore.YELLOW}FILTER MODE: Testing only portals with Polish channels{Style.RESET_ALL}\n")

    try:
        with open(INPUT_FILE, "r") as f:
            portals = json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}Error: File not found {INPUT_FILE}")
        return

    working_portals = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_portal = {executor.submit(test_portal, p): p for p in portals}

        for future in concurrent.futures.as_completed(future_to_portal):
            res = future.result()
            if res:
                process_portal_result(res, working_portals)

    save_results(working_portals)
    print_summary(working_portals)


if __name__ == "__main__":
    main()
