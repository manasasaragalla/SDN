# Generalized routing execution 65a057a1098145b69798d31e8733a203

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T15:18:00.318478+00:00
- **Completed:** 2026-11-05T15:18:22.031198+00:00
- **Duration:** 21.713s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** `MAXIMIZE bandwidth` (Mbps)
- **Hard constraints:** none

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-0a004c003fefce9bd5a73d823e8883f782651c732242c7a41430699f73da7940` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | 16345973044628765633 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `9.46999960733498` Mbps; run `3a61e6ad-ef28-47ed-b361-0ccac0bc6e1d`
| `physical-ee54da10bbf51eb3e635b195fcccfa03d9031fa475e66a396a0cb5ccce78feae` | `h1 → s1 → s3 → s5 → s4 → h4` | not recorded | not recorded | None | not recorded | True | 3580763385881718151 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `45.513992707075225` Mbps; run `b1cef012-4402-4e39-a71b-d44864fd6379`

## Candidate evidence

### physical-0a004c003fefce9bd5a73d823e8883f782651c732242c7a41430699f73da7940

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `3a61e6ad-ef28-47ed-b361-0ccac0bc6e1d`
- **Probe operation ID:** `706c0091-e12d-4402-a11b-a3023ecf9794`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `16345973044628765633`; DPIDs `[1, 2, 4]`; readback 12/12
- **Observation:** `VALID` (optimization-observation)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Observation identity:** candidate `physical-0a004c003fefce9bd5a73d823e8883f782651c732242c7a41430699f73da7940`, evaluation run `47736be8-f5c1-4705-a438-38f5e10609bc`, request `19a25e559e0c52307dc82e0507a1c3f78d9453ee7a9bf1893d02c6a7a56b6a80`, plan `6dc3d3990c53ed518c7185777860f1707eca727c127af9cc9f1c6ca38bcc5cfe`, path `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Probe snapshot fingerprints:** planned `fd1413fe4c316586f20a1ca3d1e5550e15883bcaffa4f1af31fec72caa926bd4`, fresh `caeeb44b5b3823c6e0caa5ea00b0b9ca25f401e65faf238dd6047c306d02b5d5`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T15:18:00.363005+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T15:18:00.346057+00:00; preflight_started_at=2026-11-05T15:18:00.346076+00:00; preflight_completed_at=2026-11-05T15:18:00.372604+00:00; compilation_completed_at=2026-11-05T15:18:00.372987+00:00; deployment_started_at=2026-11-05T15:18:00.372992+00:00; deployment_completed_at=2026-11-05T15:18:00.420985+00:00; measurement_started_at=2026-11-05T15:18:00.421004+00:00; measurement_completed_at=2026-11-05T15:18:06.635493+00:00; cleanup_started_at=2026-11-05T15:18:06.635507+00:00; cleanup_completed_at=2026-11-05T15:18:06.645917+00:00

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

Raw candidate iperf3 output:

