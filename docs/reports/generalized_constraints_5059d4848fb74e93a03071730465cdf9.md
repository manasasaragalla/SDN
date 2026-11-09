# Generalized routing execution 5059d4848fb74e93a03071730465cdf9

- **Status:** `SUCCEEDED`
- **Started:** 2026-11-05T13:18:11.997999+00:00
- **Completed:** 2026-11-05T13:18:36.423907+00:00
- **Duration:** 24.426s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** none
- **Hard constraints:** latency LTE, bandwidth GTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |
| `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed` | `h1 → s1 → s3 → s5 → s4 → h4` | 1.811 | 10/10 | True | not recorded | True | 2994977745385656325 | SUCCEEDED |
- **bandwidth measurement:** `VALID`; value `47.42012738244417` Mbps; run `4c3a3773-220b-44f6-b081-e6089333c85c`
- **latency measurement:** `VALID`; value `1.811` ms; run `0627a5b6-5789-4e3e-9292-91f3d7a363d8`
- **Constraint constraint:0:latency:** `SATISFIED`; observed `1.811`; Observation satisfies the hard constraint.
- **Constraint constraint:1:bandwidth:** `SATISFIED`; observed `47.42012738244417`; Observation satisfies the hard constraint.

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
- **Probe snapshot fingerprints:** planned `b3e86169517a2f2c0f8a0c10179d12524e53e4b075e4e9db59cf56fedbc8b2d6`, fresh `925632596c574fa70d6a42e5759e30baa6d0d7f8f8e62a365c7c461c4453753a`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:18:12.032114+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:18:12.014902+00:00; preflight_started_at=2026-11-05T13:18:12.014916+00:00; preflight_completed_at=2026-11-05T13:18:12.041339+00:00; probe_completed_at=2026-11-05T13:18:12.041351+00:00

### physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `acf3727e483cbf42990f457591cbbd6b25ca754e6db10e3840c99fde8433e4c2`
- **Measurement run ID:** `4c3a3773-220b-44f6-b081-e6089333c85c`
- **Probe operation ID:** `11b88037-e7ba-42e4-91e4-efe3827ef7a4`
- **Preflight:** `PASSED`
- **Deployment:** `SUCCEEDED`; cookie `2994977745385656325`; DPIDs `[1, 3, 4, 5]`; readback 16/16
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `SUCCEEDED`; remaining flows `0`
- **Probe snapshot fingerprints:** planned `b3e86169517a2f2c0f8a0c10179d12524e53e4b075e4e9db59cf56fedbc8b2d6`, fresh `2c19a64d2eb9242f935c80fa581ae006b4a004798759e90d6c14b08b546a6645`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:18:12.056613+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:18:12.042424+00:00; preflight_started_at=2026-11-05T13:18:12.042433+00:00; preflight_completed_at=2026-11-05T13:18:12.065430+00:00; compilation_completed_at=2026-11-05T13:18:12.065763+00:00; deployment_started_at=2026-11-05T13:18:12.065766+00:00; deployment_completed_at=2026-11-05T13:18:12.115692+00:00; measurement_started_at=2026-11-05T13:18:12.115707+00:00; measurement_completed_at=2026-11-05T13:18:27.209981+00:00; cleanup_started_at=2026-11-05T13:18:27.210009+00:00; cleanup_completed_at=2026-11-05T13:18:27.234892+00:00

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=1.11 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=1.17 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=1.16 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=1.39 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=2.56 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=1.42 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=1.26 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=2.93 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.40 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=3.72 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 1.114/1.811/3.716/0.869 ms

