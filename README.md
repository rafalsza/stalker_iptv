# Stalker IPTV Portal Tester

Narzędzie do testowania i weryfikacji portalów IPTV opartych na oprogramowaniu Stalker Middleware.

## Funkcjonalności

- **Testowanie portalów Stalker IPTV**: Automatyczne sprawdzanie dostępności portali
- **Weryfikacja kanałów**: Pobieranie i testowanie rzeczywistych strumieni
- **Filtrowanie polskich kanałów**: Identyfikacja portali z polską zawartością
- **Konwersja do M3U**: Generowanie list odtwarzania M3U
- **Testy strumieni**: Weryfikacja jakości działania strumieni

## Struktura projektu

```
stalker_iptv/
├── README.md                 # Dokumentacja
├── requirements.txt          # Zależności Python
├── stalker_test.py          # Główna klasa StalkerToM3U
├── stalker-portal-tests.py  # Testery portali
├── data/                    # Dane wejściowe i wyjściowe
│   ├── portals.json        # Lista portali do testowania
│   ├── working_portals.json # Zweryfikowane portale
│   └── POLSKA_HITY.txt     # Lista portali z polskimi kanałami
└── examples/               # Przykłady użycia
```

## Instalacja

```bash
# Klonuj repozytorium
git clone https://github.com/twoja-nazwa/stalker_iptv.git
cd stalker_iptv

# Zainstaluj zależności
pip install -r requirements.txt
```

## Użycie

### Testowanie portali

```python
from stalker_test import StalkerToM3U

# Inicjalizacja
converter = StalkerToM3U("http://portal.example.com/c/", "00:1A:79:XX:XX:XX")

# Pobierz kanały
channels = converter.get_channels()
print(f"Znaleziono {len(channels)} kanałów")

# Testuj losowe kanały
is_working = converter.test_random_channels(channels, num_tests=3)
```

### Uruchomienie testera portali

```bash
python stalker-portal-tests.py
```

### Generowanie listy M3U

```python
# Konwersja do M3U
m3u_content = converter.generate_m3u(channels)
with open("playlist.m3u", "w") as f:
    f.write(m3u_content)
```

## Format danych

### Portale JSON

```json
[
    {
        "url": "http://portal.example.com/c/",
        "mac": "00:1A:79:XX:XX:XX",
        "name": "Nazwa Portalu"
    }
]
```

### Wynik testu

```json
{
    "status": "WORKING",
    "url": "http://portal.example.com/c/",
    "mac": "00:1A:79:XX:XX:XX",
    "info": {
        "channels": 1500,
        "has_pl": true,
        "expires": "2024-12-31",
        "summary": "ACTIVE | PL: TAK | Exp: 2024-12-31"
    },
    "channels": [...]
}
```

## Wymagania

- Python 3.7+
- requests
- colorama

## Konfiguracja

Główne parametry konfiguracyjne w `stalker-portal-tests.py`:

```python
TIMEOUT = 15          # Czas oczekiwania na odpowiedź
MAX_THREADS = 3       # Liczba równoległych testów
TEST_ONLY_POLISH = True  # Testuj tylko portale z polskimi kanałami
```

## Przykładowe wyniki

```
--- Stalker Portal Tester ---

[HIT] [PL!] http://portal.example.com/c/ | ACTIVE | PL: TAK | Exp: 2024-12-31
[HIT] [NO-PL] http://portal2.example.com/c/ | ACTIVE | PL: NIE | Exp: 2024-12-31

=== ZAKOŃCZONO TESTOWANIE PORTALI ===
Znaleziono 2 działających portali
```

## Licencja

MIT License

## Współpraca

Pull requests są mile widziane! Proszę o otwieranie issue dla zgłaszania błędów.

## Disclaimer

Narzędzie przeznaczone wyłącznie do celów edukacyjnych i testowych. Użytkownik jest odpowiedzialny za zgodność z prawem lokalnym.
