const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const handlers=new Map(),objects=new Map(),writes=[];
const context={console,Map,Object,Date,log:()=>{},
    getObjectAsync:async id=>objects.get(id),
    setObjectAsync:async(id,obj)=>objects.set(id,obj),
    setStateAsync:async(id,val,ack)=>writes.push({id,val,ack}),
    on:(options,callback)=>handlers.set(options.id,callback)};
vm.createContext(context);
vm.runInContext(fs.readFileSync('iobroker/RFLink_bridge.js','utf8'),context);
(async()=>{
    await vm.runInContext('startup',context);
    assert(objects.size===35);
    const button='0_userdata.0.RFLink.ShutterRemote40.98461A.41.UP';
    await handlers.get(button)({state:{ack:false,val:true}});
    assert(writes.some(x=>x.id==='rflink.0.rawData' && x.val==='10;ShutterRemote40;98461A;41;UP;\n' && !x.ack));
    await handlers.get('rflink.0.rawData')({state:{ack:true,val:'20;01;HTR008W;ID=000001;SWITCH=00;CMD=UP;\r'}});
    assert(writes.some(x=>x.id==='0_userdata.0.RFLink.HTR008W.000001.00.lastCommand' && x.val==='UP' && x.ack));
    const length=writes.length;
    await handlers.get(button)({state:{ack:true,val:true}});
    assert(writes.length===length);
    console.log('PASS: ioBroker bridge creates controls, routes sends and preserves UP feedback without command loops.');
})().catch(error=>{console.error(error);process.exitCode=1;});