```

Raw candidate iperf3 output:

```text
{
	"start":	{
		"connected":	[{
				"socket":	5,
				"local_host":	"10.0.0.1",
				"local_port":	53750,
				"remote_host":	"10.0.0.4",
				"remote_port":	5201
			}],
		"version":	"iperf 3.16",
		"system_info":	"Linux SasiRekhas 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64",
		"timestamp":	{
			"time":	"Thu, 05 Nov 2026 13:18:13 GMT",
			"timesecs":	1793884693
		},
		"connecting_to":	{
			"host":	"10.0.0.4",
			"port":	5201
		},
		"cookie":	"44bmqvrxmobvl7wrmm2qb3zkcb4eovhhy4h3",
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
					"end":	1.0011,
					"seconds":	1.0010999441146851,
					"bytes":	6553600,
					"bits_per_second":	52371194.612706728,
					"retransmits":	1,
					"snd_cwnd":	120184,
					"snd_wnd":	1403392,
					"rtt":	19399,
					"rttvar":	335,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	0,
				"end":	1.0011,
				"seconds":	1.0010999441146851,
				"bytes":	6553600,
				"bits_per_second":	52371194.612706728,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	1.0011,
					"end":	2.001095,
					"seconds":	0.999994993209839,
					"bytes":	5898240,
					"bits_per_second":	47186156.251182862,
					"retransmits":	1,
					"snd_cwnd":	115840,
					"snd_wnd":	1404928,
					"rtt":	19180,
					"rttvar":	345,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	1.0011,
				"end":	2.001095,
				"seconds":	0.999994993209839,
				"bytes":	5898240,
				"bits_per_second":	47186156.251182862,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	2.001095,
					"end":	3.001078,
					"seconds":	0.999983012676239,
					"bytes":	5767168,
					"bits_per_second":	46138127.763314039,
					"retransmits":	2,
					"snd_cwnd":	110048,
					"snd_wnd":	1404928,
					"rtt":	18147,
					"rttvar":	425,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	2.001095,
				"end":	3.001078,
				"seconds":	0.999983012676239,
				"bytes":	5767168,
				"bits_per_second":	46138127.763314039,
				"retransmits":	2,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	3.001078,
					"end":	4.001032,
					"seconds":	0.9999539852142334,
					"bytes":	6291456,
					"bits_per_second":	50333964.106575146,
					"retransmits":	1,
					"snd_cwnd":	107152,
					"snd_wnd":	1404928,
					"rtt":	17436,
					"rttvar":	262,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	3.001078,
				"end":	4.001032,
				"seconds":	0.9999539852142334,
				"bytes":	6291456,
				"bits_per_second":	50333964.106575146,
				"retransmits":	1,
				"omitted":	false,
				"sender":	true
			}
		}, {
			"streams":	[{
					"socket":	5,
					"start":	4.001032,
					"end":	5.001523,
					"seconds":	1.00049102306366,
					"bytes":	5767168,
					"bits_per_second":	46114700.6184226,
					"retransmits":	1,
					"snd_cwnd":	101360,
					"snd_wnd":	1404928,
					"rtt":	16329,
					"rttvar":	282,
					"pmtu":	1500,
					"omitted":	false,
					"sender":	true
				}],
			"sum":	{
				"start":	4.001032,
				"end":	5.001523,
				"seconds":	1.00049102306366,
				"bytes":	5767168,
				"bits_per_second":	46114700.6184226,
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
					"end":	5.001523,
					"seconds":	5.001523,
					"bytes":	30277632,
					"bits_per_second":	48429459.586609922,
					"retransmits":	6,
					"max_snd_cwnd":	120184,
					"max_snd_wnd":	1404928,
					"max_rtt":	19399,
					"min_rtt":	16329,
					"mean_rtt":	18098,
					"sender":	true
				},
				"receiver":	{
					"socket":	5,
					"start":	0,
					"end":	5.01953,
					"seconds":	5.001523,
					"bytes":	29753344,
					"bits_per_second":	47420127.382444173,
					"sender":	true
				}
			}],
		"sum_sent":	{
			"start":	0,
			"end":	5.001523,
			"seconds":	5.001523,
			"bytes":	30277632,
			"bits_per_second":	48429459.586609922,
			"retransmits":	6,
			"sender":	true
		},
		"sum_received":	{
			"start":	0,
			"end":	5.01953,
			"seconds":	5.01953,
			"bytes":	29753344,
			"bits_per_second":	47420127.382444173,
			"sender":	true
		},
		"cpu_utilization_percent":	{
			"host_total":	2.3040717372744375,
			"host_user":	0.08268357458682643,
			"host_system":	2.2213682197125539,
			"remote_total":	5.5833590162004274,
			"remote_user":	0.88647229766599023,
			"remote_system":	4.6968468743967344
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
- **Final deployment operation ID:** `9cf00b95-a0e3-45b3-8679-183ac3317cd4`
- **Final selected path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Final deployment:** `SUCCEEDED` (cookie `7025211364585243474`, DPIDs `[1, 3, 4, 5]`)
- **Verified rules:** 16 / 16 (executor reported exact readback status)
- **Connectivity:** `VERIFIED`
- **Final packets:** 10/10 received; loss 0.0%
- **Final RTT:** 1.891 ms

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
64 bytes from 10.0.0.4: icmp_seq=1 ttl=64 time=0.851 ms
64 bytes from 10.0.0.4: icmp_seq=2 ttl=64 time=2.34 ms
64 bytes from 10.0.0.4: icmp_seq=3 ttl=64 time=2.43 ms
64 bytes from 10.0.0.4: icmp_seq=4 ttl=64 time=2.99 ms
64 bytes from 10.0.0.4: icmp_seq=5 ttl=64 time=2.57 ms
64 bytes from 10.0.0.4: icmp_seq=6 ttl=64 time=2.73 ms
64 bytes from 10.0.0.4: icmp_seq=7 ttl=64 time=0.931 ms
64 bytes from 10.0.0.4: icmp_seq=8 ttl=64 time=1.31 ms
64 bytes from 10.0.0.4: icmp_seq=9 ttl=64 time=1.59 ms
64 bytes from 10.0.0.4: icmp_seq=10 ttl=64 time=1.18 ms

--- 10.0.0.4 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9038ms
rtt min/avg/max/mdev = 0.851/1.891/2.989/0.761 ms

```

**Final-stage timestamps:** selection_completed_at=2026-11-05T13:18:27.288203+00:00; preflight_started_at=2026-11-05T13:18:27.288213+00:00; preflight_completed_at=2026-11-05T13:18:27.338191+00:00; deployment_started_at=2026-11-05T13:18:27.338543+00:00; deployment_completed_at=2026-11-05T13:18:27.377130+00:00; connectivity_started_at=2026-11-05T13:18:27.377142+00:00; connectivity_completed_at=2026-11-05T13:18:36.423748+00:00

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
