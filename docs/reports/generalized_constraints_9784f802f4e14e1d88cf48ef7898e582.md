# Generalized routing execution 9784f802f4e14e1d88cf48ef7898e582

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T13:21:12.985382+00:00
- **Completed:** 2026-11-05T13:21:28.593305+00:00
- **Duration:** 15.608s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** none
- **Hard constraints:** bandwidth GTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-68303b0cc0beaa04960fce95471892fca9a573ec3a4419df41f9839a787d62bd` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |
| `physical-154d8cd69d822196aa4cf4b5c332618126f6e0a188afb87ad68a86cf85396b30` | `h1 → s1 → s3 → s5 → s4 → h4` | not recorded | not recorded | None | not recorded | True | 17720585221943930551 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `46.351419072939244` Mbps; run `a58b8b88-f35f-4366-a744-fc2df92140ea`
- **Constraint constraint:0:bandwidth:** `SATISFIED`; observed `46.351419072939244`; Observation satisfies the hard constraint.

## Candidate evidence

### physical-68303b0cc0beaa04960fce95471892fca9a573ec3a4419df41f9839a787d62bd

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `not created`
- **Probe operation ID:** `not created`
- **Preflight:** `SKIPPED_INFEASIBLE`
- **Deployment:** `NOT_REACHED`; cookie `None`; DPIDs `None`; readback None/None
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `NOT_REACHED`; remaining flows `None`
- **Skipped:** Candidate is statically infeasible: Known physical path capacity cannot satisfy a bandwidth lower bound.
- **Probe snapshot fingerprints:** planned `9998df8b1a82c3d3d81bc9db7befe8d462fc0199a6a28ffa6c3c16f5fec61cc2`, fresh `03f0b0ca4fb0b91aa633d52f73159fd2d11418392009b58e33639f2facb19de2`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:21:13.051352+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:21:13.026639+00:00; preflight_started_at=2026-11-05T13:21:13.026713+00:00; preflight_completed_at=2026-11-05T13:21:13.064339+00:00; probe_completed_at=2026-11-05T13:21:13.064361+00:00

### physical-154d8cd69d822196aa4cf4b5c332618126f6e0a188afb87ad68a86cf85396b30

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `a58b8b88-f35f-4366-a744-fc2df92140ea`
- **Probe operation ID:** `7ac69b90-4761-4798-b2fd-ffebf211e029`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `17720585221943930551`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Probe snapshot fingerprints:** planned `9998df8b1a82c3d3d81bc9db7befe8d462fc0199a6a28ffa6c3c16f5fec61cc2`, fresh `de952733da46d961e7edd8859f60a1f2b04691449da767415ff3dec354273b6e`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:21:13.084190+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:21:13.065029+00:00; preflight_started_at=2026-11-05T13:21:13.065033+00:00; preflight_completed_at=2026-11-05T13:21:13.108314+00:00; compilation_completed_at=2026-11-05T13:21:13.109577+00:00; deployment_started_at=2026-11-05T13:21:13.109594+00:00; deployment_completed_at=2026-11-05T13:21:13.259123+00:00; measurement_started_at=2026-11-05T13:21:13.259169+00:00; measurement_completed_at=2026-11-05T13:21:19.346301+00:00; cleanup_started_at=2026-11-05T13:21:19.346320+00:00; cleanup_completed_at=2026-11-05T13:21:19.364172+00:00

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

Raw candidate iperf3 output:

```text
{
	"start":	{
		"connected":	[{
				"socket":	5,
				"local_host":	"10.0.0.1",
				"local_port":	60068,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 13:21:14 GMT",
			"timesecs":	1793884874
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"rbuu3z537zhkofsvnpvrto6v2ogjql5uah5m",
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
					"end":	1.001197,
					"seconds":	1.0011969804763794,
					"bytes":	6422528,
					"bits_per_second":	51318796.402634755,
					"retransmits":	5,
					"snd_cwnd":	123080,
					"snd_wnd":	548352,
					"rtt":	21257,
					"rttvar":	598,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.001197,
				"seconds":	1.0011969804763794,
				"bytes":	6422528,
				"bits_per_second":	51318796.402634755,
				"retransmits":	5,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.001197,
					"end":	2.001079,
					"seconds":	0.99988198280334473,
					"bytes":	5505024,
					"bits_per_second":	44045390.113466777,
					"retransmits":	1,
					"snd_cwnd":	117288,
					"snd_wnd":	649216,
					"rtt":	19426,
					"rttvar":	374,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.001197,
				"end":	2.001079,
				"seconds":	0.99988198280334473,
				"bytes":	5505024,
				"bits_per_second":	44045390.113466777,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001079,
					"end":	3.001155,
					"seconds":	1.0000760555267334,
					"bytes":	6029312,
					"bits_per_second":	48230827.778988481,
					"retransmits":	1,
					"snd_cwnd":	111496,
					"snd_wnd":	650752,
					"rtt":	19129,
					"rttvar":	1069,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001079,
				"end":	3.001155,
				"seconds":	1.0000760555267334,
				"bytes":	6029312,
				"bits_per_second":	48230827.778988481,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.001155,
					"end":	4.001168,
					"seconds":	1.000012993812561,
					"bytes":	5898240,
					"bits_per_second":	47185306.882966727,
					"retransmits":	1,
					"snd_cwnd":	104256,
					"snd_wnd":	650752,
					"rtt":	16711,
					"rttvar":	344,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.001155,
				"end":	4.001168,
				"seconds":	1.000012993812561,
				"bytes":	5898240,
				"bits_per_second":	47185306.882966727,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.001168,
					"end":	5.003507,
					"seconds":	1.0023390054702759,
					"bytes":	5898240,
					"bits_per_second":	47075809.424239039,
					"retransmits":	5,
					"snd_cwnd":	97016,
					"snd_wnd":	650752,
					"rtt":	15960,
					"rttvar":	208,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.001168,
				"end":	5.003507,
				"seconds":	1.0023390054702759,
				"bytes":	5898240,
				"bits_per_second":	47075809.424239039,
				"retransmits":	5,
				"omitted":	false,
				"sender":	true
			}
		}],
	"end":	{
		"streams":	[{
				"sender":	{
					"socket":	5,
					"start":	0,
					"end":	5.003507,
					"seconds":	5.003507,
					"bytes":	29884416,
					"bits_per_second":	47781551.61969395,
					"retransmits":	13,
					"max_snd_cwnd":	123080,
					"max_snd_wnd":	650752,
					"max_rtt":	21257,
					"min_rtt":	15960,
					"mean_rtt":	18496,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.022152,
					"seconds":	5.003507,
					"bytes":	29097984,
					"bits_per_second":	46351419.072939247,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.003507,
			"seconds":	5.003507,
			"bytes":	29884416,
			"bits_per_second":	47781551.61969395,
			"retransmits":	13,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.022152,
			"seconds":	5.022152,
			"bytes":	29097984,
			"bits_per_second":	46351419.072939247,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	3.0306286064199361,
			"host_user":	0.10648332345973925,
			"host_system":	2.9240854832652547,
			"remote_total":	8.93179476907798,
			"remote_user":	1.2515634588069171,
			"remote_system":	7.6802313102710631
		},
		"sender_tcp_congestion":	"cubic",
		"receiver_tcp_congestion":	"cubic"
	}
}

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-154d8cd69d822196aa4cf4b5c332618126f6e0a188afb87ad68a86cf85396b30`
- **Selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Selection method:** `NEUTRAL_DETERMINISTIC`

| Candidate | constraints value (metric unit) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-68303b0cc0beaa04960fce95471892fca9a573ec3a4419df41f9839a787d62bd` | None | PROVEN_INFEASIBLE | False |
| `physical-154d8cd69d822196aa4cf4b5c332618126f6e0a188afb87ad68a86cf85396b30` | None | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `86819df9-4482-4a55-8da8-c2b27ffb2f63`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `13082058210504544536`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 2.635 ms

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=4.52 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.12 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=3.51 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.03 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.99 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.18 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=2.62 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.89 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=3.45 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.05 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9014ms
rtt min/avg/max/mdev = 1.049/2.635/4.517/0.937 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T13:21:19.422086+00:00; preflight_started_at=2026-11-05T13:21:19.422159+00:00; preflight_completed_at=2026-11-05T13:21:19.498395+00:00; deployment_started_at=2026-11-05T13:21:19.498743+00:00; deployment_completed_at=2026-11-05T13:21:19.565037+00:00; connectivity_started_at=2026-11-05T13:21:19.565182+00:00; connectivity_completed_at=2026-11-05T13:21:28.592662+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
