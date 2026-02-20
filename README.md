# HA DHD Audio – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [Home Assistant](https://www.home-assistant.io/) custom integration for **DHD audio mixing consoles** (RM4200D & RM5200 series).  
Control and monitor **internal logic states** (true/false) via the DHD **External Control Protocol (ECP)** over TCP.

---

## Features

| Capability | Platform | Description |
|---|---|---|
| **Read logic state** | `binary_sensor` | Monitor a logic as a read-only binary sensor |
| **Read + write logic state** | `switch` | Control a logic as a toggle switch |

- Connects to the mixer over **TCP port 2008** (configurable)
- **Instant push updates** – state changes are received in real-time from the mixer
- Automatic **reconnection** on connection loss
- Supports **multiple logics** per mixer
- Full **config flow UI** – no YAML needed
- **HACS** compatible

## Requirements

- A DHD mixing console with ECP support:
  - **RM4200D** (with RM420-850/852/853 Communication Controller)
  - **RM5200** series (XS, XC, XD, XS2, XC2, XD2)
- Network connectivity between Home Assistant and the mixer
- Logic IDs configured in **DHD Toolbox** (TB5/TB8)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **HA DHD Audio** and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/dhd_audio` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **HA DHD Audio**
3. Enter the **IP address** and **port** (default: 2008) of your DHD mixer
4. Add one or more **logic entities**:
   - **Logic ID** – the 16-bit logic number from your DHD Toolbox configuration
   - **Name** – a friendly name (e.g. "Studio Mic Live")
   - **Entity type** – `switch` (read/write) or `sensor` (read-only)
5. You can add more logics later via **Options** on the integration card

## Finding Logic IDs

The **Logic ID** is a 16-bit number (0–65535) that identifies a logic function inside your DHD mixer. How you find it depends on your system:

### RM5200 / Series 52 (Toolbox 5 / Toolbox 8)

1. Open your project in **Toolbox 5** or **Toolbox 8**
2. Go to **View** → **Audio and Logic IDs View**
3. Use the **Base** or **Addr** column as the Logic ID

### RM4200D (Toolbox 4)

1. Open your project in **Toolbox 4**
2. Go to **Logic System** → **Logic Functions**
3. Open the **Logic Sources Window** (menu *View* → *Logic Sources*, or press **F5**)
4. The Logic ID is shown next to each logic function
5. Use this number directly as the Logic ID in this integration

## Protocol Reference

This integration uses the **DHD External Control Protocol (ECP)** over TCP.

- **Port:** 2008
- **Block size:** 16 bytes (fixed)
- **Byte order:** Big-endian (Motorola)
- **Command used:** `0x110E0000` – Set/Get Internal Logic States

| Operation | Data bytes | Description |
|---|---|---|
| **Query** | `LogicID_Hi, LogicID_Lo` (2 bytes) | Request current state |
| **Set** | `LogicID_Hi, LogicID_Lo, State` (3 bytes) | Set state (`0x01` = on, `0x00` = off) |

Full protocol documentation: [developer.dhd.audio](https://developer.dhd.audio/docs/API/ECP/commands)

> **Note:** ECP is marked as deprecated for 3rd-generation cores (XC3/XD3/XS3) with firmware ≥ 10.2.  
> The `Set Internal Logic States` command is **not** on the planned removal list and remains supported.  
> For RM4200D systems, ECP is fully supported on all firmware versions.

## Troubleshooting

- **Cannot connect:** Verify the mixer IP is reachable from your HA host (`ping <ip>`). Ensure TCP port 2008 is not blocked by a firewall.
- **Entity unavailable:** The mixer may have closed the socket. The integration will automatically reconnect.
- **Wrong state:** Verify the Logic ID matches your Toolbox configuration exactly.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

## License

[MIT](LICENSE)
