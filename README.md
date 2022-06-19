# Home Assistant integration for The Things Network

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This adapter is a replacement for the official [TTN integration](https://www.home-assistant.io/integrations/thethingsnetwork)

## Differences compared to the official integration

1. Support TTN v3. v2 support has been removed
2. Supports setup from the UI
3. Devices and channels can be renamed using the adapter extra settings
4. Can be installed/updated with HACS - add as extra repository

## How to install

1. Enable persistent storage in [TTN](https://www.thethingsindustries.com/docs/integrations/storage/)
2. Install the TTN adapter in HA
3. Configure adapter in HA: Configuration → Device and Settings → Add Integration → Search for The Things Network

## Questions / Suggestions

Either open an issue, pull request, reply in the [HA forum](https://community.home-assistant.io/t/the-things-network-ttn-new-adapter-for-v3/368951) or ping me in the HA discord channel (angelnu)
