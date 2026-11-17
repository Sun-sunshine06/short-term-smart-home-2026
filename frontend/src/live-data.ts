import type { Sensor } from './data';
export type UnoState={enabled:boolean;connected:boolean;ready:boolean;port?:string;last_seen_at?:string;last_error?:string;telemetry?:{received:number;delivered:number;errors:number}};
export type PrimaryStatus={uno?:UnoState;expected_states?:Record<string,{value:number|boolean;confirmed:false;command_id:number;auto_close_at?:string}>};
export type RawSample={id:number;created_at:string;source:string;raw_json?:Record<string,unknown>};
export const SAMPLE_TTL_MS=15000;
export function sampleFresh(sample:RawSample|undefined,now=Date.now()) { const age=now-Date.parse(sample?.created_at??'');return Number.isFinite(age)&&age>=-2000&&age<SAMPLE_TTL_MS; }
export function primarySensor(sample:RawSample|undefined,prefix:'rain'|'soil',now=Date.now()):Sensor {
 const unknown:Sensor={value:null,raw:null,state:'UNKNOWN',valid:false};
 if(!sampleFresh(sample,now)||sample?.source!=='uno_usb_asr_d3_v1')return unknown;
 const raw=sample.raw_json??{},value=raw[`${prefix}_percent`],adc=raw[`${prefix}_raw`],state=raw[`${prefix}_state`];
 const quality=raw.quality as Record<string,string>|undefined;
 const numeric=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100&&quality?.[`${prefix}_percent`]==='valid';
 return {value:numeric?value:null,raw:typeof adc==='number'&&adc>=0&&adc<=1023&&quality?.[`${prefix}_raw`]==='valid'?adc:null,state:typeof state==='string'&&(prefix==='rain'?['DRY','WET']:['DRY','OK']).includes(state)&&quality?.[`${prefix}_state`]==='valid'?state:'UNKNOWN',valid:numeric};
}
export function controlReady(status:PrimaryStatus|null,checkedAt:number,now=Date.now()) {const uno=status?.uno;return Boolean(uno?.enabled&&uno.connected&&uno.ready&&now-checkedAt<7000);}
export const deliveryText=(status:string)=>status==='link_sent_no_ack'?'已发往旧板 · 执行未确认':status==='accepted'||status==='queued'?'新板已接收 · 等待投递':status==='pending'?'已入队 · 尚未投递':status==='failed'?'发送失败':'请求已返回 · 执行未确认';
