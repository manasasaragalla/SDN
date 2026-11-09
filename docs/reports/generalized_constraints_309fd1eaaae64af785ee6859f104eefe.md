# Generalized routing execution 309fd1eaaae64af785ee6859f104eefe

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T13:16:56.493747+00:00
- **Completed:** 2026-11-05T13:17:20.941771+00:00
- **Duration:** 24.448s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** none
- **Hard constraints:** latency LTE, bandwidth GTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |
| `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed` | `h1 → s1 → s3 → s5 → s4 → h4` | 2.601 | 10/10 | True | not recorded | True | 400952379930669106 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `46.155964276701596` Mbps; run `9684f8e1-d46a-424f-9faf-f862054dc3df`
- **latency measurement:** `VALID`; value `2.601` ms; run `29474bcc-c4d8-44dc-b8eb-74802612c8f7`
- **Constraint constraint:0:latency:** `SATISFIED`; observed `2.601`; Observation satisfies the hard constraint.
- **Constraint constraint:1:bandwidth:** `SATISFIED`; observed `46.155964276701596`; Observation satisfies the hard constraint.

## Candidate evidence

### physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `not created`
- **Probe operation ID:** `not created`
- **Preflight:** `SKIPPED_INFEASIBLE`
- **Deployment:** `NOT_REACHED`; cookie `None`; DPIDs `None`; readback None/None
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `NOT_REACHED`; remaining flows `None`
- **Skipped:** Candidate is statically infeasible: Known physical path capacity cannot satisfy a bandwidth lower bound.
- **Probe snapshot fingerprints:** planned `7eaf332e8816be81a8ef41892e1dcc829c67f1cfc9e828e10a555edb260bfb89`, fresh `6c4f5314ff9f1e370a2da459ded3686a29997135478c6e88cbd59e86cd59eafa`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:16:56.527851+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:16:56.511920+00:00; preflight_started_at=2026-11-05T13:16:56.511937+00:00; preflight_completed_at=2026-11-05T13:16:56.543599+00:00; probe_completed_at=2026-11-05T13:16:56.543609+00:00

### physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `9684f8e1-d46a-424f-9faf-f862054dc3df`
- **Probe operation ID:** `84bb6f32-c599-4006-96fb-e50e9b982cef`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `400952379930669106`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Probe snapshot fingerprints:** planned `7eaf332e8816be81a8ef41892e1dcc829c67f1cfc9e828e10a555edb260bfb89`, fresh `5aa35f769df1472768155884998ee8cdc19453038a03736307a52fdd0cde3857`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:16:56.557993+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:16:56.544392+00:00; preflight_started_at=2026-11-05T13:16:56.544397+00:00; preflight_completed_at=2026-11-05T13:16:56.568647+00:00; compilation_completed_at=2026-11-05T13:16:56.569112+00:00; deployment_started_at=2026-11-05T13:16:56.569117+00:00; deployment_completed_at=2026-11-05T13:16:56.626895+00:00; measurement_started_at=2026-11-05T13:16:56.626911+00:00; measurement_completed_at=2026-11-05T13:17:11.753026+00:00; cleanup_started_at=2026-11-05T13:17:11.753054+00:00; cleanup_completed_at=2026-11-05T13:17:11.779190+00:00

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.51 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.78 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=3.48 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.24 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=2.34 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.91 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=4.52 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=1.47 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=3.30 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.48 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9021ms
rtt min/avg/max/mdev = 1.469/2.601/4.517/0.948 ms

