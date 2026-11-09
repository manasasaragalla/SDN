# Generalized routing execution 430b123f1aff4bddae0f8999ff08a431

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T13:21:50.390935+00:00
- **Completed:** 2026-11-05T13:22:18.020485+00:00
- **Duration:** 27.630s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** none
- **Hard constraints:** latency LTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-752a89d226d1360f0730ddaf5b4b454809c00b85da6543ac6b912d7437c4031e` | `h1 → s1 → s2 → s4 → h4` | 2.052 | 10/10 | True | not recorded | True | 17078067518657317768 | SUCCEEDED |
- **latency measurement:** `VALID`; value `2.052` ms; run `4ff62edb-20df-48eb-80d9-a03933f130a0`
- **Constraint constraint:0:latency:** `SATISFIED`; observed `2.052`; Observation satisfies the hard constraint.
| `physical-5ad60c907a5acb047766672d18a3574ce07b107f727e7427c96344dc9dbb6e5b` | `h1 → s1 → s3 → s5 → s4 → h4` | 2.13 | 10/10 | True | not recorded | False | 10281395895334653862 | SUCCEEDED |
- **latency measurement:** `VALID`; value `2.13` ms; run `7bdff705-a08a-4043-a43e-7a9a093d0118`
- **Constraint constraint:0:latency:** `SATISFIED`; observed `2.13`; Observation satisfies the hard constraint.

## Candidate evidence

### physical-752a89d226d1360f0730ddaf5b4b454809c00b85da6543ac6b912d7437c4031e

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `4ff62edb-20df-48eb-80d9-a03933f130a0`
- **Probe operation ID:** `0abc104c-dcbf-410d-a887-76261c5c53f0`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `17078067518657317768`; DPIDs `[1, 2, 4]`; readback 12/12
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Probe snapshot fingerprints:** planned `fe1380693d15a44cb1d5c3bd5fa0fc19c354f6932d88dbdc7d157796ae76a661`, fresh `118bccc146f20e1732257d5084cffbe1ac95ebc987f9a6b049aba5b31f609200`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:21:50.421526+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:21:50.406340+00:00; preflight_started_at=2026-11-05T13:21:50.406355+00:00; preflight_completed_at=2026-11-05T13:21:50.428659+00:00; compilation_completed_at=2026-11-05T13:21:50.428951+00:00; deployment_started_at=2026-11-05T13:21:50.428954+00:00; deployment_completed_at=2026-11-05T13:21:50.468235+00:00; measurement_started_at=2026-11-05T13:21:50.468251+00:00; measurement_completed_at=2026-11-05T13:21:59.532593+00:00; cleanup_started_at=2026-11-05T13:21:59.532613+00:00; cleanup_completed_at=2026-11-05T13:21:59.551077+00:00

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=4.38 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.15 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=2.14 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.00 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=2.37 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=1.40 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.57 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=1.48 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.32 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.72 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9017ms
rtt min/avg/max/mdev = 1.316/2.052/4.382/0.847 ms

```

### physical-5ad60c907a5acb047766672d18a3574ce07b107f727e7427c96344dc9dbb6e5b

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `7bdff705-a08a-4043-a43e-7a9a093d0118`
- **Probe operation ID:** `88976cca-5981-4ae4-89f9-74e1daf2e329`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `10281395895334653862`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Probe snapshot fingerprints:** planned `fe1380693d15a44cb1d5c3bd5fa0fc19c354f6932d88dbdc7d157796ae76a661`, fresh `130424099fcde9d9981891c0f84ccc0616086a8a31044026b053b37c614d8d29`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:21:59.601635+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:21:59.553102+00:00; preflight_started_at=2026-11-05T13:21:59.553110+00:00; preflight_completed_at=2026-11-05T13:21:59.628033+00:00; compilation_completed_at=2026-11-05T13:21:59.628690+00:00; deployment_started_at=2026-11-05T13:21:59.628702+00:00; deployment_completed_at=2026-11-05T13:21:59.769548+00:00; measurement_started_at=2026-11-05T13:21:59.769580+00:00; measurement_completed_at=2026-11-05T13:22:08.797585+00:00; cleanup_started_at=2026-11-05T13:22:08.797636+00:00; cleanup_completed_at=2026-11-05T13:22:08.851803+00:00

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=2.75 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.21 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=3.30 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=3.26 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=0.884 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.00 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.39 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=1.06 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=2.79 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=2.66 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9014ms
rtt min/avg/max/mdev = 0.884/2.130/3.302/0.886 ms

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-752a89d226d1360f0730ddaf5b4b454809c00b85da6543ac6b912d7437c4031e`
- **Selected path:** `h1 → s1 → s2 → s4 → h4`
- **Selection method:** `NEUTRAL_DETERMINISTIC`

| Candidate | constraints value (metric unit) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-752a89d226d1360f0730ddaf5b4b454809c00b85da6543ac6b912d7437c4031e` | None | CANDIDATE | True |
| `physical-5ad60c907a5acb047766672d18a3574ce07b107f727e7427c96344dc9dbb6e5b` | None | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `a2771cf4-b444-49e8-8493-0f9301b4f6a3`
- **Final selected path:** `h1 → s1 → s2 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `6413571643363004352`, DPIDs `[1, 2, 4]`)
- **Verified rules:** 12 / 12 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 1.994 ms

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

Raw final ping output:

```text
PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.27 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.26 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.87 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=1.15 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.66 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.82 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=2.94 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.21 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.95 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.80 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.150/1.994/2.941/0.557 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T13:22:08.898140+00:00; preflight_started_at=2026-11-05T13:22:08.898153+00:00; preflight_completed_at=2026-11-05T13:22:08.950824+00:00; deployment_started_at=2026-11-05T13:22:08.951144+00:00; deployment_completed_at=2026-11-05T13:22:08.997061+00:00; connectivity_started_at=2026-11-05T13:22:08.997076+00:00; connectivity_completed_at=2026-11-05T13:22:18.020194+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
