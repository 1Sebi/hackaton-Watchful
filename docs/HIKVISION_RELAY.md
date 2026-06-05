# 🔌 Hikvision relay (ACT) — VALIDATED on the real NVR

> Hardware-lane result for **PAS 10**. The relay trigger was run against the real
> NVR2 and the output state was observed changing — the cloud session can't do
> this. Use this to make `backend/actions/hikvision.py` work on the first try.

## Proven working ✅

On **NVR2 (192.168.0.60:80)**, ISAPI digest auth, output 1:

```
state before : inactive
PUT /ISAPI/System/IO/outputs/1/trigger  body <IOPortData><outputState>high</outputState></IOPortData>  -> 200
state during : active        <-- relay actually toggled
PUT .../1/trigger  body <IOPortData><outputState>low</outputState></IOPortData>   -> 200
state after  : inactive
```

So the full Perceive→Understand→**Act** loop's action stage is real, not theoretical.

## The working call (digest auth)

```
GET  /ISAPI/System/IO/outputs                 # list outputs
GET  /ISAPI/System/IO/outputs/<id>/status     # <ioState>active|inactive</ioState>
PUT  /ISAPI/System/IO/outputs/<id>/trigger    # body: <IOPortData><outputState>high|low</outputState></IOPortData>
```
Auth: `requests.auth.HTTPDigestAuth(user, pass)`. To pulse: set `high`, sleep, set `low`.

## Output map on NVR2

| id | kind | notes |
|---|---|---|
| **1** | **local NVR relay** | `IOType=local`, default low, PowerOn pulse 5000ms. This is the brief's "relay 1" — use it for the demo (team likely wired a demo LED here). |
| 201, 301, 601, 701, 901, 1001, 1301, 1501 | camera relays (proxied) | each maps to a camera's onboard IO (e.g. 201 → 192.168.0.61 innerIOPortID 1). |
| 203, 303, ... (x03) | secondary | `GET status` returns **403** — skip. |

## Gotchas (affect PAS 10)

1. **NVR1 (.59) ISAPI :80 is refused** — relays there are NOT reachable on port 80.
   Use NVR2 (.60) for relay actions, or find .59's real HTTP port first.
2. **Confirm the physical wiring before firing in a demo** — output 1 actuates
   whatever is on the NVR alarm-out terminal. Read `/status` before/after to prove
   the toggle even if nothing visible is wired.
3. Default PowerOn pulse for output 1 is 5000ms — fine for the brief's "relay 1
   for N seconds" pattern; or drive high/low manually for exact duration.

## Tool
`scripts/hikvision_io.py` — read-only by default; `--trigger <id> --confirm` to fire
(double opt-in so it never actuates hardware by accident). Reads creds from `.env`.

## Suggested `backend/actions/hikvision.py` shape (for PAS 10)
```python
class HikvisionRelay:
    def __init__(self, ip, user, password, port=80):
        self.base = f"http://{ip}:{port}"
        self.auth = HTTPDigestAuth(user, password)
    def set(self, output_id, high: bool):
        xml = f"<IOPortData><outputState>{'high' if high else 'low'}</outputState></IOPortData>"
        return requests.put(f"{self.base}/ISAPI/System/IO/outputs/{output_id}/trigger",
                            auth=self.auth, data=xml, timeout=8).status_code
    def pulse(self, output_id, seconds):
        self.set(output_id, True); time.sleep(seconds); self.set(output_id, False)
```
Verified against NVR2 output 1.