```text
{
	"start":	{
		"connected":	[{
				"socket":	5,
				"local_host":	"10.0.0.1",
				"local_port":	43478,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 15:18:01 GMT",
			"timesecs":	1793891881
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"f3fluq4xctf3xmqclbajtjfw3keib5kuh77s",
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
					"end":	1.00106,
					"seconds":	1.0010600090026855,
					"bytes":	1441792,
					"bits_per_second":	11522122.446476689,
					"retransmits":	0,
					"snd_cwnd":	97016,
					"snd_wnd":	190976,
					"rtt":	78755,
					"rttvar":	649,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.00106,
				"seconds":	1.0010600090026855,
				"bytes":	1441792,
				"bits_per_second":	11522122.446476689,
				"retransmits":	0,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.00106,
					"end":	2.001067,
					"seconds":	1.0000070333480835,
					"bytes":	1441792,
					"bits_per_second":	11534254.875570577,
					"retransmits":	5,
					"snd_cwnd":	99912,
					"snd_wnd":	481280,
					"rtt":	84874,
					"rttvar":	370,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.00106,
				"end":	2.001067,
				"seconds":	1.0000070333480835,
				"bytes":	1441792,
				"bits_per_second":	11534254.875570577,
				"retransmits":	5,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001067,
					"end":	3.000813,
					"seconds":	0.999746024608612,
					"bytes":	1310720,
					"bits_per_second":	10488423.801540039,
					"retransmits":	0,
					"snd_cwnd":	123080,
					"snd_wnd":	1237504,
					"rtt":	100839,
					"rttvar":	627,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001067,
				"end":	3.000813,
				"seconds":	0.999746024608612,
				"bytes":	1310720,
				"bits_per_second":	10488423.801540039,
				"retransmits":	0,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.000813,
					"end":	4.001175,
					"seconds":	1.0003620386123657,
					"bytes":	1048576,
					"bits_per_second":	8385572.0991133442,
					"retransmits":	1,
					"snd_cwnd":	128872,
					"snd_wnd":	1237504,
					"rtt":	111750,
					"rttvar":	426,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.000813,
				"end":	4.001175,
				"seconds":	1.0003620386123657,
				"bytes":	1048576,
				"bits_per_second":	8385572.0991133442,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.001175,
					"end":	5.00246,
					"seconds":	1.0012849569320679,
					"bytes":	1310720,
					"bits_per_second":	10472303.540970311,
					"retransmits":	0,
					"snd_cwnd":	107152,
					"snd_wnd":	1239040,
					"rtt":	88814,
					"rttvar":	458,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.001175,
				"end":	5.00246,
				"seconds":	1.0012849569320679,
				"bytes":	1310720,
				"bits_per_second":	10472303.540970311,
				"retransmits":	0,
				"omitted":	false,
				"sender":	true
			}
		}],
	"end":	{
		"streams":	[{
				"sender":	{
					"socket":	5,
					"start":	0,
					"end":	5.00246,
					"seconds":	5.00246,
					"bytes":	6553600,
					"bits_per_second":	10480603.543056816,
					"retransmits":	6,
					"max_snd_cwnd":	128872,
					"max_snd_wnd":	1239040,
					"max_rtt":	111750,
					"min_rtt":	78755,
					"mean_rtt":	93006,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.0934,
					"seconds":	5.00246,
					"bytes":	6029312,
					"bits_per_second":	9469999.60733498,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.00246,
			"seconds":	5.00246,
			"bytes":	6553600,
			"bits_per_second":	10480603.543056816,
			"retransmits":	6,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.0934,
			"seconds":	5.0934,
			"bytes":	6029312,
			"bits_per_second":	9469999.60733498,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	1.532105955303376,
			"host_user":	0,
			"host_system":	1.531986148766971,
			"remote_total":	3.5862844537339149,
			"remote_user":	0.51467950770605675,
			"remote_system":	3.0716442120593443
		},
		"sender_tcp_congestion":	"cubic",
		"receiver_tcp_congestion":	"cubic"
	}
}

```

