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

#### `/etc/gre-bridge.sh` — Slate 7 (GL-BE3600)

```sh
#!/bin/sh
for i in $(seq 1 30); do
    ip link show wgclient1 >/dev/null 2>&1 && break
    sleep 2
done
sleep 5
ip link add gretap-home type gretap local 10.10.10.4 remote 10.10.10.1 ttl 64
ip link set gretap-home mtu 1380
ip link set gretap-home up
brctl addif br-lan gretap-home
```

#### `/etc/gre-bridge.sh` — Flint 3 (GL-BE9300)

```sh
#!/bin/sh
for i in $(seq 1 30); do
    ip link show wgserver >/dev/null 2>&1 && break
    sleep 2
done
sleep 5
ip link add gretap-travel type gretap local 10.10.10.1 remote 10.10.10.4 ttl 64
ip link set gretap-travel mtu 1380
ip link set gretap-travel up
brctl addif br-lan gretap-travel
```

Both are `chmod +x` and invoked from `/etc/rc.local` by a single line inserted
before `exit 0`:

```
/etc/gre-bridge.sh
```

#### Supporting config

```sh
# Slate 7 — hand DHCP authority to the Flint 3 (persisted via uci)
uci set dhcp.lan.ignore='1'
uci commit dhcp
/etc/init.d/dnsmasq restart

# Slate 7 — static LAN address inside the unified subnet
uci set network.lan.ipaddr='10.5.5.3'
uci commit network
/etc/init.d/network restart   # NOTE: this drops the GRETAP, see Known fragility
```

#### Verification

```sh
brctl show br-lan                 # gretap-* should be listed, state forwarding
ip -d link show gretap-home       # confirm local/remote endpoints and MTU
cat /tmp/dhcp.leases              # on Flint 3: bridged clients appear here
```

A device on the Slate 7's WiFi receiving a `10.5.5.x` lease from the Flint 3 is the
end-to-end proof the bridge works.

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

## Open work queue

Roughly in the order that makes sense to tackle.

### Quick wins (Home Assistant, now that the Pi is on the home LAN)

1. Add **Sensi** and **Flume** — both are plain cloud logins.
2. Check **Settings → Devices & Services → Discovered** for **Kasa** and **WiZ**.
   These require the Pi to be on the home LAN, which it now is; they should appear
   without manual configuration.
3. Finish the **eufy E340** feed: enable NAS/RTSP in the eufy app, note the stream
   URL, give the camera a DHCP reservation, then add via HA's **Generic Camera**
   integration. Some units drop the RTSP stream when idle — if that happens, it is a
   known model behaviour, not a misconfiguration.
4. Retry the **HA companion app** on iOS. It failed earlier while Safari worked, which
   points at mDNS auto-discovery rather than connectivity — enter
   `http://10.5.5.8:8123` manually instead of using discovery.

### Network parity work

5. **Fix the `rc.local` fragility first** (see Known fragility above). Redeclare the
   GRETAP natively in `/etc/config/network`. Do this before adding a second bridged
   router, since it doubles exposure to the failure.
6. **Configure the Mudi V2** as a second L2-bridged router, mirroring the Slate 7:
   GRETAP over WireGuard (peer `10.10.10.5`), bridged into `br-lan`, own DHCP
   disabled, static LAN address `10.5.5.4`. Star topology with the Flint 3 as hub —
   remote routers bridge to home, never to each other.
   - **Decide the cellular tradeoff first.** L2 bridging carries every LAN broadcast
     and multicast frame across the tunnel. With ~50 devices and a large camera
     fleet, mDNS/SSDP chatter is continuous, and on cellular that is metered data
     even when idle. Either apply multicast filtering at the bridge, or run the Mudi
     as an L3 client (Tier 2 below) instead.
   - Set its GRETAP MTU below 1380; cellular WAN MTU is typically lower than wired.
7. **Direct WireGuard clients** (phones, laptops without a travel router): assign each
   a `/32` from `10.5.5.20-29`, set the matching `AllowedIPs` on the Flint 3, and
   enable proxy ARP so the router answers ARP on their behalf:
   ```sh
   echo 1 > /proc/sys/net/ipv4/conf/br-lan/proxy_arp
   ```
   Persist it alongside the bridge config. Do **not** put a `10.5.5.x/24` on the
   `wgserver` interface — `br-lan` already owns that subnet and two interfaces
   claiming it creates routing ambiguity. Per-peer `/32` is the correct shape.
   - **Renumbering caution:** the GRETAP scripts hardcode `10.10.10.1` and
     `10.10.10.4`. Renumbering the WireGuard subnet wholesale breaks the bridge
     silently at next boot. Either leave router peers on `10.10.10.x` (they don't
     benefit from proxy ARP — they already have true L2, which is strictly better) or
     update both scripts in the same sitting.

## Design notes

### Two tiers of "appears to be home"

**Tier 1 — true L2 parity.** OpenWrt routers carry Ethernet frames over the tunnel
via GRETAP bridged into `br-lan`. Clients behind them get real Flint 3 DHCP leases and
full broadcast/multicast, so mDNS/SSDP discovery behaves exactly as at home. This is
genuine parity. Applies to: Slate 7, and Mudi V2 once configured.

**Tier 2 — L3 with home-looking addresses.** iOS and Android VPN frameworks are
packet-level only; no app can provide an L2 equivalent. Proxy ARP plus a `/32` from
the LAN range yields a home-looking address and working unicast, but multicast
discovery remains unavailable.

**Consequence:** a phone gets *better* parity by joining a travel router's WiFi than
by running WireGuard directly, because the router does the bridging. Since the Mudi V2
travels with the user, direct WireGuard on the phone is best treated as the fallback
for when the Mudi isn't present, not the primary path.

## Open questions

- **Is the Flint 3's IoT Network feature in use?** It appears in the LAN menu. If
  active it is a separate subnet, which directly contradicts the single-subnet goal.
  Needs an answer before the address plan can be called complete.
- **What is the Mudi V2's cellular data situation?** Determines whether it can be a
  Tier 1 bridged router or should stay Tier 2. See item 6 above.
- **Are the two `ESP_*` devices on the LAN running ESPHome, Tasmota, or stock
  firmware?** ESPHome devices integrate natively and would be among the easiest wins;
  worth identifying.

## Operational notes

- The HA admin password was lost once, forcing a full reflash and re-onboarding.
  Store the current credentials in a password manager.
- The Flint 3 has **Network Acceleration (hardware offload) enabled**, which by GL.iNet's
  own documentation breaks *Client Speed and Traffic Statistics*. Per-client
  throughput figures in the admin panel are unreliable while this is on — do not use
  them to diagnose whether traffic is flowing. Test with an actual connection instead.
- HAOS first boot is headless: HDMI goes black after boot, and the web UI is
  unreachable for 10–20+ minutes while the Core image downloads. This is normal, not
  a failure.
- Bulk transfers stalling while ping succeeds is the signature of an MTU problem
  across a tunnel, not a bandwidth problem.
