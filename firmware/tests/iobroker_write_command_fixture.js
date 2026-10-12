// MIT: ioBroker RFLink installed main.js writeCommand snapshot.
function writeCommand(id, value, callback) {
    let command = '10;' + states[id].native.brand + ';' + Parses.encodeValue('ID', states[id].native.ID) + ';';

    if (states[id].native.attr === 'COLOR') {
        value = value.toString(16);
        if (value.length < 2) value = '0' + value;
        command += '01;' + value + 'BC;COLOR;';
    } else
    if (states[id].native.attr === 'BRIGHT') {
        value = value.toString(16);
        if (value.length < 2) value = '0' + value;
        command += '01;34' + value + ';BRIGHT;';
    }  else
    if (states[id].native.attr === 'MODE') {
        command += '00;3c00;MODE' + value  + ';';
    } else
    if (states[id].native.attr === 'DISCO') {
        command += '00;3c00;' + states[id].native.value + ';'; // if 3c00 (COLOR|BRIGHT) required ?
    } else
    if (states[id].native.brand === 'MiLightv1') {
        if (value === 'true' || value === true || value === '1' || value === 1) {
            value = 'ON';
        } else {
            value = 'OFF';
        }
        command += '00;3c00;' + value + ';';
    } else {
        if (states[id].native.switch !== undefined) {
            command += states[id].native.switch + ';';
        }

        if (states[id].native.stop) {
            value = 'STOP';
            command += value + ';';
        } else if (states[id].native.blind) {
            if (value === 'true' || value === true || value === '1' || value === 1) {
                value = 'UP';
            } else {
                value = 'DOWN';
            }
            command += value + ';';
        } else if (states[id].native.all) {
            if (value === 'true' || value === true || value === '1' || value === 1) {
                value = 'ALLON';
            } else {
                value = 'ALLOFF';
            }
            command += value + ';';
        } else if (states[id].native.set_level) {
            command += Math.max(1, Math.min(100, (value - 1) / 99 * 15)) + ';';
        } else if (states[id].native.switch !== undefined) {
            if (value === 'true' || value === true || value === '1' || value === 1) {
                value = 'ON';
            } else {
                value = 'OFF';
            }
            command += value + ';';
        } else if (states[id].native.attr === 'RGBW') {
            command +=  states[id].native.attr + '=' + value + ';';
        } else if (states[id].native.attr === 'CHIME') {
            command += states[id].native.attr + '=' + value + ';';
        } else {
            command += states[id].native.attr + '=' + value + ';';
        }
    }

    adapter.log.debug('Write: ' + command);
    if (comm) comm.write(command, callback);
}

