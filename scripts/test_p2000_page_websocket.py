"""Local, read-only p2000.page WebSocket smoke test.

No API key is stored or printed. This test never touches Home Assistant and
never sends messages to TTS, Telegram, MQTT, or another service.

Install: py -m pip install "websockets>=14,<17"
Run:     py scripts/test_p2000_page_websocket.py
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from getpass import getpass
import json
import re

import websockets

ENDPOINT = "wss://api.p2000.page/api-/r/{regions}/d/brandweer"
REGIONS = re.compile(r"^(?:0[1-9]|1[0-9]|2[0-5])(?:~(?:0[1-9]|1[0-9]|2[0-5]))*$")


async def main() -> None:
    regions = (input("Regio's [06]: ").strip() or "06")
    if not REGIONS.fullmatch(regions):
        raise SystemExit("Ongeldige regiocodes. Voorbeeld: 06~17")
    key = getpass("p2000.page API-sleutel (onzichtbaar): ").strip()
    if not key:
        raise SystemExit("Geen sleutel ingevoerd.")

    print("Verbinding maken met p2000.page (geen sleutels in logs)...")
    try:
        async with websockets.connect(
            ENDPOINT.format(regions=regions),
            additional_headers={"X-Api-Key": key},
            open_timeout=15,
            ping_interval=20,
            ping_timeout=20,
            max_size=1_048_576,
        ) as websocket:
            print("WebSocket-handshake: OK")
            print("Luisteren maximaal 90 seconden; Ctrl+C stopt de test.")
            async with asyncio.timeout(90):
                async for payload in websocket:
                    try:
                        data = json.loads(payload)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(data, dict):
                        continue
                    kind = data.get("type")
                    if kind == "welkom":
                        print("Welkom ontvangen | verbindingen:", data.get("verbindingen"),
                              "| regiofilter:", regions)
                    elif kind == "melding":
                        item = data.get("melding")
                        if isinstance(item, dict):
                            print(
                                datetime.now(timezone.utc).isoformat(),
                                "| LIVE bericht | uid aanwezig:",
                                bool(item.get("uid")),
                                "| timestamp aanwezig:",
                                bool(item.get("timestamp")),
                                "| dienst:",
                                str(item.get("dienst", ""))[:30],
                            )
                    elif kind == "fout":
                        print("Server meldt een fout (details bewust verborgen).")
                    elif kind == "laatste":
                        print("Historie ontvangen; niet als LIVE behandeld.")
    except TimeoutError:
        print("Test beëindigd na 90 seconden. Geen live meldingen is niet per se een fout.")
    except websockets.exceptions.InvalidStatus as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        print("WebSocket-handshake geweigerd; HTTP-status:", code)
        if code in (401, 403):
            print("Controleer de sleutel, abonnementstoegang, IP-restricties en headerauthenticatie.")
    except websockets.exceptions.ConnectionClosed as exc:
        print("WebSocket gesloten; code:", getattr(exc, "code", None))
    except OSError:
        print("Netwerkverbinding mislukt (geen sleutel of URL afgedrukt).")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGestopt.")
