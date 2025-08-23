# -*- coding: utf-8 -*-
# =============================================================================
# File      : producer.py
# Purpose   : Generate sample messages for 3 Streaming Queue demos.
# Author    : rob lee
# Version   : 1.1.0
# License   : MIT (SPDX-License-Identifier: MIT)
# Standards : PEP 8, PEP 257; Google-style docstrings; RFC 2119 keywords used.
# Dependencies:
#   - pymqi (IBM MQ Client required on host)
#   - python-dotenv
# =============================================================================
"""
CLI producer for IBM MQ Streaming Queue demos.

This utility connects to a queue manager over TCP and continuously PUTs messages
to one of three *source* queues. Streaming Queues (configured separately via
MQSC) duplicate the traffic to corresponding *stream* queues for dashboards or
downstream analytics.

Usage:
    python producer.py --use-case {audit|ecom|retail} --rate 5

Environment:
    Values are loaded from `.env` in the same directory (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import time
from datetime import datetime
from typing import Callable, Dict, Tuple

from dotenv import load_dotenv
import pymqi  # requires IBM MQ Client on host

__author__ = "rob lee"
__license__ = "MIT"
__version__ = "1.1.0"


def load_cfg() -> Dict[str, str]:
    """Load IBM MQ connection configuration from .env.

    Returns:
        Dict[str, str]: A dictionary containing host, port, qmgr, channel,
        user, password, and optional ccdt values.
    """
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    return {
        "host": os.getenv("MQ_HOST", "127.0.0.1"),
        "port": int(os.getenv("MQ_PORT", "1414")),
        "qmgr": os.getenv("MQ_QMGR", "QM1"),
        "channel": os.getenv("MQ_CHANNEL", "DEV.APP.SVRCONN"),
        "user": os.getenv("MQ_USER", "app"),
        "password": os.getenv("MQ_PASSWORD", "passw0rd"),
        "ccdt": os.getenv("MQ_CCDT", ""),
    }


def connect(cfg: Dict[str, str]) -> pymqi.QueueManager:
    """Create a TCP client connection using pymqi.

    Args:
        cfg: Connection parameters (host/port/qmgr/channel/user/password/ccdt).

    Returns:
        pymqi.QueueManager: An established queue manager connection.

    Raises:
        pymqi.MQMIError: If connection fails (e.g., channel auth).
    """
    cd = pymqi.CD()
    cd.ChannelName = cfg["channel"].encode()
    cd.ConnectionName = f'{cfg["host"]}({cfg["port"]})'.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP

    if cfg["ccdt"]:
        # CCDT path split into MQCHLLIB (dir) / MQCHLTAB (file)
        os.environ["MQCHLLIB"], os.environ["MQCHLTAB"] = os.path.split(cfg["ccdt"])

    # No TLS for dev; in production, configure pymqi.SCO with key repos
    sco = pymqi.SCO()
    qmgr = pymqi.QueueManager(None)
    qmgr.connect_with_options(cfg["qmgr"], cd=cd, sco=sco, user=cfg["user"], password=cfg["password"])
    return qmgr


def rand_id(n: int = 8) -> str:
    """Generate a random alphanumeric identifier.

    Args:
        n: Desired length of the identifier.

    Returns:
        str: Random ID of length n.
    """
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def txn_message() -> Dict[str, object]:
    """Construct a synthetic transaction message."""
    return {
        "type": "txn",
        "txn_id": rand_id(),
        "account": f"ACCT-{random.randint(10000, 99999)}",
        "amount": round(random.uniform(-500.0, 500.0), 2),
        "currency": "USD",
        "ts": datetime.utcnow().isoformat() + "Z",
        "merchant": random.choice(["AMAZON", "UBER", "STARBUCKS", "WALMART"]),
    }


def order_message() -> Dict[str, object]:
    """Construct a synthetic e-commerce order message."""
    items = random.randint(1, 4)
    return {
        "type": "order",
        "order_id": rand_id(),
        "customer_id": f"CUST-{random.randint(1000, 9999)}",
        "items": items,
        "total": round(random.uniform(10.0, 300.0), 2),
        "ts": datetime.utcnow().isoformat() + "Z",
        "promo_opt_in": random.choice([True, False]),
    }


def inventory_message() -> Dict[str, object]:
    """Construct a synthetic inventory update message."""
    return {
        "type": "inventory",
        "sku": f"SKU-{random.randint(10000, 99999)}",
        "delta": random.randint(-5, 10),
        "store": random.choice(["DAL01", "AUS02", "NYC03", "SFO04"]),
        "ts": datetime.utcnow().isoformat() + "Z",
    }


USE_CASES: Dict[str, Tuple[str, Callable[[], Dict[str, object]]]] = {
    "audit": ("APP.TXN.IN", txn_message),
    "ecom": ("ORDERS.IN", order_message),
    "retail": ("INV.UPDATES", inventory_message),
}


def put_loop(qmgr: pymqi.QueueManager, queue_name: str, rate: float) -> None:
    """Continuously PUT messages to a queue at an approximate rate.

    Args:
        qmgr: Connected queue manager handle.
        queue_name: Target *source* queue name.
        rate: Approximate messages per second (MUST be > 0 for intended effect).

    Notes:
        - Uses NO_SYNCPOINT for performance (at-least-once semantics).
        - Streaming Queue duplication is handled by the queue attributes (MQSC).
    """
    q = pymqi.Queue(qmgr, queue_name)
    try:
        interval = 1.0 / max(rate, 0.01)
        while True:
            # Build message based on selected queue
            if queue_name == "APP.TXN.IN":
                msg = txn_message()
            elif queue_name == "ORDERS.IN":
                msg = order_message()
            else:
                msg = inventory_message()

            data = json.dumps(msg).encode("utf-8")
            md = pymqi.MD()
            pmo = pymqi.PMO(Options=pymqi.CMQC.MQPMO_NO_SYNCPOINT)
            q.put(data, md, pmo)
            print(f"Put -> {queue_name}: {msg}")
            time.sleep(interval)
    finally:
        q.close()


def main() -> None:
    """CLI entry point parsing arguments and starting the generator."""
    ap = argparse.ArgumentParser(description="IBM MQ Streaming Demos Producer (pymqi)")
    ap.add_argument("--use-case", choices=USE_CASES.keys(), required=True, help="Which demo stream to drive")
    ap.add_argument("--rate", type=float, default=5.0, help="Messages per second (approx)")
    args = ap.parse_args()

    cfg = load_cfg()
    queue_name, _ = USE_CASES[args.use_case]
    qmgr = connect(cfg)

    try:
        put_loop(qmgr, queue_name, args.rate)
    except KeyboardInterrupt:
        pass
    finally:
        qmgr.disconnect()


if __name__ == "__main__":
    main()