```

Raw candidate iperf3 output:

```text
{
	"start":	{
		"connected":	[{
				"socket":	5,
				"local_host":	"10.0.0.1",
				"local_port":	60812,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 13:16:57 GMT",
			"timesecs":	1793884617
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"bwpayhqd7phxoktcymbnoqxg522qazo374kc",
		"tcp_mss_default":	1448,
		"target_bitrate":	0,
		"fq_rate":	0,
		"sock_bufsize":	0,
		"sndbuf_actual":	87380,
		"rcvbuf_actual":	87380,
		"test_start":	{
			"protocol":	"TCP",
			"num_streams":	1,
			"blksize":	131072,
			"omit":	0,
			"duration":	5,
			"bytes":	0,
			"blocks":	0,
			"reverse":	0,
			"tos":	0,
			"target_bitrate":	0,
			"bidir":	0,
			"fqrate":	0
		}
	},
	"intervals":	[{
			"streams":	[{
					"socket":	5,
					"start":	0,
					"end":	1.001097,
					"seconds":	1.0010969638824463,
					"bytes":	6160384,
					"bits_per_second":	49229069.48880434,
					"retransmits":	2,
					"snd_cwnd":	118736,
					"snd_wnd":	1275392,
					"rtt":	21753,
					"rttvar":	876,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.001097,
				"seconds":	1.0010969638824463,
				"bytes":	6160384,
				"bits_per_second":	49229069.48880434,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.001097,
					"end":	2.001103,
					"seconds":	1.0000059604644775,
					"bytes":	5636096,
					"bits_per_second":	45088499.251601867,
					"retransmits":	2,
					"snd_cwnd":	114392,
					"snd_wnd":	1276928,
					"rtt":	18407,
					"rttvar":	410,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.001097,
				"end":	2.001103,
				"seconds":	1.0000059604644775,
				"bytes":	5636096,
				"bits_per_second":	45088499.251601867,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001103,
					"end":	3.001047,
					"seconds":	0.999943971633911,
					"bytes":	6029312,
					"bits_per_second":	48237198.651425146,
					"retransmits":	1,
					"snd_cwnd":	108600,
					"snd_wnd":	1276928,
					"rtt":	18056,
					"rttvar":	409,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001103,
				"end":	3.001047,
				"seconds":	0.999943971633911,
				"bytes":	6029312,
				"bits_per_second":	48237198.651425146,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.001047,
					"end":	4.001045,
					"seconds":	0.99999797344207764,
					"bytes":	5898240,
					"bits_per_second":	47186015.6251938,
					"retransmits":	2,
					"snd_cwnd":	101360,
					"snd_wnd":	1276928,
					"rtt":	16530,
					"rttvar":	392,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.001047,
				"end":	4.001045,
				"seconds":	0.99999797344207764,
				"bytes":	5898240,
				"bits_per_second":	47186015.6251938,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.001045,
					"end":	5.004338,
					"seconds":	1.0032930374145508,
					"bytes":	5898240,
					"bits_per_second":	47031045.009139478,
					"retransmits":	2,
					"snd_cwnd":	97016,
					"snd_wnd":	1276928,
					"rtt":	19246,
					"rttvar":	879,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.001045,
				"end":	5.004338,
				"seconds":	1.0032930374145508,
				"bytes":	5898240,
				"bits_per_second":	47031045.009139478,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}],
	"end":	{
		"streams":	[{
				"sender":	{
					"socket":	5,
					"start":	0,
					"end":	5.004338,
					"seconds":	5.004338,
					"bytes":	29622272,
					"bits_per_second":	47354550.392079838,
					"retransmits":	9,
					"max_snd_cwnd":	118736,
					"max_snd_wnd":	1276928,
					"max_rtt":	21753,
					"min_rtt":	16530,
					"mean_rtt":	18798,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.020701,
					"seconds":	5.004338,
					"bytes":	28966912,
					"bits_per_second":	46155964.2767016,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.004338,
			"seconds":	5.004338,
			"bytes":	29622272,
			"bits_per_second":	47354550.392079838,
			"retransmits":	9,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.020701,
			"seconds":	5.020701,
			"bytes":	28966912,
			"bits_per_second":	46155964.2767016,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	1.4445560109344007,
			"host_user":	0.074630549913086958,
			"host_system":	1.3697263931367765,
			"remote_total":	8.02118555706196,
			"remote_user":	0.558757913861574,
			"remote_system":	7.462427643200388
		},
		"sender_tcp_congestion":	"cubic",
		"receiver_tcp_congestion":	"cubic"
	}
}

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed`
- **Selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Selection method:** `NEUTRAL_DETERMINISTIC`

| Candidate | constraints value (metric unit) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736` | None | PROVEN_INFEASIBLE | False |
| `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed` | None | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `937584a3-0a91-4405-8db3-d449f7ad0e35`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `9688837111803103666`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 1.945 ms

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.43 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.68 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.28 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.14 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.99 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=1.76 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.62 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=1.97 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=2.48 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=2.11 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9017ms
rtt min/avg/max/mdev = 1.275/1.945/2.681/0.419 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T13:17:11.825419+00:00; preflight_started_at=2026-11-05T13:17:11.825431+00:00; preflight_completed_at=2026-11-05T13:17:11.876360+00:00; deployment_started_at=2026-11-05T13:17:11.876685+00:00; deployment_completed_at=2026-11-05T13:17:11.917267+00:00; connectivity_started_at=2026-11-05T13:17:11.917279+00:00; connectivity_completed_at=2026-11-05T13:17:20.941458+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
