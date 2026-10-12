# ioBroker integration

The maintained adapter lives in [zonfacter/ioBroker.rflink](https://github.com/zonfacter/ioBroker.rflink). Install a [versioned release](https://github.com/zonfacter/ioBroker.rflink/releases/tag/v2.1.13-rfbuttons.2) and follow its [maintenance instructions](https://github.com/zonfacter/ioBroker.rflink/blob/master/FORK.md).

The fork automatically adds fixed UP, STOP and DOWN buttons for every included blind channel. Keep automatic RFLink upgrades disabled and merge upstream updates deliberately. Existing device assignments and button IDs are preserved.

`RFLink_bridge.js` is an optional JavaScript-adapter script with extra controls and readable last-command/last-reception states under `0_userdata.0.RFLink`. Edit its `RFLINK` constant if the RFLink instance has a different number. It uses external device assignments and never stores learned records on the Mega.

`patch_adapter_buttons.js` is the historical manual patch used before the versioned fork. It is retained only for the regression fixture in `firmware/tests/test_adapter_buttons.js`; use the fork package for installation and updates.

Server credentials, configuration snapshots, network discovery, SSH deployment logs, backups and installed adapter copies are local operational files and are not included in this repository.
