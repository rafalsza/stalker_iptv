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
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            print(f"Authentication error: {e}")
            return False

        return False

    def _parse_channels_from_response(self, data):
        """Extract channels list from API response data"""
        all_channels = data.get("js", {})
        
        # Handle different response structures
        if isinstance(all_channels, dict):
            all_channels = self._extract_channels_from_dict(all_channels)
        elif isinstance(all_channels, str):
            all_channels = self._parse_json_string(all_channels)
        
        # Fallback to other data structures
        if not isinstance(all_channels, list):
            all_channels = self._fallback_channel_extraction(data)
            
        return all_channels if isinstance(all_channels, list) else []
    
    def _extract_channels_from_dict(self, data_dict):
        """Extract channels from dictionary response"""
        channels_from_dict = []
        for key, value in data_dict.items():
            if isinstance(value, list):
                channels_from_dict.extend(value)
        return channels_from_dict
    
    def _parse_json_string(self, json_str):
        """Parse JSON string to extract channels"""
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _fallback_channel_extraction(self, data):
        """Try alternative data locations for channels"""
        if isinstance(data, list):
            return data
        
        # Check common channel keys
        for key in ["data", "channels"]:
            if key in data:
                return data[key]
        
        print(f"Błąd: oczekiwano listy kanałów, otrzymano: {type(data)}")
        print(f"Debug - struktura odpowiedzi: {list(data.keys()) if isinstance(data, dict) else 'nie jest słownikiem'}")
        return []
    
    def _process_channel_data(self, channel):
        """Process individual channel data and extract stream info"""
        if not isinstance(channel, dict):
            return None
        
        channel_info = {
            "id": channel.get("id"),
            "name": channel.get("name", ""),
            "number": channel.get("number", ""),
            "logo": channel.get("logo", ""),
            "cmd": channel.get("cmd", ""),
        }
        
        cmd = channel.get("cmd", "")
        if cmd and "ffmpeg http" in cmd:
            channel_info["url"] = self._process_ffmpeg_command(cmd)
            return channel_info
        
        return None
    
    def _process_ffmpeg_command(self, cmd):
        """Process ffmpeg command and replace localhost with portal URL"""
        parsed = urlparse(self.portal_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return cmd.replace("http://localhost", base_url)

    def get_channels(self):
        """Pobiera listę kanałów"""
        if not self.token and not self.authenticate():
            return []

        api_url = self.get_api_url()
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
            print(f"Debug - znaleziono {len(data.get('js', {}))} elementów")

            all_channels = self._parse_channels_from_response(data)
            channels = []
            
            for ch in all_channels:
                processed_channel = self._process_channel_data(ch)
                if processed_channel:
                    channels.append(processed_channel)

            print(f"Znaleziono {len(channels)} kanałów ze strumieniami")
            return channels

        except Exception as e:
            print(f"Błąd pobierania kanałów: {e}")
            return []

    def get_stream_url(self, channel_id):
        """Pobiera URL strumienia dla kanału"""
        if not self._is_valid_request(channel_id):
            return None

        try:
            response_data = self._fetch_stream_response(channel_id)
            return self._extract_url_from_response(response_data)
        except Exception as e:
            print(f"Błąd pobierania URL strumienia: {e}")
            return None

    def _is_valid_request(self, channel_id):
        """Sprawdza czy żądanie jest prawidłowe"""
        return self.token and channel_id

    def _fetch_stream_response(self, channel_id):
        """Pobiera odpowiedź z API"""
        api_url = self.get_api_url()
        params = self._build_stream_params(channel_id)
        
        response = self.session.get(
            api_url,
            headers=self.headers,
            params=params,
            cookies=self.cookies,
            timeout=15,
        )
        
        data = response.json()
        print(f"Debug - stream URL response: {data}")
        print(f"Debug - raw cmd from response: {data.get('js', 'NO JS FIELD')}")
        return data

    def _build_stream_params(self, channel_id):
        """Buduje parametry dla żądania strumienia"""
        return {
            "type": "itv",
            "action": "create_link",
            "cmd": f"ffmpeg http://localhost/ffmpeg/{channel_id}",
            "JsHttpRequest": "1-xml",
        }

    def _extract_url_from_response(self, data):
        """Wyciąga URL z odpowiedzi API"""
        if "js" not in data:
            return None
            
        cmd = data["js"]
        
        if isinstance(cmd, str):
            return self._extract_url_from_string(cmd)
            
        if isinstance(cmd, dict) and "cmd" in cmd:
            return self._extract_url_from_string(cmd["cmd"])
            
        return None

    def _extract_url_from_string(self, text):
        """Wyciąga URL z tekstu"""
        if "http" not in text:
            return None
            
        url_match = re.search(r"http\S+", text)
        return url_match.group(0) if url_match else None

    def get_real_stream_url(self, cmd):
        """Pobiera prawdziwy URL strumienia używając create_link API"""
        if not cmd or not self.token:
            return None

        print(f"Debug - Input cmd: {cmd}")  # Debug
        print(f"Debug - Token available: {bool(self.token)}")  # Debug

        # Try direct URL extraction first
        direct_url = self._extract_direct_url(cmd)
        if direct_url:
            return direct_url

        # Try API-based URL extraction
        api_url = self._get_api_stream_url(cmd)
        if api_url:
            return api_url

        # Fallback to alternative URL extraction
        return self._extract_alternative_url(cmd)

    def _extract_direct_url(self, cmd):
        """Extract direct URL from command"""
        # Check for direct play/live.php URL
        if "http://" in cmd and "play/live.php" in cmd:
            url_match = re.search(r"http://[^\s]+", cmd)
            if url_match:
                return url_match.group(0)

        # Check for localhost URL and convert to portal URL
        if "http://localhost" in cmd:
            return self._convert_localhost_to_portal_url(cmd)

        return None

    def _convert_localhost_to_portal_url(self, cmd):
        """Convert localhost URL to portal URL"""
        url_match = re.search(r"ffmpeg (http://[^\s]+)", cmd)
        if not url_match:
            return None

        original_url = url_match.group(1)
        parsed = urlparse(self.portal_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return original_url.replace("http://localhost", base_url)

    def _get_api_stream_url(self, cmd):
        """Get stream URL via API call"""
        api_url = self.get_api_url()
        params = self._build_api_params(cmd)

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
            return self._extract_url_from_api_response(data)

        except Exception as e:
            print(f"Błąd pobierania prawdziwego URL: {e}")
            return None

    def _build_api_params(self, cmd):
        """Build API parameters for create_link request"""
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

        if self.token:
            params["token"] = self.token

        return params

    def _extract_url_from_api_response(self, data):
        """Extract URL from API response"""
        if "js" not in data or "cmd" not in data["js"]:
            return None

        real_cmd = data["js"]["cmd"]
        print(f"Debug - extracted real_cmd: {real_cmd}")  # Debug
        
        url_match = re.search(r"http[^\s]+", real_cmd)
        if url_match:
            final_url = url_match.group(0)
            print(f"Debug - final extracted URL: {final_url}")  # Debug
            return final_url

        return None

    def _extract_alternative_url(self, cmd):
        """Extract alternative URL from command as fallback"""
        if "http://" not in cmd and "https://" not in cmd:
            return None

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

        test_channels, test_type = self._prepare_test_channels(channels, num_tests, polish_only)
        print(f"Testowanie {len(test_channels)} {test_type} kanałów...")

        success_count = self._test_channels_batch(test_channels, use_fallback)
        success_rate = (success_count / len(test_channels)) * 100
        print(f"Wynik testu: {success_count}/{len(test_channels)} kanałów działa ({success_rate:.1f}%)")

        return success_rate >= 50

    def _prepare_test_channels(self, channels, num_tests, polish_only):
        """Przygotowuje listę kanałów do testowania"""
        if polish_only:
            polish_channels = self.get_polish_channels(channels)
            if not polish_channels:
                print("Nie znaleziono polskich kanałów do testowania")
                print("Testowanie losowych kanałów zamiast polskich...")
                return random.sample(channels, min(num_tests, len(channels))), "losowych"
            else:
                return random.sample(polish_channels, min(num_tests, len(polish_channels))), "polskich"
        else:
            return random.sample(channels, min(num_tests, len(channels))), "losowych"

    def _test_channels_batch(self, test_channels, use_fallback):
        """Testuje wsadowo kanały i zwraca liczbę sukcesów"""
        success_count = 0
        
        for i, ch in enumerate(test_channels, 1):
            if self._test_single_channel(ch, i, len(test_channels), use_fallback):
                success_count += 1
            time.sleep(0.5)
            
        return success_count

    def _test_single_channel(self, ch, current_index, total_count, use_fallback):
        """Testuje pojedynczy kanał i zwraca True jeśli sukces"""
        name = ch.get("name", "Unknown")
        cmd = ch.get("cmd", "")
        
        safe_name = self._sanitize_channel_name(name)
        print(f"[{current_index}/{total_count}] Testowanie: {safe_name}")
        
        if not cmd:
            print("  [ERROR] Brak komendy dla kanału")
            return False
            
        real_url = self.get_real_stream_url(cmd)
        if not real_url:
            print("  [ERROR] Nie można uzyskać prawdziwego URL")
            return False
            
        print(f"  URL: {real_url[:60]}...")
        return self._test_stream_url(real_url, use_fallback)

    def _sanitize_channel_name(self, name):
        """Usuwa problemyczne znaki z nazwy kanału"""
        return "".join(c if ord(c) < 128 else "?" for c in name)

    def _test_stream_url(self, real_url, use_fallback):
        """Testuje URL strumienia używając ffprobe lub fallback"""
        try:
            return self._test_with_ffprobe(real_url)
        except FileNotFoundError:
            return self._handle_ffprobe_missing(real_url, use_fallback)
        except Exception as e:
            print(f"  [FAIL] Błąd testu: {str(e)[:50]}")
            return False

    def _test_with_ffprobe(self, real_url):
        """Testuje strumień używając ffprobe"""
        cmd_ffprobe = [
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1", real_url
        ]
        
        result = subprocess.run(cmd_ffprobe, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and ("video" in result.stdout or "audio" in result.stdout):
            print("  [OK] Strumień dostępny i odtwarzalny")
            return True
        else:
            print(f"  [FAIL] Strumień niedostępny: {result.stderr.strip()}")
            return False

    def _handle_ffprobe_missing(self, real_url, use_fallback):
        """Obsługuje brak ffprobe - używa fallback lub standardowego testu"""
        if use_fallback:
            return self._test_with_fallback(real_url)
        else:
            return self._test_with_http_requests(real_url)

    def _test_with_fallback(self, real_url):
        """Testuje URL z fallback proxy"""
        success, message = self.test_stream_url_with_fallback(real_url)
        if success:
            print(f"  [OK] {message}")
        else:
            print(f"  [FAIL] {message}")
        return success

    def _test_with_http_requests(self, real_url):
        """Testuje URL używając standardowych żądań HTTP"""
        try:
            response = requests.head(real_url, timeout=8, allow_redirects=True)
            
            if response.status_code != 200:
                print(f"  [FAIL] URL nie odpowiada (status: {response.status_code})")
                return False
                
            if not self._is_valid_content_type(response):
                return False
                
            return self._test_stream_data(real_url, response)
            
        except Exception as e:
            print(f"  [FAIL] Błąd połączenia: {str(e)[:50]}")
            return False

    def _is_valid_content_type(self, response):
        """Sprawdza czy Content-Type jest odpowiedni dla strumienia wideo"""
        content_type = response.headers.get("Content-Type", "").lower()
        video_types = [
            "video/mp4", "video/mpeg", "video/avi", "video/x-matroska",
            "application/octet-stream", "video/mp2t", "application/x-mpegURL"
        ]
        
        if not any(vt in content_type for vt in video_types):
            print(f"  [FAIL] Zły Content-Type: {content_type}")
            return False
        return True

    def _test_stream_data(self, real_url, head_response):
        """Testuje dane strumienia"""
        content_length = head_response.headers.get("Content-Length", "0")
        
        if content_length != "0":
            return self._test_stream_sample(real_url)
        else:
            print(f"  [OK] Live stream (status: {head_response.status_code})")
            return True

    def _test_stream_sample(self, real_url):
        """Testuje próbkę danych strumienia"""
        try:
            sample_response = requests.get(real_url, timeout=8, stream=True)
            sample_data = next(sample_response.iter_content(512), b"")
            
            if len(sample_data) == 0:
                print("  [FAIL] Brak danych w strumieniu")
                return False
                
            if self._is_html_error(sample_data):
                print("  [FAIL] To jest plik HTML/XML, nie strumień wideo")
                return False
            else:
                print(f"  [OK] Strumień z danymi (status: {sample_response.status_code}, {len(sample_data)} bytes)")
                return True
                
        except Exception as e:
            print(f"  [FAIL] Błąd pobierania próbki: {str(e)[:50]}")
            return False

    def _is_html_error(self, sample_data):
        """Sprawdza czy próbka danych to błąd HTML/XML"""
        data_start = sample_data[:100].strip()
        return (
            data_start.startswith(b"<!DOCTYPE") or
            data_start.startswith(b"<html") or
            data_start.startswith(b"<?xml")
        )

    def _build_proxy_url(self, original_url, proxy_server):
        """Buduje URL z serwerem proxy"""
        from urllib.parse import urlparse
        
        parsed = urlparse(original_url)
        path = parsed.path
        query = parsed.query
        
        proxy_url = f"{proxy_server}{path}"
        if query:
            proxy_url += f"?{query}"
        return proxy_url

    
    def _test_single_url(self, url, proxy_server=None):
        """Testuje pojedynczy URL i zwraca (success, message)"""
        try:
            response = self.session.head(url, timeout=8, allow_redirects=True)
            
            if response.status_code != 200:
                return False, None
                
            if not self._is_valid_content_type(response):
                return False, None
                
            # Pobierz próbkę danych
            try:
                sample_response = self.session.get(url, timeout=12, stream=True)
                sample_data = next(sample_response.iter_content(1024), b"")
                
                if len(sample_data) == 0:
                    return False, None
                    
                if self._is_html_error(sample_data):
                    return False, None
                    
                server_name = "Oryginalny" if proxy_server is None else proxy_server
                return True, f"Działa z serwerem: {server_name}"
                
            except Exception:
                return False, None
                
        except Exception:
            return False, None

    def test_stream_url_with_fallback(self, url):
        """Testuje URL strumienia z różnymi serwerami proxy jako fallback"""
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

        for proxy_server in proxy_servers:
            test_url = self._build_proxy_url(url, proxy_server) if proxy_server else url
            success, message = self._test_single_url(test_url, proxy_server)
            
            if success:
                return True, message

        return False, "Żaden serwer proxy nie działa"

    def generate_m3u(self, channels, use_real_urls=True):
        """Generuje M3U z kanałami"""
        m3u_content = "#EXTM3U\n\n"

        for ch in channels:
            name = ch.get("name", "Unknown")
            cmd = ch.get("cmd", "")
            logo = ch.get("logo", "")

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
