import {useEffect,useState} from 'react';
import type {PrimaryStatus,RawSample} from './live-data';
export function usePrimary(demo:boolean) {
 const [status,setStatus]=useState<PrimaryStatus|null>(null),[sample,setSample]=useState<RawSample>(),[checkedAt,setCheckedAt]=useState(0),[error,setError]=useState('');
 useEffect(()=>{setStatus(null);setSample(undefined);setCheckedAt(0);setError('');if(demo)return;
 let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
 async function refresh(){controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),2500);
 try {const results=await Promise.allSettled([fetch('/api/status',{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error();return r.json() as Promise<PrimaryStatus>;}),fetch('/api/history?limit=30',{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error();return r.json() as Promise<{records:RawSample[]}>;})]);
 if(disposed)return;
 const [state,history]=results;
 if(state.status==='fulfilled'){setStatus(state.value);setCheckedAt(Date.now());setError('');}else{setStatus(null);setError('无法连接电脑后端');}
 if(history.status==='fulfilled')setSample(history.value.records.find(r=>r.source==='uno_usb_asr_d3_v1'));
 }catch{if(!disposed){setStatus(null);setError('无法读取采集状态');}}finally{clearTimeout(timeout);if(!disposed)timer=setTimeout(refresh,3000);}}
 void refresh();return()=>{disposed=true;controller?.abort();clearTimeout(timer);};
 },[demo]);
 return {status,sample,checkedAt,error};
}
