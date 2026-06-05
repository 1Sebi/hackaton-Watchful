# 📷 Real Camera Access — validated against the live ThePlace NVRs

> **FOR THE AGENT WORKING ON `main`:** This was produced on a *local* machine
> that is on the venue LAN and **can reach the real Hikvision NVRs** — something
> a cloud session cannot do. Your `backend/core/video_source.py` was tested
> against the real cameras here (not just a webcam). Read §1 (it works) and §4
> (gotchas that affect PAS 8/10/11). Credentials are **not** in git — see §5.

## 1. TL;DR — your VideoSource works on real cameras ✅

`backend/core/video_source.py` (commit on main) was run against a real RTSP
stream from NVR1 cam5:

```
VideoSource('rtsp://admin:***@192.168.0.59:554/Streaming/Channels/502')
  -> 640x360 @ 20fps,  120/120 frames ok,  effective 22.7 FPS,  0 drops
```

No code change required to capture. Two hardening notes in §4.

## 2. The two NVRs

| NVR | IP | RTSP port | ISAPI HTTP (port 80) |
|---|---|---|---|
| NVR1 | `192.168.0.59` | 554 ✅ | **refused** ❌ (see §4.4) |
| NVR2 | `192.168.0.60` | 554 ✅ | works ✅ (`/ISAPI/Streaming/channels` → 200) |

We are NOT on the camera subnet (laptop is `192.168.200.x`, cameras on
`192.168.0.x`) but routing works — pings + RTSP succeed across subnets.

## 3. RTSP URL scheme + camera map

```
rtsp://admin:<password>@<ip>:554/Streaming/Channels/<C>
  <C> = camera*100 + stream      stream: 1 = main (3840x2160 ~16fps),
                                          2 = sub  (640x360 ~20-30fps)
```
**Use the SUB stream (x02) for detection** — main is 4K and will choke CPU YOLO.

**NVR1 (192.168.0.59) — 8 cams:**
| cam | view | | cam | view |
|---|---|---|---|---|
| 1 | w entrance | | 5 | **restaurant SW (people!)** |
| 2 | lobby | | 6 | north parking (outdoor) |
| 3 | east exit (glass) | | 7 | lobby bar |
| 4 | stairs (c2-c1) | | 8 | lounge |

**NVR2 (192.168.0.60) — ~14 cams:**
| cam | view | | cam | view |
|---|---|---|---|---|
| 1 | conference SE | | 10 | bar |
| 2 | marble lobby | | 12 | west -1 entry (parking) |
| 3 | **jacuzzi / pool** 🛁 | | 13 | lobby |
| 4 | dishwashers | | 14 | (no signal / gray) |
| 5 | event hall N | | 15 | gym entrance |
| 6 | restaurant bar | | 16 | wine cellar |
| 7 | reception computers | | — | (cam 8, 11 = no stream) |
| 9 | lobby bar | | | |

**Best demo targets:** NVR2 cam3 = the literal "jacuzzi" from the brief;
NVR1 cam5 = a busy restaurant (real people → person/pose detection).

## 4. Gotchas (these bite — verified live)

**4.1 First frames are gray/partial.** The first ~3-5 `read()`s after open return
a low-variance/partial frame until the decoder hits a keyframe. Fine for the
continuous agent loop, but any *snapshot* endpoint (e.g. `/stream` thumbnail,
predicate-compiler preview) should warm up: discard the first ~10 frames.

**4.2 URL-encode the password.** Passwords contain `@` and `$` →
`@`→`%40`, `$`→`%24`. e.g. `p@ss$word` → `p%40ss%24word`.
`urllib.parse.quote(pw, safe="")` handles it. (Your VideoSource takes a full URL,
so whoever builds the URL must encode.)

**4.3 Harden RTSP transport (recommended, not required).** Set this BEFORE the
first `cv2` import so FFmpeg uses TCP (not lossy UDP) and fails fast on a dead
stream — prevents artifacts ("PPS id out of range" on some HEVC cams) and infinite
hangs:
```python
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                      "rtsp_transport;tcp|stimeout;8000000")
```

**4.4 ISAPI on NVR1 (.59) port 80 is REFUSED — affects PAS 10.** The Hikvision
relay/action layer talks ISAPI over HTTP. `.60:80` works (digest auth, 200), but
`.59:80` actively refuses. Before building relays on .59: find its real HTTP port
or confirm relays live on .60. Don't assume port 80 everywhere.

**4.5 Some channels are dead/HEVC.** NVR2 cam 8 & 11 = no stream; cam 14 = gray;
a couple are HEVC and emit decoder warnings on the sub-stream — skip/guard them.

## 5. Credentials (NOT in git)

Passwords are in the team WhatsApp and in a local `.env` (gitignored). Structure:
```
NVR1_IP=192.168.0.59      NVR1_USER=admin   NVR1_PASS=<see WhatsApp>
NVR2_IP=192.168.0.60      NVR2_USER=admin   NVR2_PASS=<see WhatsApp>
# for the pipeline default (sub-stream), URL-encode the password:
VIDEO_SOURCE=rtsp://admin:<encoded-pass>@192.168.0.59:554/Streaming/Channels/502
```

## 6. Tools used to produce this (added under `scripts/`)

| script | purpose |
|---|---|
| `scripts/probe_rtsp.py` | grab 1 frame from a channel, save snapshot |
| `scripts/list_channels.py` | list NVR channels via ISAPI |
| `scripts/contact_sheet.py` | tile a thumbnail from every camera into one image |
| `scripts/live_view.py` | plain live viewer (q=quit, s=snapshot) |
| `scripts/validate_video_source.py` | run the project's VideoSource against a real camera + FPS |

— produced from the `experiment/pose-handraise` branch (parallel hardware-validation lane).
