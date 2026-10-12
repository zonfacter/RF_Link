/* Run on the ioBroker host from /opt/iobroker:
 * node /path/to/patch_adapter_buttons.js
 * Adds native.fixedCommand to RFLink states; keeps a backup of main.js.
 * Adapter updates may overwrite this local extension.
 */
const fs = require('node:fs');
const path = require('node:path');
const childProcess = require('node:child_process');
const marker = '// RFLink fixed direction buttons';
const anchor = "    if (states[id].native.attr === 'COLOR') {";
const extension = `    ${marker}
    if (states[id].native.fixedCommand !== undefined) {
        const fixed = states[id].native.fixedCommand;
        if (!['UP', 'DOWN', 'STOP'].includes(fixed)) {
            callback && callback(new Error('Invalid RFLink fixedCommand'));
            return;
        }
        if (!(value === true || value === 'true' || value === 1 || value === '1')) {
            callback && callback();
            return;
        }
        command += states[id].native.switch + ';' + fixed + ';';
        if (comm) comm.write(command, err => {
            if (!err) adapter.setForeignState(id, false, true);
            callback && callback(err);
        });
        return;
    }

`;

function patch(source) {
    if (source.includes(marker)) return source;
    if (source.split(anchor).length !== 2)
        throw Error('Unexpected adapter source: expected one COLOR branch. No changes made.');
    const start = source.indexOf('function writeCommand(');
    const position = source.indexOf(anchor, start);
    if (start < 0 || position < 0) throw Error('writeCommand not found');
    return source.slice(0, position) + extension + source.slice(position);
}

if (require.main === module) {
    const packageFile = require.resolve('iobroker.rflink/package.json', {paths:[process.argv[2] || process.cwd()]});
    const filename = path.join(path.dirname(packageFile), 'main.js');
    const source = fs.readFileSync(filename, 'utf8');
    const result = patch(source);
    if (result === source) {
        console.log('Extension already installed.');
    } else {
        const stamp = Date.now();
        const candidate = filename + '.candidate-' + stamp + '.js';
        fs.writeFileSync(candidate, result);
        try {
            childProcess.execFileSync(process.execPath, ['--check', candidate]);
            const backup = filename + '.before-fixed-buttons-' + stamp;
            fs.copyFileSync(filename, backup);
            fs.writeFileSync(filename, result);
            console.log('Installed. Backup: ' + backup);
            console.log('Restart only rflink.0, then create the fixed direction buttons.');
        } finally {
            fs.unlinkSync(candidate);
        }
    }
}
module.exports = {patch};
