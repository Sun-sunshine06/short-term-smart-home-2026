import {useState} from 'react';
import {LoaderCircle} from 'lucide-react';
import type {DeviceId} from './data';
import type {UIComponents} from './ui-types';
import {deliveryText} from './live-data';
import {jsonBody,request} from './pages-data';
export function RealControl({id,ready,notify,onResult,Switch}:{id:DeviceId;ready:boolean;notify:(s:string)=>void;onResult:(s:string)=>void;Switch:UIComponents['Switch']}) {
 const [busy,setBusy]=useState(false),[result,setResult]=useState<{stage:string;message:string}|null>(null);
 const [requested,setRequested]=useState(false);
 if(id==='camera')return <a className="text-link" href="#vision">打开图像采集与识别 →</a>;
 async function send(on:boolean){if(busy||!ready)return;setBusy(true);setRequested(on);setResult({stage:'sending',message:'正在等待新板投递结果…'});
 try{const data=await request<{status:string;command_id:number}>('/api/device/control',jsonBody({target:id==='door'?'door':id,action:id==='door'?(on?'open':'close'):(on?'on':'off')}));const message=`#${data.command_id} · ${deliveryText(data.status)}`;setResult({stage:data.status,message});notify(message);onResult(message);}
 catch(e){setRequested(!on);const message=(e as Error).name==='TimeoutError'?'请求超时，投递结果未确认，请检查现场后再操作':(e as Error).message;setResult({stage:'failed',message});notify(message);onResult(message);}
 finally{setBusy(false);}}
 return <><div className="real-device-toggle"><span>{busy?<><LoaderCircle size={13}/>正在发送…</>:!ready?'等待设备连接':result?`指令目标：${requested?(id==='door'?'开门':'开启'):(id==='door'?'关门':'关闭')}`:'指令开关'}</span><Switch label={`${id==='light'?'灯光':id==='fan'?'风扇':'门控'}指令开关`} isLabelHidden value={requested} isDisabled={!ready||busy} onChange={on=>void send(on)}/></div>{result&&<div className="command-delivery" data-stage={result.stage} role="status">{result.message}</div>}<p className="device-confirmation">开关表示指令目标，不代表实际状态。{id==='door'?'开门后预计约 4 秒自动关闭。':''}</p></>;
}
