import {test} from 'node:test';
import assert from 'node:assert/strict';
import {controlReady,deliveryText,primarySensor,sampleFresh} from '../src/live-data.ts';
const now=Date.now();
const sample={id:1,created_at:new Date(now).toISOString(),source:'uno_usb_asr_d3_v1',raw_json:{rain_percent:0,rain_raw:1023,rain_state:'DRY',quality:{rain_percent:'valid',rain_raw:'valid',rain_state:'valid'}}};
test('电脑有效遥测支持零读数，不依赖旁路状态',()=>{assert.equal(primarySensor(sample,'rain',now).value,0);assert.equal(primarySensor(sample,'rain',now).state,'DRY');});
test('过期、无效质量和非硬件来源不显示成实时读数',()=>{
 assert.equal(primarySensor(sample,'rain',now+16000).value,null);
 assert.equal(primarySensor({...sample,source:'demo'},'rain',now).value,null);
 assert.equal(primarySensor({...sample,raw_json:{...sample.raw_json,quality:{rain_percent:'invalid'}}},'rain',now).value,null);
 assert.equal(sampleFresh({...sample,created_at:'invalid'},now),false);
});
test('控制仅在新板桥接已连接就绪且查询新鲜时允许',()=>{
 const ready={uno:{enabled:true,connected:true,ready:true}};
 assert.equal(controlReady(ready,now,now),true);
 assert.equal(controlReady(ready,now,now+8000),false);
 assert.equal(controlReady({},now,now),false);
 assert.equal(controlReady({...ready,uno:{...ready.uno,connected:false}},now,now),false);
 assert.match(deliveryText('link_sent_no_ack'),/执行未确认/);
});
