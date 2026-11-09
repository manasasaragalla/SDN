# Generalized routing execution 3d429ec3e38a418da9080b346b56a0a9

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T14:01:32.322141+00:00
- **Completed:** 2026-11-05T14:01:59.754161+00:00
- **Duration:** 27.432s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** `MINIMIZE latency` (ms)
- **Hard constraints:** none

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-6ae1c9c34a35b4e433fc095cfb3f69590c31f1ca3d700b918e597f65c935e3f5` | `h1 → s1 → s2 → s4 → h4` | 2.238 | 10/10 | True | not recorded | False | 2217436498506130222 | SUCCEEDED |
- **latency measurement:** `VALID`; value `2.238` ms; run `822c5951-114b-4b28-9b99-94a939b2187c`
| `physical-dbcbec515afd50a9a9bcb9ccc6673ae7caf79530e8a4b11cb789d1642fae0909` | `h1 → s1 → s3 → s5 → s4 → h4` | 1.954 | 10/10 | True | not recorded | True | 13969212999030383102 | SUCCEEDED |
- **latency measurement:** `VALID`; value `1.954` ms; run `4f966937-0dc3-4668-b821-7a71b5ffdce5`

## Candidate evidence

### physical-6ae1c9c34a35b4e433fc095cfb3f69590c31f1ca3d700b918e597f65c935e3f5

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `822c5951-114b-4b28-9b99-94a939b2187c`
- **Probe operation ID:** `22d62641-c4de-47b1-b1fb-ff2c8446ac3a`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `2217436498506130222`; DPIDs `[1, 2, 4]`; readback 12/12
- **Observation:** `VALID` (optimization-observation)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Observation identity:** candidate `physical-6ae1c9c34a35b4e433fc095cfb3f69590c31f1ca3d700b918e597f65c935e3f5`, evaluation run `89ea26bd-8da8-45bf-9d2f-3f63bfb05d86`, request `d3be74bad134bab60ea1a3c805ec0a921a90904ecee000e9f4c0ee2be894f598`, plan `bbadb396f419c8827737e5180db57b7fbe179634fece38ea0182a2bbc71f096a`, path `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Probe snapshot fingerprints:** planned `cb12f6c059c6b4232830227f53314789c0a8b91e92cb3a19df3479897650d2f2`, fresh `7e698d6ac5d425f10335811d69b8d5a3b914a7ec3a3419912a73725b93a7b051`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T14:01:32.353515+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T14:01:32.341206+00:00; preflight_started_at=2026-11-05T14:01:32.341220+00:00; preflight_completed_at=2026-11-05T14:01:32.361404+00:00; compilation_completed_at=2026-11-05T14:01:32.361806+00:00; deployment_started_at=2026-11-05T14:01:32.361813+00:00; deployment_completed_at=2026-11-05T14:01:32.403048+00:00; measurement_started_at=2026-11-05T14:01:32.403063+00:00; measurement_completed_at=2026-11-05T14:01:41.436718+00:00; cleanup_started_at=2026-11-05T14:01:41.436744+00:00; cleanup_completed_at=2026-11-05T14:01:41.454067+00:00

Compiled probe rules:

```json
[
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 2,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s2"
  },
  {
    "dpid": 2,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s2"
  },
  {
    "dpid": 2,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s2"
  },
  {
    "dpid": 2,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s2"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  }
]
```

Raw candidate ping output:

```text
PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=3.41 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.46 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=2.21 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.54 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.97 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=1.99 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.77 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.92 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=2.33 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.78 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.458/2.238/3.410/0.557 ms

```

