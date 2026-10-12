const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {patch}=require('../../iobroker/patch_adapter_buttons.js');
const source=fs.readFileSync('firmware/tests/iobroker_write_command_fixture.js','utf8');
const updated=patch(source);
assert.equal(patch(updated),updated);
const writes=[],resets=[];
const states={};
const context={states,Parses:{encodeValue:()=> '000001'},adapter:{log:{debug:()=>{}},setForeignState:(...args)=>resets.push(args)},comm:{write:(command,cb)=>{writes.push(command);cb?.();}}};
vm.createContext(context);vm.runInContext(updated,context);
for(const command of ['UP','DOWN','STOP']){
    states.button={native:{brand:'HTR008W',ID:1,switch:'00',fixedCommand:command}};
    context.writeCommand('button',true);
    assert.equal(writes.at(-1),`10;HTR008W;000001;00;${command};`);
    assert.deepEqual(resets.at(-1),['button',false,true]);
    const count=writes.length;context.writeCommand('button',false);
    assert.equal(writes.length,count);
}
states.button={native:{brand:'HTR008W',ID:1,switch:'00',blind:true}};
context.writeCommand('button',true);assert.equal(writes.at(-1),'10;HTR008W;000001;00;UP;');
context.writeCommand('button',false);assert.equal(writes.at(-1),'10;HTR008W;000001;00;DOWN;');
console.log('PASS: fixed UP/DOWN/STOP buttons, automatic reset and existing blind commands.');
