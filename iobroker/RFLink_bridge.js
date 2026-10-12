/* Paste into an ioBroker JavaScript adapter script.
 * Uses RFLink adapter rawData for commands and original serial feedback.
 * Avoids the upstream parser's UP/DOWN feedback ambiguity.
 */
const RFLINK = 'rflink.0';
const BASE = '0_userdata.0.RFLink';
const devices = new Map();

async function register(brand, id, channel) {
    const key = `${brand}.${id}.${channel}`;
    if (devices.has(key)) return devices.get(key);
    const path = `${BASE}.${key}`;
    devices.set(key, path);
    for (const [button, label] of [['UP','Hoch'],['STOP','Stopp'],['DOWN','Runter']]) {
        const state = `${path}.${button}`;
        if (!await getObjectAsync(state)) {
            await setObjectAsync(state, {type:'state', common:{name:`${brand} ${id} Kanal ${channel}: ${label}`, type:'boolean', role:'button', read:true, write:true}, native:{}});
            await setStateAsync(state, false, true);
        }
        on({id:state, change:'any'}, async event => {
            if (!event.state || event.state.ack || !event.state.val) return;
            await setStateAsync(`${RFLINK}.rawData`, `10;${brand};${id};${channel};${button};\n`, false);
            await setStateAsync(state, false, true);
        });
    }
    for (const [name, label] of [['lastCommand','Letzter empfangener Befehl'],['lastSeen','Letzter Empfang']]) {
        const state = `${path}.${name}`;
        if (!await getObjectAsync(state))
            await setObjectAsync(state,{type:'state',common:{name:label,type:'string',role:'text',read:true,write:false},native:{}});
    }
    return path;
}

const startup = (async () => {
    // Existing devices; assignments remain external to the Mega.
    for(let ch=0;ch<=5;++ch) await register('ShutterRemote40','98461A',(0x40+ch).toString(16).toUpperCase());
    await register('HTR008W','000001','00');
    log(`RFLink bridge ready: ${BASE}; adapter ${RFLINK}`,'info');
})();

on({id:`${RFLINK}.rawData`,change:'any'}, async event => {
    if (!event.state || !event.state.ack || typeof event.state.val!=='string') return;
    const match = event.state.val.trim().match(/^20;[0-9a-f]+;(ShutterRemote40|HTR008W);(.*)$/i);
    if (!match) return;
    const fields = Object.fromEntries(match[2].split(';').filter(x=>x.includes('=')).map(x=>x.split('=')));
    if (!/^[0-9a-f]{1,6}$/i.test(fields.ID||'') || !/^[0-9a-f]{2}$/i.test(fields.SWITCH||'') || !['UP','STOP','DOWN'].includes(fields.CMD)) return;
    await startup;
    const path=await register(match[1],fields.ID.padStart(6,'0').toUpperCase(),fields.SWITCH.toUpperCase());
    await setStateAsync(`${path}.lastCommand`, fields.CMD, true);
    await setStateAsync(`${path}.lastSeen`, new Date().toISOString(), true);
});
