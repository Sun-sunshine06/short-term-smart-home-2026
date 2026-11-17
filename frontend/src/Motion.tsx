import {useEffect,useState} from 'react';
import {House,Play,Wind} from 'lucide-react';
import './motion.css';
export function Opening({replay,onComplete}:{replay:number;onComplete?:()=>void}) {
 const [visible,setVisible]=useState(()=>!matchMedia('(prefers-reduced-motion: reduce)').matches&&!sessionStorage.getItem('qiju-opened'));
 function close(){sessionStorage.setItem('qiju-opened','1');setVisible(false);onComplete?.();}
 useEffect(()=>{if(replay>0&&!matchMedia('(prefers-reduced-motion: reduce)').matches)setVisible(true);},[replay]);
 useEffect(()=>{if(!visible)return;const timer=setTimeout(close,1600);return()=>clearTimeout(timer);},[visible,replay]);
 if(!visible)return null;
 return <div className="opening-screen" role="dialog" aria-modal="false" aria-label="栖居开场动画"><div className="opening-glow"/><div className="opening-mark"><House size={48} strokeWidth={1.3}/><span className="opening-ring"/></div><div className="opening-wordmark">栖居<span>.</span></div><p>让每一次归家，都有回应。</p><div className="opening-track"><span/></div><small>SMART HOME · 生活，自有节奏</small><button autoFocus onClick={close}>跳过开场</button></div>;
}
export function MotionButton({onClick}:{onClick:()=>void}) {return <button className="motion-replay" onClick={onClick} title="重播开场动画" aria-label="重播开场动画"><Play size={15}/><span>开场</span></button>;}
export function RealReadiness({backend,ready,hasData,error}:{backend:boolean;ready:boolean;hasData:boolean;error:string}) {
 return <div className="readiness-strip"><div className="readiness-lead"><Wind size={19}/><span>家庭连接</span></div><span className={backend?'checked':''}><i/>{backend?'电脑已连接':'等待电脑连接'}</span><b>→</b><span className={ready?'checked':''}><i/>{ready?'USB 桥接就绪':'USB 桥接待连接'}</span><b>→</b><span className={hasData?'checked':''}><i/>{hasData?'环境数据已更新':'等待有效采集'}</span><small>{error||'设备未接入时，不显示虚构状态'}</small></div>;
}
