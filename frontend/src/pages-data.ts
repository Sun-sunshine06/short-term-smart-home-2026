export type HistoryRow = { id:number; created_at:string; temperature:number|null; light_level:number|null; door_open:boolean|null; window_open:boolean|null; fan_on:boolean|null; source:string };
export type Person = {id:number;name:string;identity:string;active:boolean;image_count?:number};
export type Detection = {id:number;created_at:string;labels:string[];confidence:number|null;model_name:string|null;image_path?:string;result_image_path?:string;inference_ms?:number};
export type AccessRow = {id:number;created_at:string;user_name:string|null;matched:boolean;score:number|null;result:string};
export function demoHistory():HistoryRow[] {
  const start=new Date();start.setHours(0,0,0,0);
  return Array.from({length:48},(_,i)=>({id:i+1,created_at:new Date(start.getTime()+i*1800000).toISOString(),temperature:Math.round((23.6+Math.sin(i/7)*1.6+i/100)*10)/10,light_level:i>13&&i<39?75:20,door_open:[15,19,34,38].includes(i),window_open:i>16&&i<35,fan_on:i>20&&i<35,source:'演示样本'}));
}
export const demoPeople:Person[]=[{id:1,name:'林同学',identity:'member_001',active:true,image_count:3},{id:2,name:'陈同学',identity:'member_002',active:true,image_count:2}];
export const stamp=(offset=0)=>new Date(Date.now()-offset*60000).toISOString();
export const shortDate=(s?:string)=>s?new Date(s).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
export const localDate=(date=new Date())=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
export function filterHistory(rows:HistoryRow[],from:string,to:string) {
 const start=from?new Date(from).getTime():-Infinity,end=to?new Date(to).getTime():Infinity;
 return rows.filter(row=>{const time=new Date(row.created_at).getTime();return time>=start&&time<=end;}).sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at));
}
export async function request<T>(path:string,options?:RequestInit):Promise<T> {
 const response=await fetch(path,{...options,signal:options?.signal??AbortSignal.timeout(20000)});
 const data=await response.json();
 if(!response.ok||data.ok===false)throw new Error(data.error||`请求失败 (${response.status})`);
 return data;
}
export const jsonBody=(value:unknown,method='POST'):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export function csvHistory(rows:HistoryRow[]) {
 const cell=(v:unknown)=>`"${String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')}"`;
 return '\uFEFF时间,温度,灯光,门,窗,风扇,来源\r\n'+rows.map(r=>[r.created_at,r.temperature,r.light_level,r.door_open,r.window_open,r.fan_on,r.source].map(cell).join(',')).join('\r\n');
}
