#!/usr/bin/env python3
"""
deploy_config_yaml.py
=====================
Network Configuration Management & Provisioning Tool — YAML Edition

Workflow:
  1. Load structured device data from network_config.yaml
  2. Render Cisco IOS config per device using a Jinja2 template
  3. (Dry-run) Print rendered configs to stdout, OR
  4. (Live)    Push configs to real devices via Netmiko SSH

Dependencies:
    pip install pyyaml jinja2 netmiko

Usage:
    # Dry run (no SSH — safe for review)
    python deploy_config_yaml.py --dry-run

    # Live push to all devices
    python deploy_config_yaml.py

    # Live push to a single device
    python deploy_config_yaml.py --host SW-CORE-01
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# ── Optional: only needed for live push ──────────────────────────────────────
try:
    from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_FILE     = BASE_DIR / "network_config.yaml"
TEMPLATE_DIR  = BASE_DIR
TEMPLATE_FILE = "cisco_ios_template.j2"
OUTPUT_DIR    = BASE_DIR / "rendered_configs"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Load YAML data model
# ─────────────────────────────────────────────────────────────────────────────

def load_data(path: Path) -> dict:
    """Parse the YAML data model and return a Python dict."""
    log.info(f"Loading YAML data from: {path}")
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    log.info(f"Found {len(data['devices'])} device(s) in data model.")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# 2. Render Jinja2 template
# ─────────────────────────────────────────────────────────────────────────────

def build_jinja_env(template_dir: Path) -> Environment:
    """Create a Jinja2 environment with strict undefined checking."""
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,   # raise on missing variables — no silent failures
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_config(env: Environment, device: dict, global_cfg: dict) -> str:
    """Render the IOS template for a single device."""
    template = env.get_template(TEMPLATE_FILE)
    return template.render(device=device, global_cfg=global_cfg, **{"global": global_cfg})


# ─────────────────────────────────────────────────────────────────────────────
# 3. Save rendered config to disk
# ─────────────────────────────────────────────────────────────────────────────

def save_config(hostname: str, config_text: str) -> Path:
    """Write rendered config to OUTPUT_DIR/<hostname>.cfg"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{hostname}.cfg"
    out_path.write_text(config_text)
    log.info(f"  Rendered config saved → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. Push config to live device (Netmiko SSH)
# ─────────────────────────────────────────────────────────────────────────────

def push_config(device: dict, config_text: str, username: str, password: str) -> bool:
    """
    Open an SSH session to the device and send the rendered configuration.
    Returns True on success, False on failure.

    NOTE: In production, credentials should come from a secrets vault
          (HashiCorp Vault, AWS Secrets Manager, Ansible Vault, etc.)
          — never hard-coded or stored in plain text.
    """
    if not NETMIKO_AVAILABLE:
        log.error("Netmiko is not installed. Run: pip install netmiko")
        return False

    connection_params = {
        "device_type": device["platform"],   # e.g. "cisco_ios"
        "host":        device["mgmt_ip"],
        "username":    username,
        "password":    password,
    }

    log.info(f"  Connecting to {device['hostname']} ({device['mgmt_ip']}) via SSH…")
    try:
        with ConnectHandler(**connection_params) as conn:
            conn.enable()                                   # enter enable mode
            output = conn.send_config_set(                  # push config line by line
                config_text.splitlines(),
                cmd_verify=False,
            )
            conn.save_config()                              # write memory
            log.info(f"  ✔ Config pushed successfully to {device['hostname']}")
            log.debug(f"  Device output:\n{output}")
            return True

    except NetmikoAuthenticationException:
        log.error(f"  ✖ Authentication failed for {device['hostname']}")
    except NetmikoTimeoutException:
        log.error(f"  ✖ Connection timed out for {device['hostname']} ({device['mgmt_ip']})")
    except Exception as exc:
        log.error(f"  ✖ Unexpected error for {device['hostname']}: {exc}")

    return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run(dry_run: bool = True, target_host: str = None,
        username: str = "", password: str = "") -> None:

    # Load data
    data       = load_data(DATA_FILE)
    global_cfg = data["global"]
    devices    = data["devices"]

    # Filter to a single host if requested
    if target_host:
        devices = [d for d in devices if d["hostname"] == target_host]
        if not devices:
            log.error(f"Host '{target_host}' not found in data model.")
            sys.exit(1)

    # Build template engine
    jinja_env = build_jinja_env(TEMPLATE_DIR)

    results = {"success": [], "failure": []}

    for device in devices:
        hostname = device["hostname"]
        log.info(f"\n{'='*60}")
        log.info(f"Processing: {hostname} ({device['mgmt_ip']}) — role: {device['role']}")
        log.info(f"{'='*60}")

        # Render
        try:
            config_text = render_config(jinja_env, device, global_cfg)
        except Exception as exc:
            log.error(f"  Template rendering failed for {hostname}: {exc}")
            results["failure"].append(hostname)
            continue

        # Save rendered config
        save_config(hostname, config_text)

        if dry_run:
            # Pretty-print to console — no SSH
            separator = "─" * 60
            print(f"\n{separator}")
            print(f"  DRY RUN — Rendered config for: {hostname}")
            print(separator)
            print(config_text)
            results["success"].append(hostname)
        else:
            # Live push
            ok = push_config(device, config_text, username, password)
            (results["success"] if ok else results["failure"]).append(hostname)

    # Summary
    log.info(f"\n{'='*60}")
    log.info("DEPLOYMENT SUMMARY")
    log.info(f"  ✔ Success : {results['success']}")
    log.info(f"  ✖ Failed  : {results['failure']}")
    log.info(f"{'='*60}")

    if results["failure"]:
        sys.exit(1)   # non-zero exit for CI/CD pipelines


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Network Config Provisioning Tool (YAML data source)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Render configs and print them — do NOT push to devices (default: True)",
    )
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="Push rendered configs to live devices via SSH",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Target a single device by hostname (e.g. SW-CORE-01)",
    )
    parser.add_argument("--username", type=str, default="admin", help="SSH username")
    parser.add_argument("--password", type=str, default="",      help="SSH password")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # --live overrides --dry-run
    dry = not args.live

    run(
        dry_run     = dry,
        target_host = args.host,
        username    = args.username,
        password    = args.password,
    )
