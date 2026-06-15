This project is an excellent representation of modern **Infrastructure as Code (IaC)** applied to network engineering. It demonstrates how to shift from manual, error-prone CLI configuration to a structured, repeatable, automated pipeline.

Separating the **data model** (what the network looks like) from the **configuration template** (how that look translates into Cisco IOS CLI commands), this project provides a framework to safely validate and deploy changes across network infrastructure.

Here is a detailed breakdown of how the entire project functions, layer by layer.

---

## 1. Architectural Overview

The project follows a classic automation paradigm: **Data Model + Template = Rendered Artifact**, followed by a **Transport Layer** to push changes to production.

```
┌─────────────────────────┐
│       DATA MODEL        │
│  (network_config.json/  │
│         .yaml)          │
└────────────┬────────────┘
             │ (Parses into Python dict)
             ▼
┌─────────────────────────┐       ┌──────────────────────────┐
│    ORCHESTRATION ENGINE │ ◄────  │  JINJA2 TEMPLATE ENGINE  │
│  (deploy_config_*.py)   │       │ (cisco_ios_template.j2)  │
└────────────┬────────────┘       └──────────────────────────┘
             │ (Generates final configs)
             ▼
 ┌───────────┴───────────┐
 │   DRY-RUN / VALIDATE  │ ──► (Prints to console & saves to disk)
 └───────────┬───────────┘
             │ (If --live flag is passed)
             ▼
┌─────────────────────────┐
│     TRANSPORT LAYER     │
│      (Netmiko SSH)      │
└────────────┬────────────┘
             │ (Executes production push)
             ▼
┌─────────────────────────┐
│     LIVE INFRASTRUCTURE │
│ (SW-CORE-01 / SW-ACCESS)│
└─────────────────────────┘

```

---

## 2. Component Breakdowns

### Component A: The Data Models (`network_config.json` & `network_config.yaml`)

These files represent the "Source of Truth." Instead of writing terminal commands, you define the network in plain, structured data text. Both files are structurally identical, carrying:

* **Global Parameters:** Shared attributes across all devices (NTP servers, Syslog infrastructure, SNMP communities, DNS domains).
* **Device Profiles:** A specific list of target nodes (`SW-CORE-01`, `SW-ACCESS-01`). For each node, it details its management IP, role, local VLAN definitions, interface mappings (Trunks vs. Access ports), explicit Access Control Lists (ACLs), and OSPF routing configurations.

### Component B: The Templating Engine (`cisco_ios_template.j2`)

This is a **Jinja2** template file. It acts as an abstract stencil of a Cisco IOS configuration file. Instead of hardcoding hostnames or IPs, it uses variables (`{{ device.hostname }}`) and conditional programmatic logic:

* **Loops (`{% for %}`):** Dynamically iterate over lists of VLANs, NTP servers, or interfaces. If a switch has 3 interfaces or 48 interfaces, the template loops through them and builds the correct block dynamically.
* **Conditionals (`{% if/elif/else %}`):** Adjusts CLI generation based on context. For example, if an interface mode is defined as `trunk`, it generates trunking commands; if it is an `access` port, it generates portfast and access commands. It also checks if OSPF is defined before attempting to generate routing processes.

### Component C: The Automation Drivers (`deploy_config_json.py` & `deploy_config_yaml.py`)

These Python scripts serve as the orchestrators. They handle arguments passed via the command line, manage file operations, and execute the deployment pipeline.

The **only functional difference** between the two files is the serialization library utilized in step one:

* `deploy_config_yaml.py` utilizes `yaml.safe_load()` to translate the YAML structure into a native Python dictionary.
* `deploy_config_json.py` utilizes `json.load()` to read the JSON file, and explicitly includes a line (`data.pop("_comment", None)`) to strip out any structural comment tags since JSON does not natively support comments.

---

## 3. Step-by-Step Program Workflow

When you execute either script, the application steps through five distinct operational phases:

### Step 1: Parsing and Arguments Identification

The script leverages Python's `argparse` module to check how the engineer wants to run the tool. By default, it runs safely in a **Dry-Run** mode. It checks if it should run globally or isolate a specific device using the `--host` flag.

### Step 2: Data Synthesis

The script reads your data files and builds a comprehensive internal memory map. It loads the Jinja2 context using `StrictUndefined`. This setting acts as a safety guard: if your data model is missing a vital parameter that the template needs, the script will crash immediately rather than generating a corrupted or incomplete config file.

### Step 3: Local Configuration Compilation

The script iterates through the list of target switches. It merges the unique properties of the switch with the global properties inside the Jinja2 engine, producing clean, production-ready Cisco commands. These generated configurations are then automatically saved locally as `.cfg` text files inside a `rendered_configs/` directory for historical tracking or auditing.

### Step 4: Dry-Run Evaluation

If you ran the script normally without safety overrides, it halts here. It prints the entire rendered configuration straight to your terminal window. This allows an engineer to peer-review the exact structural changes before modifying a production network.

### Step 5: Live Transport Deployment (The Pushing Layer)

If you intentionally pass the `--live` flag along with authorization credentials, the script initializes **Netmiko**, an industry-standard SSH library built specifically for network equipment.

* It securely logs into the switch via SSH using the device's management IP.
* It enters privileged `enable` mode.
* It feeds the newly generated configuration line-by-line using `send_config_set()`.
* It permanently commits the changes to NVRAM (`conn.save_config()`), equivalent to typing `write memory` or `copy running-config startup-config` on the CLI.
* It cleanly terminates the SSH session and reports a structured deployment success/failure summary.

---

## 4. Key Automation Best Practices Demonstrated Here

* **Idempotency and Consistency:** By driving configurations from a centralized data model, you ensure that settings across hundreds of switches never drift out of sync.
* **Fail-Safe Architecture:** The split execution mode (Dry-Run vs Live Mode) guarantees that engineers cannot accidentally push an unverified or broken command configuration to a live environment.
* **Error Abstraction:** The network scripts incorporate robust `try-except` wrappers around the Netmiko transport block. If a single switch goes offline, crashes, or suffers an authentication failure, the tool catches the error, notes the failure, logs it, and continues setting up the remaining devices rather than breaking the entire deployment queue mid-run.