### physical-ee54da10bbf51eb3e635b195fcccfa03d9031fa475e66a396a0cb5ccce78feae

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `b1cef012-4402-4e39-a71b-d44864fd6379`
- **Probe operation ID:** `ef2d44c1-6e88-42c5-b79a-0568e1b940a3`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `3580763385881718151`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `VALID` (optimization-observation)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Observation identity:** candidate `physical-ee54da10bbf51eb3e635b195fcccfa03d9031fa475e66a396a0cb5ccce78feae`, evaluation run `47736be8-f5c1-4705-a438-38f5e10609bc`, request `19a25e559e0c52307dc82e0507a1c3f78d9453ee7a9bf1893d02c6a7a56b6a80`, plan `6dc3d3990c53ed518c7185777860f1707eca727c127af9cc9f1c6ca38bcc5cfe`, path `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Probe snapshot fingerprints:** planned `fd1413fe4c316586f20a1ca3d1e5550e15883bcaffa4f1af31fec72caa926bd4`, fresh `a229fc2c665b55296672053dac11845a1104644a50706185eac6fa0a8384ded3`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T15:18:06.659477+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T15:18:06.647753+00:00; preflight_started_at=2026-11-05T15:18:06.647762+00:00; preflight_completed_at=2026-11-05T15:18:06.669472+00:00; compilation_completed_at=2026-11-05T15:18:06.670588+00:00; deployment_started_at=2026-11-05T15:18:06.670598+00:00; deployment_completed_at=2026-11-05T15:18:06.721644+00:00; measurement_started_at=2026-11-05T15:18:06.721659+00:00; measurement_completed_at=2026-11-05T15:18:12.787623+00:00; cleanup_started_at=2026-11-05T15:18:12.787642+00:00; cleanup_completed_at=2026-11-05T15:18:12.803059+00:00

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
				"local_port":	53594,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 15:18:07 GMT",
			"timesecs":	1793891887
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"fgzb4peacbasnlduzsfs7bc3udgvn3mivvj7",
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
					"end":	1.001103,
					"seconds":	1.0011030435562134,
					"bytes":	6422528,
					"bits_per_second":	51323611.82069958,
					"retransmits":	2,
					"snd_cwnd":	120184,
					"snd_wnd":	1515008,
					"rtt":	19569,
					"rttvar":	438,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.001103,
				"seconds":	1.0011030435562134,
				"bytes":	6422528,
				"bits_per_second":	51323611.82069958,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.001103,
					"end":	2.001254,
					"seconds":	1.0001510381698608,
					"bytes":	5505024,
					"bits_per_second":	44033541.254516423,
					"retransmits":	6,
					"snd_cwnd":	86880,
					"snd_wnd":	1515008,
					"rtt":	14007,
					"rttvar":	394,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.001103,
				"end":	2.001254,
				"seconds":	1.0001510381698608,
				"bytes":	5505024,
				"bits_per_second":	44033541.254516423,
				"retransmits":	6,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001254,
					"end":	3.001058,
					"seconds":	0.99980401992797852,
					"bytes":	5898240,
					"bits_per_second":	47195169.312680967,
					"retransmits":	0,
					"snd_cwnd":	128872,
					"snd_wnd":	1515008,
					"rtt":	21128,
					"rttvar":	246,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001254,
				"end":	3.001058,
				"seconds":	0.99980401992797852,
				"bytes":	5898240,
				"bits_per_second":	47195169.312680967,
				"retransmits":	0,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.001058,
					"end":	4.00108,
					"seconds":	1.0000220537185669,
					"bytes":	5505024,
					"bits_per_second":	44039220.7714192,
					"retransmits":	1,
					"snd_cwnd":	121632,
					"snd_wnd":	1516544,
					"rtt":	20251,
					"rttvar":	299,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.001058,
				"end":	4.00108,
				"seconds":	1.0000220537185669,
				"bytes":	5505024,
				"bits_per_second":	44039220.7714192,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.00108,
					"end":	5.00175,
					"seconds":	1.0006699562072754,
					"bytes":	5898240,
					"bits_per_second":	47154328.6648111,
					"retransmits":	1,
					"snd_cwnd":	118736,
					"snd_wnd":	1516544,
					"rtt":	25325,
					"rttvar":	371,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.00108,
				"end":	5.00175,
				"seconds":	1.0006699562072754,
				"bytes":	5898240,
				"bits_per_second":	47154328.6648111,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}],
	"end":	{
		"streams":	[{
				"sender":	{
					"socket":	5,
					"start":	0,
					"end":	5.00175,
					"seconds":	5.00175,
					"bytes":	29229056,
					"bits_per_second":	46750127.055530563,
					"retransmits":	10,
					"max_snd_cwnd":	128872,
					"max_snd_wnd":	1516544,
					"max_rtt":	25325,
					"min_rtt":	14007,
					"mean_rtt":	20056,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.022402,
					"seconds":	5.00175,
					"bytes":	28573696,
					"bits_per_second":	45513992.707075223,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.00175,
			"seconds":	5.00175,
			"bytes":	29229056,
			"bits_per_second":	46750127.055530563,
			"retransmits":	10,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.022402,
			"seconds":	5.022402,
			"bytes":	28573696,
			"bits_per_second":	45513992.707075223,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	3.3696329542559389,
			"host_user":	0,
			"host_system":	3.3696528896095743,
			"remote_total":	6.2202717409266715,
			"remote_user":	0.500679133305645,
			"remote_system":	5.7195527874330674
		},
		"sender_tcp_congestion":	"cubic",
		"receiver_tcp_congestion":	"cubic"
	}
}

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-ee54da10bbf51eb3e635b195fcccfa03d9031fa475e66a396a0cb5ccce78feae`
- **Selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Selection method:** `OBJECTIVE_RANKING`

| Candidate | bandwidth value (Mbps) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-0a004c003fefce9bd5a73d823e8883f782651c732242c7a41430699f73da7940` | 9.46999960733498 | CANDIDATE | True |
| `physical-ee54da10bbf51eb3e635b195fcccfa03d9031fa475e66a396a0cb5ccce78feae` | 45.513992707075225 | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- Selected by MAXIMIZE of measured bandwidth (45.513992707075225 Mbps) among 2 eligible candidate(s); equal values use ascending physical path fingerprint.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `b81f2fd7-2b36-421e-9485-26fe643bfc4f`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `2418535953736653942`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 1.494 ms

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.81 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.46 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.72 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=0.893 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.22 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=1.39 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.43 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.49 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.30 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.24 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9017ms
rtt min/avg/max/mdev = 0.893/1.494/2.491/0.412 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T15:18:12.857869+00:00; preflight_started_at=2026-11-05T15:18:12.857886+00:00; preflight_completed_at=2026-11-05T15:18:12.922706+00:00; deployment_started_at=2026-11-05T15:18:12.923109+00:00; deployment_completed_at=2026-11-05T15:18:12.995022+00:00; connectivity_started_at=2026-11-05T15:18:12.995039+00:00; connectivity_completed_at=2026-11-05T15:18:22.030953+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
