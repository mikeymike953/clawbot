# Project context

This repo holds two unrelated things:

1. **`app.py`** — a small Flask/Telegram bot deployed on Render. Untouched by the
   network work.
2. **`NETWORK.md`** — the home network and Home Assistant buildout reference.
   **Read this first** for anything involving the routers, WireGuard, subnets, or
   Home Assistant.

## Working agreement for the network buildout

- **`NETWORK.md` is the source of truth.** Update it when topology changes. It exists
  because sessions are disposable and the network state is not.
- **Never commit secrets.** No WireGuard private/public keys, no DDNS hostnames, no
  public IPs, no RTSP or integration credentials. Internal RFC1918 addressing and
  device models only. If a value would let someone reach or authenticate to
  something, it stays out of git.
- **Confirm before changing router config.** A bad change to the Flint 3 takes down
  the whole house's network, including the bridged travel routers. Read current state
  (`uci show`, `ip a`, `brctl show`) before writing.
- **Change the remote/travel router before the home router.** If something breaks,
  better it breaks on the box that isn't serving the house.

## Running locally vs. in a cloud container

Earlier sessions ran in an isolated cloud container with **no route to the home LAN** —
every command had to be relayed through the user by hand. A local session on the
user's machine can reach the network directly:

- `ssh root@10.5.5.1` — Flint 3 (home router)
- `ssh root@10.5.5.3` — Slate 7 (travel router)
- `curl http://10.5.5.8:8123` — Home Assistant

Verify reachability before assuming it; the user may be remote, in which case the
relay workflow applies again.

## Home Assistant API access

For direct queries against HA, create a long-lived access token in the HA UI
(profile → Security → Long-lived access tokens) and keep it in an untracked local
file or environment variable — **not** in this repo.
