# Hikvision ISAPI — relay & snapshot cheatsheet

Quick reference for driving a Hikvision camera/NVR over **ISAPI** (HTTP, Digest
auth). Used by [`backend/actions/hikvision.py`](../backend/actions/hikvision.py).

## Auth
- **HTTP Digest** with the camera admin user (default `admin`).
- Base URL: `http://<CAM_IP>` (HTTPS if enabled).
- Most write ops are `PUT` with a small XML body.

## Relay / alarm output (what we use for the demo)

Trigger a physical relay output (drives a light, buzzer, lock, LED…):

```
PUT http://<ip>/ISAPI/System/IO/outputs/<port>/trigger
Content-Type: application/xml

<IOPortData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <outputState>high</outputState>   <!-- high = on, low = off -->
</IOPortData>
```

`<port>` is 1-based (output 1 = `.../outputs/1/trigger`).

curl example:
```bash
curl --digest -u admin:PASS -X PUT \
  "http://192.168.1.64/ISAPI/System/IO/outputs/1/trigger" \
  -H "Content-Type: application/xml" \
  --data '<IOPortData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema"><outputState>high</outputState></IOPortData>'
```

In code:
```python
from backend.actions.hikvision import HikvisionClient
hv = HikvisionClient(ip="192.168.1.64", user="admin", password="PASS")
hv.relay_set(port=1, state="high", duration=3)   # on for 3s, then auto-off
hv.pulse(port=1, duration=2)                       # convenience on->off
```

## List I/O outputs
```
GET http://<ip>/ISAPI/System/IO/outputs
GET http://<ip>/ISAPI/System/IO/outputs/<port>/status
```

## Snapshot (JPEG still) — handy for event evidence
```
GET http://<ip>/ISAPI/Streaming/channels/<chan>/picture
# chan: 101 = main stream, 102 = substream
```

## RTSP live stream (for VIDEO_SOURCE)
```
rtsp://<user>:<pass>@<ip>:554/Streaming/Channels/101   # main (HD)
rtsp://<user>:<pass>@<ip>:554/Streaming/Channels/102   # sub (faster)
```

## Device info / reboot
```
GET  http://<ip>/ISAPI/System/deviceInfo
PUT  http://<ip>/ISAPI/System/reboot
```

## Notes & gotchas
- Digest (not Basic): the first request gets a `401` + `WWW-Authenticate`; the
  client re-sends with the digest header. `requests.auth.HTTPDigestAuth` does
  this automatically.
- Some models expose outputs under `/ISAPI/System/IO/outputs/<port>/trigger`,
  others only support alarm I/O via the NVR — check `GET .../outputs` first.
- A `200 OK` with an `<ResponseStatus>` body of `statusCode 1` = success.
- For the demo without a relay handy, point an LED USB dongle or just use the
  `webhook`/`log` actions — same dispatcher path.
