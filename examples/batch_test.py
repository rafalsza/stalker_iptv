#!/usr/bin/env python3
"""
Przykład testowania wielu portali jednocześnie
"""

import sys
import os
import json

# Dodaj katalog główny do ścieżki
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stalker_test import StalkerToM3U

def test_multiple_portals():
    """Testuje wiele portali z pliku JSON"""
    
    portals_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "portals.json")
    
    try:
        with open(portals_file, "r") as f:
            portals = json.load(f)
    except FileNotFoundError:
        print(f"Błąd: Nie znaleziono pliku {portals_file}")
        return
    
    print(f"Testowanie {len(portals)} portali...")
    print("=" * 60)
    
    working_portals = []
    
    for i, portal in enumerate(portals, 1):
        url = portal.get("url", "")
        mac = portal.get("mac", "")
        name = portal.get("name", f"Portal {i}")
        
        print(f"[{i}/{len(portals)}] Testowanie: {name}")
        print(f"  URL: {url}")
        print(f"  MAC: {mac}")
        
        try:
            converter = StalkerToM3U(url, mac)
            
            if converter.authenticate():
                channels = converter.get_channels()
                
                if channels:
                    # Testuj tylko 1 kanał dla szybkości
                    is_working = converter.test_random_channels(channels, num_tests=1)
                    
                    if is_working:
                        print(f"  [OK] {len(channels)} kanałów - DZIAŁA")
                        working_portals.append({
                            'name': name,
                            'url': url,
                            'mac': mac,
                            'channels': len(channels)
                        })
                    else:
                        print(f"  [FAIL] {len(channels)} kanałów - strumienie nie działają")
                else:
                    print(f"  [FAIL] Brak kanałów")
            else:
                print(f"  [FAIL] Autentykacja nieudana")
                
        except Exception as e:
            print(f"  [ERROR] {str(e)[:50]}...")
        
        print()
    
    # Podsumowanie
    print("=" * 60)
    print(f"Zakończono testowanie. Znaleziono {len(working_portals)} działających portali:")
    
    for portal in working_portals:
        print(f"  - {portal['name']}: {portal['channels']} kanałów")
        print(f"    URL: {portal['url']}")
        print(f"    MAC: {portal['mac']}")
        print()
    
    # Zapis wyników
    if working_portals:
        output_file = "working_portals_batch.json"
        with open(output_file, "w") as f:
            json.dump(working_portals, f, indent=2)
        print(f"Wyniki zapisane w: {output_file}")

if __name__ == "__main__":
    test_multiple_portals()
