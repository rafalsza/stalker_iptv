import json
import random
import re
import subprocess
import time
from urllib.parse import urlparse

import requests


class StalkerToM3U:
    def __init__(self, portal_url, mac):
        self.portal_url = portal_url.rstrip("/")
        self.mac = mac
        self.session = requests.Session()

        self.headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 roz/2.16.1.435 Safari/533.3",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "X-User-Agent": "Model: MAG250; Link: WiFi",
        }

        self.cookies = {"mac": self.mac, "stb_lang": "en", "timezone": "Europe/Warsaw"}
        self.token = None

    def get_api_url(self):
        """Generuje URL do API endpointu"""
        parsed = urlparse(self.portal_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base + "/server/load.php"

    def authenticate(self):
        """Autentykacja i pobranie tokenu"""
        api_url = self.get_api_url()

        params = {
            "type": "stb",
            "action": "handshake",
            "token": "",
            "JsHttpRequest": "1-xml",
        }

        try:
            response = self.session.get(
                api_url,
                headers=self.headers,
                params=params,
                cookies=self.cookies,
                timeout=15,
            )

            data = response.json()
            if "js" in data and "token" in data["js"]:
                self.token = data["js"]["token"]
                return True
        except:
            pass

        return False

    def get_channels(self):
        """Pobiera listę kanałów"""
        if not self.token:
            if not self.authenticate():
                return []

        api_url = self.get_api_url()

        # Pobieramy wszystkie kanały
        params = {
            "type": "itv",
            "action": "get_all_channels",
            "force_ch_link_check": "0",
            "JsHttpRequest": "1-xml",
        }

        try:
            response = self.session.get(
                api_url,
                headers=self.headers,
                params=params,
                cookies=self.cookies,
                timeout=15,
            )

            data = response.json()
            print(f"Debug - znaleziono {len(data.get('js', {}))} elementów")  # Debug

            channels = []

            # Sprawdzamy różne możliwe struktury odpowiedzi
            all_channels = data.get("js", {})

            # Jeśli js jest słownikiem, może zawierać kanały w innej formie
            if isinstance(all_channels, dict):
                # Sprawdź czy słownik zawiera listę kanałów jako wartości
                channels_from_dict = []
                for key, value in all_channels.items():
                    if isinstance(value, list):
                        channels_from_dict.extend(value)
                all_channels = channels_from_dict

            # Jeśli js jest stringiem, spróbujemy sparsować
            elif isinstance(all_channels, str):
                try:
                    all_channels = json.loads(all_channels)
                except:
                    all_channels = []

            if not isinstance(all_channels, list):
                # Sprawdź czy dane bezpośrednio zawierają listę kanałów
                if isinstance(data, list):
                    all_channels = data
                # Sprawdź czy dane zawierają kanały w innym kluczu
                elif "data" in data:
                    all_channels = data["data"]
                elif "channels" in data:
                    all_channels = data["channels"]
                else:
                    print(f"Błąd: oczekiwano listy kanałów, otrzymano: {type(all_channels)}")
                    print(
                        f"Debug - struktura odpowiedzi: {list(data.keys()) if isinstance(data, dict) else 'nie jest słownikiem'}"
                    )
                    return []

            for ch in all_channels:
                if not isinstance(ch, dict):
                    continue

                channel_info = {
                    "id": ch.get("id"),
                    "name": ch.get("name", ""),
                    "number": ch.get("number", ""),
                    "logo": ch.get("logo", ""),
                    "cmd": ch.get("cmd", ""),
                }

                # Używamy bezpośrednio komendy ffmpeg jako URL strumienia
                cmd = ch.get("cmd", "")
                if cmd and "ffmpeg http" in cmd:
                    # Używamy pełnej komendy ffmpeg, nie tylko URL!
                    # Zamieniamy localhost na prawdziwy adres serwera w komendzie
                    parsed = urlparse(self.portal_url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    cmd = cmd.replace("http://localhost", base_url)

                    channel_info["url"] = cmd  # Używamy pełnej komendy ffmpeg
                    channels.append(channel_info)

            print(f"Znaleziono {len(channels)} kanałów ze strumieniami")
            return channels

        except Exception as e:
            print(f"Błąd pobierania kanałów: {e}")
            return []

    def get_stream_url(self, channel_id):
        """Pobiera URL strumienia dla kanału"""
        if not self.token or not channel_id:
            return None

        api_url = self.get_api_url()

        params = {
            "type": "itv",
            "action": "create_link",
            "cmd": f"ffmpeg http://localhost/ffmpeg/{channel_id}",
            "JsHttpRequest": "1-xml",
        }

        try:
            response = self.session.get(
                api_url,
                headers=self.headers,
                params=params,
                cookies=self.cookies,
                timeout=15,
            )

            data = response.json()
            print(f"Debug - stream URL response: {data}")  # Debug
            print(f"Debug - raw cmd from response: {data.get('js', 'NO JS FIELD')}")  # Debug

            if "js" in data:
                cmd = data["js"]
                # Wyciągamy URL z komendy ffmpeg
                if isinstance(cmd, str) and "http" in cmd:
                    # Znajdź URL w komendzie
                    url_match = re.search(r"http[^\s]+", cmd)
                    if url_match:
                        return url_match.group(0)
                elif isinstance(cmd, dict) and "cmd" in cmd:
                    cmd_str = cmd["cmd"]
                    if "http" in cmd_str:
                        url_match = re.search(r"http[^\s]+", cmd_str)
                        if url_match:
                            return url_match.group(0)

        except Exception as e:
            print(f"Błąd pobierania URL strumienia: {e}")

        return None

    def get_real_stream_url(self, cmd):
        """Pobiera prawdziwy URL strumienia używając create_link API"""
        if not cmd or not self.token:
            return None

        print(f"Debug - Input cmd: {cmd}")  # Debug
        print(f"Debug - Token available: {bool(self.token)}")  # Debug

        # Sprawdź czy komenda zawiera już bezpośredni URL (jak troublesupport.my.to)
        if "http://" in cmd and "play/live.php" in cmd:
            # Wyciągaj bezpośredni URL z komendy
            url_match = re.search(r"http://[^\s]+", cmd)
            if url_match:
                return url_match.group(0)

        # Spróbuj bezpośredniego URL (bez serwerów proxy)
        if "http://localhost" in cmd:
            # Wyciągnij URL z komendy ffmpeg i użyj bezpośrednio portalu
            url_match = re.search(r"ffmpeg (http://[^\s]+)", cmd)
            if url_match:
                original_url = url_match.group(1)
                # Zamień localhost na adres portalu
                parsed = urlparse(self.portal_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                direct_url = original_url.replace("http://localhost", base_url)
                return direct_url

        # Standardowe API create_link dla innych portali
        api_url = self.get_api_url()

        params = {
            "type": "itv",
            "action": "create_link",
            "cmd": cmd,
            "series": "",
            "forced_storage": "undefined",
            "disable_ad": "0",
            "download": "0",
            "JsHttpRequest": "1-xml",
        }

        # Dodaj token do parametrów jeśli dostępny
        if self.token:
            params["token"] = self.token

        try:
            print(f"Debug - Calling create_link API with params: {params}")  # Debug
            response = self.session.get(
                api_url,
                headers=self.headers,
                params=params,
                cookies=self.cookies,
                timeout=15,
            )

            data = response.json()
            print(f"Debug - create_link response: {data}")  # Debug
            if "js" in data and "cmd" in data["js"]:
                # Wyciągamy prawdziwy URL z odpowiedzi
                real_cmd = data["js"]["cmd"]
                print(f"Debug - extracted real_cmd: {real_cmd}")  # Debug
                url_match = re.search(r"http[^\s]+", real_cmd)
                if url_match:
                    final_url = url_match.group(0)
                    print(f"Debug - final extracted URL: {final_url}")  # Debug
                    return final_url

        except Exception as e:
            print(f"Błąd pobierania prawdziwego URL: {e}")

        # Alternatywna metoda: próbuj bezpośredniego URL z komendy
        if "http://" in cmd or "https://" in cmd:
            url_match = re.search(r"https?://[^\s]+", cmd)
            if url_match:
                alt_url = url_match.group(0)
                print(f"Debug - Trying alternative direct URL: {alt_url}")
                return alt_url

        return None

    def get_polish_channels(self, channels):
        """Filtruje polskie kanały z listy kanałów"""
        polish_keywords = [
            "PL:",
            "POL",
            "POLSKA",
            "POLSKI",
            "TVP",
            "POLSAT",
            "TVN",
            "CANAL+",
            "HBO",
            "ALE KINO+",
            "AXN",
            "DISCOVERY",
            "NATIONAL GEOGRAPHIC",
            "FILMBOX",
            "TVN24",
            "TVN7",
            "TV4",
            "TV6",
            "TV PULS",
            "TVP INFO",
            "TVP SPORT",
            "ELEVEN",
            "TVP 1",
            "TVP 2",
            "TVP HD",
            "POLSAT NEWS",
            "POLSAT SPORT",
            "NICKELODEON",
            "CARTOON",
            "DISNEY",
            "MINIMINI+",
            "JIMJAM",
        ]

        polish_channels = []

        for ch in channels:
            name = ch.get("name", "").upper()

            # Sprawdź czy nazwa zawiera polskie słowa kluczowe
            for keyword in polish_keywords:
                if keyword.upper() in name:
                    polish_channels.append(ch)
                    break

        return polish_channels

    def test_random_channels(self, channels, num_tests=3, polish_only=False, use_fallback=False):
        """Testuje losowe kanały aby sprawdzić czy portal działa"""
        if not channels:
            return False

        # Jeśli chcemy testować tylko polskie kanały
        if polish_only:
            polish_channels = self.get_polish_channels(channels)
            if not polish_channels:
                print("Nie znaleziono polskich kanałów do testowania")
                print("Testowanie losowych kanałów zamiast polskich...")
                test_channels = random.sample(channels, min(num_tests, len(channels)))
                test_type = "losowych"
            else:
                test_channels = random.sample(polish_channels, min(num_tests, len(polish_channels)))
                test_type = "polskich"
        else:
            test_channels = random.sample(channels, min(num_tests, len(channels)))
            test_type = "losowych"

        print(f"Testowanie {len(test_channels)} {test_type} kanałów...")

        success_count = 0

        for i, ch in enumerate(test_channels, 1):
            name = ch.get("name", "Unknown")
            cmd = ch.get("cmd", "")

            # Usuń problemyczne znaki z nazwy
            safe_name = "".join(c if ord(c) < 128 else "?" for c in name)

            print(f"[{i}/{len(test_channels)}] Testowanie: {safe_name}")

            if not cmd:
                print(f"  [ERROR] Brak komendy dla kanału")
                continue

            # Pobierz prawdziwy URL strumienia
            real_url = self.get_real_stream_url(cmd)

            if not real_url:
                print(f"  [ERROR] Nie można uzyskać prawdziwego URL")
                continue

            print(f"  URL: {real_url[:60]}...")

            # Test URL-a za pomocą ffmpeg (tak jak stalker-to-m3u)
            try:
                # Użyj ffprobe do sprawdzenia czy strumień jest dostępny
                cmd_ffprobe = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    real_url,
                ]

                result = subprocess.run(cmd_ffprobe, capture_output=True, text=True, timeout=10)

                if result.returncode == 0 and ("video" in result.stdout or "audio" in result.stdout):
                    print("  [OK] Strumień dostępny i odtwarzalny")
                    success_count += 1
                else:
                    print(f"  [FAIL] Strumień niedostępny: {result.stderr.strip()}")

            except subprocess.TimeoutExpired:
                print("  [FAIL] Timeout (10s)")
            except FileNotFoundError:
                # Jeśli ffprobe nie jest dostępne, użyj testu z fallback
                if use_fallback:
                    success, message = self.test_stream_url_with_fallback(real_url)
                    if success:
                        print(f"  [OK] {message}")
                        success_count += 1
                    else:
                        print(f"  [FAIL] {message}")
                else:
                    # Standardowy test dla live streams
                    try:
                        response = requests.head(real_url, timeout=8, allow_redirects=True)

                        if response.status_code != 200:
                            print(f"  [FAIL] URL nie odpowiada (status: {response.status_code})")
                            continue

                        # Sprawdź Content-Type - live streams mogą mieć application/octet-stream
                        content_type = response.headers.get("Content-Type", "").lower()
                        video_types = [
                            "video/mp4",
                            "video/mpeg",
                            "video/avi",
                            "video/x-matroska",
                            "application/octet-stream",
                            "video/mp2t",
                            "application/x-mpegURL",
                        ]

                        if not any(vt in content_type for vt in video_types):
                            print(f"  [FAIL] Zły Content-Type: {content_type}")
                            continue

                        # DLA IPTV - bądź bardziej tolerancyjny jak aplikacje
                        content_length = response.headers.get("Content-Length", "0")

                        # Jeśli Content-Length jest większe niż 0, testuj próbkę
                        if content_length != "0":
                            try:
                                sample_response = requests.get(real_url, timeout=8, stream=True)
                                sample_data = next(sample_response.iter_content(512), b"")

                                if len(sample_data) > 0:
                                    # Sprawdź czy to nie jest HTML/XML (błąd 404, etc.)
                                    if (
                                        sample_data[:100].strip().startswith(b"<!DOCTYPE")
                                        or sample_data[:100].strip().startswith(b"<html")
                                        or sample_data[:100].strip().startswith(b"<?xml")
                                    ):
                                        print("  [FAIL] To jest plik HTML/XML, nie strumień wideo")
                                        continue
                                    else:
                                        print(
                                            f"  [OK] Strumień z danymi (status: {response.status_code}, {len(sample_data)} bytes)"
                                        )
                                        success_count += 1
                                else:
                                    print("  [FAIL] Brak danych w strumieniu")
                                    continue
                            except Exception as e:
                                print(f"  [FAIL] Błąd pobierania próbki: {str(e)[:50]}")
                        else:
                            print(f"  [OK] Live stream (status: {response.status_code})")
                            success_count += 1

                    except Exception as e:
                        print(f"  [FAIL] Błąd połączenia: {str(e)[:50]}")
            except Exception as e:
                print(f"  [FAIL] Błąd testu: {str(e)[:50]}")

            # Mała przerwa między testami
            time.sleep(0.5)

        success_rate = (success_count / len(test_channels)) * 100
        print(f"Wynik testu: {success_count}/{len(test_channels)} kanałów działa ({success_rate:.1f}%)")

        return success_rate >= 50

    def test_stream_url_with_fallback(self, url):
        """Testuje URL strumienia z różnymi serwerami proxy jako fallback"""

        # Lista serwerów proxy do testowania
        proxy_servers = [
            None,  # Oryginalny URL
            "http://truk9rrv2.11121367.xyz:8080",
            "http://IiiIIllLLllfd.funtogether.xyz:8080",
            "http://smart.dukoow.net:80",
            "http://medotv.nl:8000",
            "http://neomixs.com:8080",
            "http://troublesupport.my.to:80",
            "http://fastrunner.live:8080",
            "http://vectraiptv.streamtv.to:8080",
            "http://kocaeli41.xyz:8000",
            "http://semprea100.relaxy.vip:8000",
        ]

        for i, proxy_server in enumerate(proxy_servers):
            try:
                # Jeśli mamy serwer proxy, zamień go w URL
                test_url = url
                if proxy_server:
                    # Wyciągnij ścieżkę z oryginalnego URL
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    path = parsed.path
                    query = parsed.query

                    # Zbuduj nowy URL z serwerem proxy
                    test_url = f"{proxy_server}{path}"
                    if query:
                        test_url += f"?{query}"

                # Testuj URL
                response = self.session.head(test_url, timeout=8, allow_redirects=True)

                if response.status_code == 200:
                    # Sprawdź Content-Type
                    content_type = response.headers.get("Content-Type", "").lower()
                    video_types = [
                        "video/mp4",
                        "video/mpeg",
                        "video/avi",
                        "video/x-matroska",
                        "application/octet-stream",
                        "video/mp2t",
                        "application/x-mpegURL",
                    ]

                    if any(vt in content_type for vt in video_types):
                        # Pobierz próbkę danych
                        try:
                            sample_response = self.session.get(test_url, timeout=12, stream=True)
                            sample_data = next(sample_response.iter_content(1024), b"")

                            if len(sample_data) > 0:
                                # Sprawdź czy to nie jest HTML
                                if not (
                                    sample_data[:100].strip().startswith(b"<!DOCTYPE")
                                    or sample_data[:100].strip().startswith(b"<html")
                                    or sample_data[:100].strip().startswith(b"<?xml")
                                ):

                                    server_name = "Oryginalny" if proxy_server is None else proxy_server
                                    return True, f"Działa z serwerem: {server_name}"
                                else:
                                    continue
                            else:
                                continue
                        except Exception as e:
                            continue
                    else:
                        continue
                else:
                    continue

            except Exception as e:
                continue

        return False, "Żaden serwer proxy nie działa"

    def generate_m3u(self, channels, use_real_urls=True):
        """Generuje M3U z kanałami"""
        m3u_content = "#EXTM3U\n\n"

        for ch in channels:
            name = ch.get("name", "Unknown")
            cmd = ch.get("cmd", "")
            logo = ch.get("logo", "")
            number = ch.get("number", "")

            # Użyj prawdziwych URL-i jeśli włączone
            if use_real_urls and cmd:
                real_url = self.get_real_stream_url(cmd)
                if real_url:
                    url = real_url
                else:
                    # Fallback do komendy ffmpeg
                    url = cmd
            else:
                url = cmd

            if url:
                # Format jak w przykładzie użytkownika
                m3u_content += f'#EXTINF:0 user-agent="Firefox" tvg-id="" tvg-name="{name}" tvg-logo="{logo}" group-title="STALKER", {name}\n'
                m3u_content += f"{url}\n\n"

        return m3u_content


def convert_stalker_to_m3u(
    portal_url,
    mac,
    output_file="stalker_channels.m3u",
    test_channels=True,
    polish_only=True,
):
    """Główna funkcja konwersji"""
    converter = StalkerToM3U(portal_url, mac)

    print(f"Konwertowanie portalu: {portal_url} (MAC: {mac})")

    channels = converter.get_channels()

    if channels:
        print(f"Znaleziono {len(channels)} kanałów")

        # Testuj losowe kanały jeśli włączone
        if test_channels:
            is_working = converter.test_random_channels(channels, num_tests=3, polish_only=polish_only)
            if not is_working:
                print("[WARNING] Portal nie przeszedl testu - strumienie moga nie dzialac")
                print("Mimo to generuje M3U...")
            else:
                print("[SUCCESS] Portal przeszedl test - strumienia dzialaja poprawnie")

        # Generuj M3U niezależnie od wyniku testu
        m3u_content = converter.generate_m3u(channels, use_real_urls=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(m3u_content)

        print(f"Wygenerowano M3U z {len(channels)} kanałami: {output_file}")
        return True
    else:
        print("Nie udało się pobrać kanałów")
        return False