### physical-dbcbec515afd50a9a9bcb9ccc6673ae7caf79530e8a4b11cb789d1642fae0909

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `4f966937-0dc3-4668-b821-7a71b5ffdce5`
- **Probe operation ID:** `467ac2f6-2584-471c-ae2b-a40438719d48`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `13969212999030383102`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `VALID` (optimization-observation)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Observation identity:** candidate `physical-dbcbec515afd50a9a9bcb9ccc6673ae7caf79530e8a4b11cb789d1642fae0909`, evaluation run `89ea26bd-8da8-45bf-9d2f-3f63bfb05d86`, request `d3be74bad134bab60ea1a3c805ec0a921a90904ecee000e9f4c0ee2be894f598`, plan `bbadb396f419c8827737e5180db57b7fbe179634fece38ea0182a2bbc71f096a`, path `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Probe snapshot fingerprints:** planned `cb12f6c059c6b4232830227f53314789c0a8b91e92cb3a19df3479897650d2f2`, fresh `4b8320e40de83b6b1107442491155ca0785cd8ce566a27f06f9196dae6b1a8d0`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T14:01:41.473004+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T14:01:41.456830+00:00; preflight_started_at=2026-11-05T14:01:41.456843+00:00; preflight_completed_at=2026-11-05T14:01:41.481294+00:00; compilation_completed_at=2026-11-05T14:01:41.481601+00:00; deployment_started_at=2026-11-05T14:01:41.481603+00:00; deployment_completed_at=2026-11-05T14:01:41.536223+00:00; measurement_started_at=2026-11-05T14:01:41.536236+00:00; measurement_completed_at=2026-11-05T14:01:50.560179+00:00; cleanup_started_at=2026-11-05T14:01:50.560196+00:00; cleanup_completed_at=2026-11-05T14:01:50.582455+00:00

Compiled probe rules:

```json
[
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s3"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s5"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 4,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 4,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 4
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 4
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  }
]
```

Raw candidate ping output:

```text
PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.30 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.20 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=2.15 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.84 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.72 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.50 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.58 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=3.07 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.69 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.51 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.199/1.954/3.072/0.619 ms

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-dbcbec515afd50a9a9bcb9ccc6673ae7caf79530e8a4b11cb789d1642fae0909`
- **Selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Selection method:** `OBJECTIVE_RANKING`

| Candidate | latency value (ms) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-6ae1c9c34a35b4e433fc095cfb3f69590c31f1ca3d700b918e597f65c935e3f5` | 2.238 | CANDIDATE | True |
| `physical-dbcbec515afd50a9a9bcb9ccc6673ae7caf79530e8a4b11cb789d1642fae0909` | 1.954 | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- Selected by MINIMIZE of measured latency (1.954 ms) among 2 eligible candidate(s); equal values use ascending physical path fingerprint.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `f63332a4-d911-4811-a7ec-ac9fa0bd6d28`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `11249345014298102646`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 1.867 ms

Compiled final rules:

```json
[
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 3
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 1,
    "priority": 100,
    "match": {
      "in_port": 3,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s1"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s3"
  },
  {
    "dpid": 3,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s3"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 2
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s5"
  },
  {
    "dpid": 5,
    "priority": 100,
    "match": {
      "in_port": 2,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s5"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 4,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.1",
      "ipv4_dst": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 4,
      "eth_type": 2054,
      "arp_spa": "10.0.0.1",
      "arp_tpa": "10.0.0.4"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 1
      }
    ],
    "cookie": null,
    "label": "10.0.0.1->10.0.0.4 forward @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2048,
      "ipv4_src": "10.0.0.4",
      "ipv4_dst": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 4
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  },
  {
    "dpid": 4,
    "priority": 100,
    "match": {
      "in_port": 1,
      "eth_type": 2054,
      "arp_spa": "10.0.0.4",
      "arp_tpa": "10.0.0.1"
    },
    "actions": [
      {
        "type": "OUTPUT",
        "port": 4
      }
    ],
    "cookie": null,
    "label": "10.0.0.4->10.0.0.1 reverse @ s4"
  }
]
```

Raw final ping output:

```text
PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=0.866 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.10 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.64 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.45 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=2.54 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=3.07 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.51 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=0.999 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.53 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=2.96 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9032ms
rtt min/avg/max/mdev = 0.866/1.867/3.074/0.779 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T14:01:50.622202+00:00; preflight_started_at=2026-11-05T14:01:50.622216+00:00; preflight_completed_at=2026-11-05T14:01:50.671097+00:00; deployment_started_at=2026-11-05T14:01:50.671410+00:00; deployment_completed_at=2026-11-05T14:01:50.714594+00:00; connectivity_started_at=2026-11-05T14:01:50.714605+00:00; connectivity_completed_at=2026-11-05T14:01:59.753952+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
