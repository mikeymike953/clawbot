# Home Network & Home Assistant Reference

Working notes for the home network buildout. Internal addressing only — no keys,
DDNS hostnames, or public IPs recorded here.

## Design goal

**One subnet, everywhere.** Any device that connects — at home, behind a travel
router, or over WireGuard — should land on `10.5.5.0/24` and behave identically.
Workflows (bookmarks, app configs, discovery) never change based on location.

## Device inventory

| Device | Model | Role | Address |
|---|---|---|---|
| Flint 3 | GL-BE9300 | Home / main router, DHCP, WireGuard server | `10.5.5.1` |
| Slate 7 | GL-BE3600 | Travel router (L2-bridged to home) | `10.5.5.3` |
| Mudi V2 | GL-E750V2C6 | Mobile/cellular router — **not yet configured** | `10.5.5.4` (reserved) |
| AP | GL-MT3000 | Access point | `10.5.5.2` |
| Home Assistant | Raspberry Pi 4 B (2GB) | HAOS 18.1, `rpi4-64` image | `10.5.5.8` |
| NAS | WD MyCloud EX2 Ultra | File storage only (32-bit ARM — cannot run HA) | `10.5.5.5` |
| Pi-hole | — | DNS | `10.5.5.53` |

## Address plan

| Range | Purpose |
|---|---|
| `.1` – `.19` | Infrastructure (routers, APs, HA, NAS) |
| `.20` – `.29` | Direct WireGuard clients (phones, laptops) via proxy ARP |
| `.30` – `.99` | Static device reservations |
| `.100` – `.247` | DHCP pool (Flint 3: start 100, limit 148, 720m lease) |
| `.248` – `.254` | Existing device reservations — **partially occupied**, check before assigning |

WireGuard tunnel transport subnet is `10.10.10.0/24`. This stays as plumbing and is
intentionally *not* user-facing:

- `10.10.10.1` — Flint 3 (`wgserver`, listen port 10255)
- `10.10.10.4` — Slate 7 (`wgclient1`)
- `10.10.10.5` — Mudi V2 (planned)

## Two tiers of "appears to be home"

### Tier 1 — true L2 parity (routers)

OpenWrt-based routers can carry Ethernet frames over the WireGuard tunnel via a
GRETAP interface bridged into `br-lan`. Devices behind them get real DHCP leases
from the Flint 3 and full broadcast/multicast, so mDNS/SSDP discovery works exactly
as it does at home. **This is genuine parity.** Slate 7 has this; Mudi V2 should get
identical treatment.

### Tier 2 — L3 with home-looking addresses (phones, laptops)

iOS/Android VPN frameworks are packet-level only — no L2 equivalent exists, no app
can change this. Best achievable: assign each peer a `/32` out of `10.5.5.20-29` and
enable proxy ARP on the Flint 3's `br-lan` so it answers ARP on their behalf.
Unicast works (reaching `10.5.5.8:8123`, etc.); multicast discovery does not.

**Implication:** for a phone, joining the Mudi V2's WiFi gives *better* parity than
connecting it directly via WireGuard, because the Mudi does the L2 bridging. Direct
WireGuard on the phone is the fallback for when the Mudi isn't present.

## Slate 7 ↔ Flint 3 bridge (built, working)

GRETAP tunnel over the existing WireGuard link, bridged into `br-lan` on both ends,
with the Slate 7's own DHCP disabled so the Flint 3 is sole DHCP authority.

Flint 3 (`10.10.10.1`) — `gretap-travel`, MTU 1380, bridged into `br-lan`
Slate 7 (`10.10.10.4`) — `gretap-home`, MTU 1380, bridged into `br-lan`

Both recreate at boot via `/etc/gre-bridge.sh` called from `/etc/rc.local`. The
script waits for the WireGuard interface to exist before building the tunnel.

Slate 7 DHCP disabled with: `uci set dhcp.lan.ignore='1'` (persisted).

### Known fragility

`rc.local` only runs at **boot**. Running `/etc/init.d/network restart` rebuilds
`br-lan` from saved config, which silently drops the manually-added GRETAP — and
because the Slate 7's DHCP is off, its clients then get no address at all. A full
power cycle recovers it; `network restart` does not.

**Cleanup candidate:** redeclare the tunnel natively in `/etc/config/network` as a
`gretap` proto interface with `br-lan` membership, so it is rebuilt declaratively by
`ifup`/`network restart` instead of depending on the `rc.local` hook. Needs syntax
verified against GL.iNet's firmware before switching over.

## MTU chain

WireGuard interfaces run at MTU 1420; GRETAP set to 1380 to leave headroom for GRE
encapsulation on top. Undersizing this matters — an oversized MTU produces stalled
bulk transfers while small packets (ping) still pass, which is a confusing failure
mode to diagnose.

Cellular WANs typically have lower MTU than wired, so the Mudi V2 will likely need
its GRETAP MTU set below 1380.

## Home Assistant integration status

| Integration | Status | Notes |
|---|---|---|
| Ring | added | Cloud login |
| Sensi | pending | Cloud login (thermostat) |
| Flume | pending | Cloud login (water monitor) |
| Kasa (HS100) | pending | Local, auto-discovered — needs HA on home LAN |
| WiZ | pending | Local, auto-discovered — needs HA on home LAN |
| eufy Floodlight Cam E340 | in progress | Native RTSP present on this unit despite conflicting vendor docs; RTSP credentials set in eufy app |
| Wyze (~8 cameras) | not started | Needs `docker-wyze-bridge` add-on + Wyze API ID/Key |
| Hubspace | not started | Needs HACS |
| MyQ | not started | Chamberlain blocks 3rd-party API; Shelly relay bypass is the reliable path |

### Hardware headroom

The Pi 4 at 2GB is fine for the cloud/local API integrations above. It is *not*
sized for continuous multi-camera recording or AI detection (Frigate). Keep the Wyze
bridge on-demand rather than 24/7. If continuous recording becomes a goal, that is a
second-box job.

## Ruled out as HA hosts

- **WD MyCloud EX2 Ultra** — Marvell Armada 385, 32-bit ARM (armv7). HA dropped
  armv7 support; no current builds exist for it. Dead end, not a workaround case.
- **Raspberry Pi 3 B+** — HAOS no longer ships an `rpi3` image, and 1GB RAM is below
  the 2GB minimum.
- **Flint 3 itself** — 1GB RAM shared with routing duties, and an HA crash would take
  down the entire network. Blast radius too large.
- **iPad** — iPadOS cannot host a persistent server process. Useful as a wall-mounted
  dashboard via the companion app's kiosk mode.
