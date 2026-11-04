"""Small Home Assistant client: websocket calls and REST flows.

Token, first found wins:
  1. $HA_TOKEN
  2. homeassistant.token_file in site.yaml (a line HA_TOKEN=..., keep it gitignored)
  3. homeassistant.token_command (e.g. "op read op://Private/HomeAssistantToken/credential");
     this runs once per process, so a password manager prompts once, not on every call
"""
import json
import os
import shlex
import subprocess
import urllib.request

import websockets

_token_cache = {}


def token(ha):
    if os.environ.get("HA_TOKEN"):
        return os.environ["HA_TOKEN"]
    if "t" in _token_cache:
        return _token_cache["t"]
    f = ha.get("token_file")
    if f and f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("HA_TOKEN="):
                _token_cache["t"] = line.split("=", 1)[1].strip()
                return _token_cache["t"]
    cmd = ha.get("token_command")
    if cmd:
        _token_cache["t"] = subprocess.run(shlex.split(cmd), check=True, capture_output=True,
                                           text=True).stdout.strip()
        return _token_cache["t"]
    raise SystemExit("no Home Assistant token: set HA_TOKEN, or homeassistant.token_file / "
                     "token_command in site.yaml")


def ws_url(ha):
    url = ha.get("url")
    if not url:
        raise SystemExit("homeassistant.url missing in site.yaml (e.g. http://192.168.1.10:8123)")
    url = url.rstrip("/")
    if url.startswith("http"):
        url = "ws" + url[4:]
    return url if url.endswith("/api/websocket") else url + "/api/websocket"


def rest_url(ha):
    return ws_url(ha).replace("ws", "http", 1).removesuffix("/api/websocket")


class HA:
    """Authenticated websocket session. Use: async with HA(site.ha) as ha: await ha.call({...})"""

    def __init__(self, ha):
        self.cfg, self.n, self.ws = ha, 0, None

    async def __aenter__(self):
        self._conn = websockets.connect(ws_url(self.cfg), max_size=64 * 1024 * 1024)
        self.ws = await self._conn.__aenter__()
        await self.ws.recv()  # auth_required
        await self.ws.send(json.dumps({"type": "auth", "access_token": token(self.cfg)}))
        if json.loads(await self.ws.recv()).get("type") != "auth_ok":
            raise SystemExit("Home Assistant: auth failed (check the token)")
        return self

    async def __aexit__(self, *exc):
        await self._conn.__aexit__(*exc)

    async def raw(self, msg):
        """Send one message; return the whole result message (success or not)."""
        self.n += 1
        await self.ws.send(json.dumps(dict(msg, id=self.n)))
        while True:
            r = json.loads(await self.ws.recv())
            if r.get("id") == self.n and r.get("type") == "result":
                return r

    async def call(self, msg):
        r = await self.raw(msg)
        if not r["success"]:
            raise SystemExit(f"HA error {r['error']} for {msg}")
        return r["result"]

    def rest(self, method, path, body=None):
        req = urllib.request.Request(rest_url(self.cfg) + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token(self.cfg)}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")

    def run_flow(self, kind, start, steps):
        """Drive a config or options flow over REST; steps are the user_input dicts in order."""
        base = f"/api/config/config_entries/{kind}"
        r = self.rest("POST", base, start)
        for user_input in steps:
            if r.get("type") not in ("form", "menu"):
                break
            r = self.rest("POST", f"{base}/{r['flow_id']}", user_input)
        if r.get("type") not in ("create_entry", "abort"):
            raise SystemExit(f"flow {start} ended in {r.get('type')}: {r.get('errors')} {r.get('step_id')}")
        return r


async def blink(ha_cfg, entity_id, times=3, seconds=1.0):
    """Flash a light so someone on site can say which one it is; restore its state after."""
    import asyncio
    async with HA(ha_cfg) as ha:
        before = ha.rest("GET", f"/api/states/{entity_id}")
        domain = entity_id.split(".")[0]
        on, off = (f"/api/services/{domain}/turn_on", f"/api/services/{domain}/turn_off")
        was_on = before["state"] == "on"
        for _ in range(times):
            ha.rest("POST", off if was_on else on, {"entity_id": entity_id})
            await asyncio.sleep(seconds)
            ha.rest("POST", on if was_on else off, {"entity_id": entity_id})
            await asyncio.sleep(seconds)
        if was_on and before["attributes"].get("brightness") is not None:
            ha.rest("POST", on, {"entity_id": entity_id, "brightness": before["attributes"]["brightness"]})
        return before["state"]
