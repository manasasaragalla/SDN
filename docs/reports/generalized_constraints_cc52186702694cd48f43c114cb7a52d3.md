# Generalized routing execution cc52186702694cd48f43c114cb7a52d3

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T15:18:48.602699+00:00
- **Completed:** 2026-11-05T15:19:13.212327+00:00
- **Duration:** 24.610s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** `MINIMIZE latency` (ms)
- **Hard constraints:** bandwidth GTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-992b8be21c90551079ec929ed2eeb640f2c2509802ba2a6481f9c03555fecd14` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |
| `physical-e512d2e3559d269f6379f8fb2b72293506cea19b51a88199d6683840d1a1aa7b` | `h1 → s1 → s3 → s5 → s4 → h4` | 2.483 | 10/10 | True | not recorded | True | 4342834872443545614 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `45.140689406112` Mbps; run `a273dec8-7de7-4181-8390-fd55cbd24fdd`
- **latency measurement:** `VALID`; value `2.483` ms; run `1ea026e4-0494-45f1-98a3-af78ed7ffacf`
- **Constraint constraint:0:bandwidth:** `SATISFIED`; observed `45.140689406112`; Observation satisfies the hard constraint.

## Candidate evidence

### physical-992b8be21c90551079ec929ed2eeb640f2c2509802ba2a6481f9c03555fecd14

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `not created`
- **Probe operation ID:** `not created`
- **Preflight:** `SKIPPED_INFEASIBLE`
- **Deployment:** `NOT_REACHED`; cookie `None`; DPIDs `None`; readback None/None
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `NOT_REACHED`; remaining flows `None`
- **Skipped:** Candidate is statically infeasible: Known physical path capacity cannot satisfy a bandwidth lower bound.
- **Probe snapshot fingerprints:** planned `f59fbe91dfc8f6e0de34ab387e7fad505d8a4d8a894f5cccf86e215070a4a21d`, fresh `fa310dbf13f408ddfe98da02922adb356c0eff04bbeee5037fa59fba97a409ff`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T15:18:48.648270+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T15:18:48.631689+00:00; preflight_started_at=2026-11-05T15:18:48.631744+00:00; preflight_completed_at=2026-11-05T15:18:48.659556+00:00; probe_completed_at=2026-11-05T15:18:48.659568+00:00

### physical-e512d2e3559d269f6379f8fb2b72293506cea19b51a88199d6683840d1a1aa7b

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `a273dec8-7de7-4181-8390-fd55cbd24fdd`
- **Probe operation ID:** `87ea353f-b451-4f58-b0ae-315ea081c1c3`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `4342834872443545614`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `VALID` (optimization-observation)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Observation identity:** candidate `physical-e512d2e3559d269f6379f8fb2b72293506cea19b51a88199d6683840d1a1aa7b`, evaluation run `bb8f4791-9c40-49b6-b83a-cf9cbb7f3158`, request `7691c31facaa7823ea60aa7923bb88be66a5532a1c23cdfca3c59374b53625de`, plan `4bcb03c3183a05f42bc8bf0e4e2c6d28cfef3c0408923ee25512d0983dcde2f2`, path `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Probe snapshot fingerprints:** planned `f59fbe91dfc8f6e0de34ab387e7fad505d8a4d8a894f5cccf86e215070a4a21d`, fresh `68f3da6ac6ef20d8c229bc98e2509a4156e8a187bbcb53f2b9a56fbde377172b`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T15:18:48.678643+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T15:18:48.662290+00:00; preflight_started_at=2026-11-05T15:18:48.662436+00:00; preflight_completed_at=2026-11-05T15:18:48.692719+00:00; compilation_completed_at=2026-11-05T15:18:48.693158+00:00; deployment_started_at=2026-11-05T15:18:48.693162+00:00; deployment_completed_at=2026-11-05T15:18:48.762294+00:00; measurement_started_at=2026-11-05T15:18:48.762607+00:00; measurement_completed_at=2026-11-05T15:19:03.940201+00:00; cleanup_started_at=2026-11-05T15:19:03.940230+00:00; cleanup_completed_at=2026-11-05T15:19:03.974564+00:00

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=2.25 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.68 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.83 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=3.98 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=3.00 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=3.32 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=2.21 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.10 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=2.05 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=2.43 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.677/2.483/3.979/0.688 ms

