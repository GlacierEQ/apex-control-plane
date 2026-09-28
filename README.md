# apex-control-plane

The universal control plane. One registry, every host.

## What this is

The operator-administration control surface that used to live only at
`~/.apex` on one machine, with 134 Android-Termux paths hardcoded into it. Those
paths made it unusable on any device but a Termux phone. They are now variables.

| was | now |
|---|---|
| `/data/data/com.termux/files/home` | `${HOME}` |
| `/data/data/com.termux` | `${TERMUX_PREFIX}` |
| `/sdcard/Download` | `${DEVICE_DOWNLOADS}` |
| `/sdcard` | `${DEVICE_STORAGE}` |

156 references across 43 configs. Zero literals.

## The rule

**Code, definitions, and configuration live here. Secrets never do. Instance
state does not.**

- config, routers, surfaces, schemas → this repo
- provider keys → keychain / vault, referenced by `${VAR}` name
- live state, continuity heads, receipts → the control plane database
- append-only history and hash chains → the ledger

A config that resolves on one host and silently points nowhere on another is the
defect this prevents. So resolution is *reported*, never assumed.

## Usage

```sh
python3 tools/resolve.py                    # report for this host
python3 tools/resolve.py --device termux    # report for the tablet
python3 tools/resolve.py --json             # machine-readable
```

Exit `0` = every reference resolves and exists. Exit `1` = references are absent
on this host (expected on a partial host). Exit `2` = the registry is malformed.

## Adding a device

Create `devices/<name>.json`:

```json
{
  "device": "workstation",
  "host": "linux",
  "vars": { "DEVICE_DOWNLOADS": "/home/op/Downloads" }
}
```

Then `python3 tools/resolve.py --device workstation`. CI runs every profile.

## What CI enforces

1. all 43 configs parse
2. **no hardcoded platform path** — the original defect
3. no committed secret
4. every `${VAR}` has a definition in a device profile or as a host fact
5. a resolution report per device

Absent paths do **not** fail the build. A declared key that is absent on the
MacBook and present on the tablet is the correct shape; a fake path is not.

## Current state

| | |
|---|---|
| configs | 43 |
| path references | 156 |
| literal Android paths | 0 |
| devices | macbook, termux |
| resolves present on this host | 28 |
| absent on this host | 128 — the Android-side surface, declared not faked |

## Source

Written from `~/.apex` on a MacBook Air. Originals retained at `~/.apex`;
per-file pre-rewrite backups in the session that produced this.
