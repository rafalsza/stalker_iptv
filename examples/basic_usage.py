#!/usr/bin/env python3
"""
Podstawowy przykład użycia biblioteki Stalker IPTV
"""

import sys
import os

# Dodaj katalog główny do ścieżki
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stalker_test import StalkerToM3U
import json

def main():
    # Przykładowy portal
    portal_url = "http://portal.example.com/c/"
    mac_address = "00:1A:79:XX:XX:XX"
    
    print(f"Testowanie portalu: {portal_url}")
    print(f"MAC: {mac_address}")
    print("=" * 50)
    
    # Inicjalizacja
    converter = StalkerToM3U(portal_url, mac_address)
    
    # Test autentykacji
    print("1. Testowanie autentykacji...")
    if converter.authenticate():
        print("   [OK] Autentykacja pomyślna")
    else:
        print("   [FAIL] Autentykacja nieudana")
        return
    
    # Pobieranie kanałów
    print("2. Pobieranie listy kanałów...")
    channels = converter.get_channels()
    print(f"   Znaleziono {len(channels)} kanałów")
    
    if channels:
        # Pokaż przykładowe kanały
        print("\n3. Przykładowe kanały:")
        for i, channel in enumerate(channels[:5], 1):
            name = channel.get('name', 'Unknown')
            url = channel.get('url', '')
            print(f"   {i}. {name}")
            print(f"      URL: {url[:80]}...")
        
        # Testowanie strumieni
        print("\n4. Testowanie losowych kanałów...")
        is_working = converter.test_random_channels(channels, num_tests=3)
        
        if is_working:
            print("   [OK] Portal działa poprawnie")
            
            # Generowanie M3U
            print("\n5. Generowanie playlisty M3U...")
            m3u_content = converter.generate_m3u(channels)
            
            with open("playlist.m3u", "w", encoding="utf-8") as f:
                f.write(m3u_content)
            print("   [OK] Playlista zapisana jako playlist.m3u")
        else:
            print("   [FAIL] Portal nie przeszedł testu strumieni")
    else:
        print("   [FAIL] Nie udało się pobrać kanałów")

if __name__ == "__main__":
    main()
