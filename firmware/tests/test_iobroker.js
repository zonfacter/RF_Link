const assert = require('node:assert/strict');
const parser = require('./iobroker_adapter_parse.js');
for (const [brand,id,sw] of [['ShutterRemote40','98461A','41'],['HTR008W','000001','00']]) {
    for(const button of ['UP','DOWN','STOP']) {
        const frame=parser.parseString(`20;01;${brand};ID=${id};SWITCH=${sw};CMD=${button};`);
        assert(frame && frame.blind && frame.ID);
        assert.equal(frame.brandRaw,brand);
        assert.equal(frame.SWITCH,sw);
        const objects=parser.analyseFrame(frame,'test.remote',0);
        assert(objects.some(obj=>obj._id.includes('BLIND_')));
        assert.equal(parser.encodeValue('ID',frame.ID).toUpperCase(),id);
        const state=Object.values(objects).find(obj=>obj.native && obj.native.attr==='CMD');
        assert(state && state.native.switch===sw);
    }
}
console.log('PASS: ioBroker adapter parser creates blind controls for both supported custom protocols and preserves IDs/channel bytes.');