```

Raw candidate iperf3 output:

```text
{
	"start":	{
		"connected":	[{
				"socket":	5,
				"local_host":	"10.0.0.1",
				"local_port":	46472,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 15:18:49 GMT",
			"timesecs":	1793891929
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"65d2cxe36gs6slbgzthlc2ike7vqaukuo3wu",
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
					"end":	1.001101,
					"seconds":	1.001101016998291,
					"bytes":	6029312,
					"bits_per_second":	48181447.407402188,
					"retransmits":	11,
					"snd_cwnd":	118736,
					"snd_wnd":	1102848,
					"rtt":	19744,
					"rttvar":	607,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.001101,
				"seconds":	1.001101016998291,
				"bytes":	6029312,
				"bits_per_second":	48181447.407402188,
				"retransmits":	11,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.001101,
					"end":	2.001081,
					"seconds":	0.99997997283935547,
					"bytes":	5505024,
					"bits_per_second":	44041074.0176643,
					"retransmits":	1,
					"snd_cwnd":	108600,
					"snd_wnd":	1102848,
					"rtt":	19121,
					"rttvar":	378,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.001101,
				"end":	2.001081,
				"seconds":	0.99997997283935547,
				"bytes":	5505024,
				"bits_per_second":	44041074.0176643,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001081,
					"end":	3.001078,
					"seconds":	0.99999701976776123,
					"bytes":	5898240,
					"bits_per_second":	47186060.6254191,
					"retransmits":	3,
					"snd_cwnd":	101360,
					"snd_wnd":	1102848,
					"rtt":	16658,
					"rttvar":	295,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001081,
				"end":	3.001078,
				"seconds":	0.99999701976776123,
				"bytes":	5898240,
				"bits_per_second":	47186060.6254191,
				"retransmits":	3,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.001078,
					"end":	4.001062,
					"seconds":	0.9999840259552002,
					"bytes":	5636096,
					"bits_per_second":	45089488.2615055,
					"retransmits":	1,
					"snd_cwnd":	104256,
					"snd_wnd":	1102848,
					"rtt":	17054,
					"rttvar":	322,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.001078,
				"end":	4.001062,
				"seconds":	0.9999840259552002,
				"bytes":	5636096,
				"bits_per_second":	45089488.2615055,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.001062,
					"end":	5.000823,
					"seconds":	0.99976098537445068,
					"bytes":	5898240,
					"bits_per_second":	47197200.821281277,
					"retransmits":	1,
					"snd_cwnd":	98464,
					"snd_wnd":	1102848,
					"rtt":	16269,
					"rttvar":	129,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.001062,
				"end":	5.000823,
				"seconds":	0.99976098537445068,
				"bytes":	5898240,
				"bits_per_second":	47197200.821281277,
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
					"end":	5.000823,
					"seconds":	5.000823,
					"bytes":	28966912,
					"bits_per_second":	46339431.729537323,
					"retransmits":	17,
					"max_snd_cwnd":	118736,
					"max_snd_wnd":	1102848,
					"max_rtt":	19744,
					"min_rtt":	16269,
					"mean_rtt":	17769,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.017478,
					"seconds":	5.000823,
					"bytes":	28311552,
					"bits_per_second":	45140689.406112,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.000823,
			"seconds":	5.000823,
			"bytes":	28966912,
			"bits_per_second":	46339431.729537323,
			"retransmits":	17,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.017478,
			"seconds":	5.017478,
			"bytes":	28311552,
			"bits_per_second":	45140689.406112,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	1.1912356186234225,
			"host_user":	0,
			"host_system":	1.1912555723188767,
			"remote_total":	7.04616179368079,
			"remote_user":	0.921968316656456,
			"remote_system":	6.1242333373060749
		},
		"sender_tcp_congestion":	"cubic",
		"receiver_tcp_congestion":	"cubic"
	}
}

```

## Selection and final execution

- **Selection status:** `SELECTED`
- **Selected candidate:** `physical-e512d2e3559d269f6379f8fb2b72293506cea19b51a88199d6683840d1a1aa7b`
- **Selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Selection method:** `OBJECTIVE_RANKING`

| Candidate | latency value (ms) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-992b8be21c90551079ec929ed2eeb640f2c2509802ba2a6481f9c03555fecd14` | None | PROVEN_INFEASIBLE | False |
| `physical-e512d2e3559d269f6379f8fb2b72293506cea19b51a88199d6683840d1a1aa7b` | 2.483 | CANDIDATE | True |

Selection reasoning:
- Selection is a pure planning result and does not imply deployment or runtime satisfaction.
- Selected by MINIMIZE of measured latency (2.483 ms) among 1 eligible candidate(s); equal values use ascending physical path fingerprint.
- **Final preflight:** `PASSED`
- **Final topology fingerprints:** planned `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`, fresh `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Connected DPIDs:** `[1, 2, 3, 4, 5]`
- **Operational data ports:** 14/14
- **Final deployment operation ID:** `0d51d299-2f53-4e00-a847-ff37515883dd`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `14657180616210790473`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 2.294 ms

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.49 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.66 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.38 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=1.93 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=1.65 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=3.28 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=2.01 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.23 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=3.32 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=3.00 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9017ms
rtt min/avg/max/mdev = 1.380/2.294/3.324/0.692 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T15:19:04.035052+00:00; preflight_started_at=2026-11-05T15:19:04.035077+00:00; preflight_completed_at=2026-11-05T15:19:04.119239+00:00; deployment_started_at=2026-11-05T15:19:04.119651+00:00; deployment_completed_at=2026-11-05T15:19:04.185995+00:00; connectivity_started_at=2026-11-05T15:19:04.186011+00:00; connectivity_completed_at=2026-11-05T15:19:13.212113+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
