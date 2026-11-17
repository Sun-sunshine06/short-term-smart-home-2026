import { Opening, MotionButton, RealReadiness } from './Motion';
import { usePrimary } from './usePrimary';
import { primarySensor, controlReady, sampleFresh } from './live-data';
import Pages, { pageInfo, readPage } from './Pages';
import { useEffect, useState } from 'react';
import type { UIComponents } from './ui-types';
import { House, LayoutDashboard, SlidersHorizontal, ChartNoAxesCombined, ScanLine, ScanFace,
  Settings2, ArrowUpRight, ArrowRight, Bell, Lightbulb, Fan, DoorClosed, Camera, Droplets,
  Sprout, Cpu, Wifi, WifiOff, CircleCheck, CircleAlert, FlaskConical, RotateCcw, ChevronRight,
  Monitor, Cable, ShieldCheck, Clock3, Info, Sun, Menu, X, Activity, LockKeyhole } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { initialDevices, liveSensor, scenarios, scenarioEvents, timeText } from './data';
import type { Scenario, Room, DeviceId, DeviceState, EdgeStatus, EventItem, Sensor } from './data';

function legacy(page = 'home') { return `#${page === 'home' ? 'devices' : page}`; }

function HouseIllustration() {
  return <svg className="home-art" viewBox="0 0 320 200" fill="none" aria-hidden="true">
    <ellipse cx="166" cy="166" rx="123" ry="20" fill="#c9e9e4" opacity=".65" />
    <circle cx="162" cy="94" r="86" fill="#d6efeb" />
    <path d="M74 103 153 48 244 88 170 143Z" fill="#aacfc9" />
    <path d="m84 104 77-50 73 36v67l-73 28-77-41Z" fill="#f8fdfb" />
    <path d="m161 112 73-22v67l-73 28Z" fill="#dbefea" />
    <path d="m65 104 89-62 96 43-14 9-81-36-77 54Z" fill="#1f7771" />
    <path d="m155 58 81 36-75 24-77-14Z" fill="#7abbb0" />
    <path d="m155 58 6 60 75-24Z" fill="#99cfc3" />
    <path d="m111 118 22 9v28l-22-11Z" fill="#e8b85c" />
    <path d="m115 122 14 6v18l-14-6Z" fill="#ffe5a0" />
    <path d="m183 122 26-8v23l-26 8Z" fill="#7fb3aa" />
    <path d="m187 124 18-5v15l-18 6Z" fill="#e5f6f1" />
    <path d="m196 122 0 15" stroke="#7fb3aa" strokeWidth="2" />
    <path d="m170 152 15-5v29l-15 6Z" fill="#489086" />
    <path d="m219 71 0-24 15 5v25Z" fill="#a4cec5" />
    <path d="m215 46 8-3 15 6-7 4Z" fill="#73a89f" />
    <path d="M60 161v-25m0 10c-18-1-23-10-21-19 14-2 23 6 21 19Zm0-4c16-1 23-12 20-22-14 1-22 8-20 22Z" stroke="#5c9f89" strokeWidth="4" strokeLinecap="round" fill="#8ac2a6" />
    <path d="M46 158h28l-5 21H51Z" fill="#e0c9a3" />
    <circle cx="261" cy="48" r="19" fill="#fff" opacity=".95" />
    <path d="M251 47c6-6 14-6 20 0m-16 4c4-4 8-4 12 0m-8 4 4 0" stroke="#3b9e8e" strokeWidth="2.5" strokeLinecap="round" />
    <circle cx="85" cy="51" r="5" fill="#f0ce83" /><circle cx="265" cy="126" r="4" fill="#8fc6bc" />
  </svg>;
}

function Sparkline({ kind, alert }: {kind: 'rain' | 'soil'; alert: boolean}) {
  const points = kind === 'rain' ? (alert ? '0,42 25,40 50,42 75,36 100,40 125,28 150,30 175,10 200,8 225,13 250,7' : '0,36 25,40 50,35 75,42 100,34 125,39 150,36 175,40 200,31 225,35 250,32') : (alert ? '0,8 25,12 50,12 75,20 100,23 125,28 150,34 175,37 200,40 225,43 250,44' : '0,23 25,25 50,22 75,20 100,25 125,21 150,23 175,18 200,22 225,20 250,22');
  return <svg viewBox="0 0 250 55" preserveAspectRatio="none" className={`sparkline ${alert ? 'alert' : ''}`} role="img" aria-label="演示趋势示意，非历史测量曲线">
    <defs><linearGradient id={`fill-${kind}`} x1="0" y1="0" x2="0" y2="1"><stop stopColor="currentColor" stopOpacity=".15"/><stop offset="1" stopColor="currentColor" stopOpacity="0"/></linearGradient></defs>
    <polygon points={`0,55 ${points} 250,55`} fill={`url(#fill-${kind})`}/><polyline pathLength="1" points={points} stroke="currentColor" strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke"/>
  </svg>;
}

export default function App({ ui }: { ui: UIComponents }) {
  const { Button, Badge, Card, Switch } = ui;
  const [page, setPage] = useState(readPage);
  useEffect(() => { const change = () => {setPage(readPage()); setMobileNav(false); window.scrollTo({top:0});}; window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  useEffect(() => { document.title = `${pageInfo[page][0]} · 栖居`; }, [page]);
  const [demo, setDemo] = useState(false);
  const primary=usePrimary(demo);
  const [replay,setReplay]=useState(0);
  const [scenario, setScenario] = useState<Scenario>('normal');
  const [devices, setDevices] = useState<DeviceState>(initialDevices);
  const [room, setRoom] = useState<Room>('all');
  const [events, setEvents] = useState<EventItem[]>(() => scenarioEvents('normal'));
  const [edge, setEdge] = useState<EdgeStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [mobileNav, setMobileNav] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => { const id = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(id); }, []);
  useEffect(() => {
    if (demo) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function refresh() {
      controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), 2500);
      setLoading(true);
      try {
        const response = await fetch('/api/sidecar/status', {signal: controller.signal});
        if (!response.ok) throw new Error('unavailable');
        const data: EdgeStatus = await response.json();
        if (typeof data.enabled !== 'boolean' || typeof data.online !== 'boolean') throw new Error('invalid');
        if (!cancelled) {setEdge(data); setConnected(true);}
      } catch { if (!cancelled) {setConnected(false); setEdge(null);} }
      finally { clearTimeout(deadline); if (!cancelled) {setLoading(false); timer = setTimeout(refresh, 3000);} }
    }
    refresh();
    return () => {cancelled = true; controller?.abort(); clearTimeout(timer);};
  }, [demo]);
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(''), 3500); return () => clearTimeout(id); }, [notice]);

  const nodeOnline = demo ? scenario !== 'offline' : Boolean(connected && edge?.online);
  const liveDevice = edge?.analysis?.devices.find(device => device.device_id === 'uno-soil-rain');
  const s = scenarios[scenario];
  const rain: Sensor = demo ? {value:s.rain,raw:Math.round(900-s.rain*6),state:scenario==='rain'?'WET':'DRY',valid:true} : primarySensor(primary.sample,'rain',clock);
  const soil: Sensor = demo ? {value:s.soil,raw:Math.round(850-s.soil*5.5),state:scenario==='dry'?'DRY':'OK',valid:true} : primarySensor(primary.sample,'soil',clock);
  const risk = demo ? scenario !== 'normal' : !connected || !nodeOnline || Boolean(liveDevice?.issues?.length) || soil.state==='DRY' || rain.state==='WET';
  const date = new Date(clock).toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  const displayEvents:EventItem[]=demo?events:primary.error?[{id:'offline',title:'电脑后端连接中断',detail:'读数暂不可用，正在自动重连',time:'现在',kind:'warn'}]:!primary.sample?[{id:'waiting',title:'等待第一条环境采集',detail:'在硬件电脑启动 USB 采集后，数据将在这里更新',time:'现在',kind:'info'}]:[{id:'sample',title:sampleFresh(primary.sample,clock)?'收到新板环境采集':'环境记录已过期',detail:sampleFresh(primary.sample,clock)?'电脑已保存雨滴与土壤原始记录':'超过 15 秒未更新，暂不显示为当前状态',time:new Date(primary.sample.created_at).toLocaleTimeString('zh-CN'),kind:sampleFresh(primary.sample,clock)?'good':'warn'}];

  function changeScenario(value: Scenario) {setScenario(value); setDevices(initialDevices); setEvents(scenarioEvents(value)); setNotice(`已切换到「${scenarios[value].label}」演示`);}
  function changeMode(value:boolean) {setDemo(value); setEdge(null); setConnected(false); setLoading(!value); setNotice(value?'已进入演示模式，设备操作仅在页面模拟':'已切换真实数据模式，保存与识别操作将请求当前后端');}
  function toggleDevice(id: DeviceId, label: string) {
    if (!demo) return;
    const next = !devices[id]; setDevices(old=>({...old,[id]:!old[id]}));
    const verb = id==='door' ? (next?'解锁':'锁定') : (next?'开启':'关闭');
    setEvents(old => [{id:crypto.randomUUID(),title:`${label}已${verb}（演示）`,detail:'仅更新本页，不向真实设备发送命令',time:new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}),kind:'info' as const},...old].slice(0,8));
    setNotice(`${label}已${verb} · 仅演示`);
  }
  const deviceItems: {id:DeviceId; label:string; room:Room; place:string; icon:LucideIcon; desc:string}[] = [
    {id:'light',label:'客厅灯光',room:'living',place:'客厅',icon:Lightbulb,desc:'旧扩展板 · 灯光控制'},
    {id:'fan',label:'通风风扇',room:'living',place:'客厅',icon:Fan,desc:'旧扩展板 · 风扇控制'},
    {id:'door',label:'入户门锁',room:'entry',place:'玄关',icon:DoorClosed,desc:'门控指令 · 无位置回传'},
    {id:'camera',label:'家庭摄像头',room:'entry',place:'玄关',icon:Camera,desc:'视频预览与识别入口'},
  ];
  return <div className="smart-home design-astryx"><Opening replay={replay}/>
    <a className="skip-link" href="#main">跳转到主要内容</a>
    {mobileNav && <button className="nav-scrim" aria-label="关闭导航" onClick={()=>setMobileNav(false)}/>}
    <aside className={`sidebar ${mobileNav?'open':''}`}>
      <a className="brand" href="#main"><span className="brand-icon"><House size={23}/></span><span><b>栖居<span className="brand-dot">.</span></b><small>SMART HOME</small></span></a>
      <div className="space-selector"><span className="space-icon"><House size={18}/></span><div><strong>我的家</strong><small>智能家居实验空间</small></div><ChevronRight size={15}/></div>
      <p className="nav-caption">工作空间</p>
      <nav aria-label="主要导航">
        <a className={`nav-link ${page==='home'?'active':''}`} href="#home" aria-current={page==='home'?'page':undefined} onClick={()=>setMobileNav(false)}><LayoutDashboard size={19}/><span>家庭概览</span>{page==='home' && <span className="nav-dot"/>}</a>
        {([{label:'设备控制',page:'home',icon:SlidersHorizontal},{label:'历史数据',page:'data',icon:ChartNoAxesCombined},{label:'视觉识别',page:'vision',icon:ScanLine},{label:'门禁与人员',page:'access',icon:ScanFace}]).map(item=><a key={item.page} className={`nav-link ${page===(item.page==='home'?'devices':item.page)?'active':''}`} href={legacy(item.page)} aria-current={page===(item.page==='home'?'devices':item.page)?'page':undefined}><item.icon size={19}/><span>{item.label}</span><ArrowUpRight size={13} className="legacy-arrow"/></a>)}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><div className="note-icon"><Sprout size={21}/></div><strong>感知变化，让家更懂你</strong><p>设备、环境与边缘分析<br/>在这里轻松掌握。</p></div><div className="version"><span className="tiny-dot"/> Astryx 工作台</div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="breadcrumb"><button className="mobile-menu" aria-label="打开导航" onClick={()=>setMobileNav(true)}><Menu size={21}/></button><House size={16}/><span>我的家</span><ChevronRight size={13}/><strong>{pageInfo[page][0]}</strong></div><div className="topbar-right"><MotionButton onClick={()=>setReplay(n=>n+1)}/><span className="date">{date}</span><span className="top-divider"/><Button label="查看最近动态" variant="ghost" icon={<Bell size={18}/>} isIconOnly onClick={()=>{if(page!=='home'){location.hash='home';setNotice('已返回概览，可查看最近动态');}else document.getElementById('events')?.scrollIntoView({behavior:'smooth',block:'center'});}}/><span className="avatar" aria-label="家庭空间">家</span></div></header>
      <main id="main"><div className="page-stage" key={page}>
        <div className="page-heading"><div><div className="overline">{pageInfo[page][1]}</div><h1>{pageInfo[page][0]}<span>{pageInfo[page][2]}</span></h1></div><div className="mode-control"><FlaskConical size={17}/><Switch label="演练模式" value={demo} onChange={changeMode}/></div></div>
        <div className={`mode-banner ${demo?'':'live'}`} role="status"><span className="mode-message">{demo?<FlaskConical size={17}/>:<ShieldCheck size={17}/>}<span><strong>{demo?'演练空间 · 示例数据':'真实数据模式'}</strong><span className="banner-detail">{demo?'练习操作与页面效果，不发送真实设备指令。':'来自当前电脑的采集记录；操作结果以实际回传为准。'}</span></span></span>{demo&&page==='home'?<div className="scenario-controls"><label htmlFor="scenario">场景</label><select id="scenario" value={scenario} onChange={e=>changeScenario(e.target.value as Scenario)}>{Object.entries(scenarios).map(([key,item])=><option key={key} value={key}>{item.label}</option>)}</select><Button label="重置演示场景" variant="ghost" isIconOnly icon={<RotateCcw size={15}/>} onClick={()=>changeScenario(scenario)}/></div>:demo?<Badge label="演示空间" variant="neutral"/>:<Badge label={loading?'正在更新':connected?'后端已连接':'等待连接'} variant={connected?'success':'neutral'}/>}</div>
        {!demo&&<RealReadiness backend={!!primary.checkedAt&&!primary.error} ready={controlReady(primary.status,primary.checkedAt,clock)} hasData={rain.valid||soil.valid} error={primary.error}/>}{page==='home' ? <><div className="overview-grid">
          <Card className="welcome-card" padding={0}><div className="welcome-content"><span className={`status-pill ${risk?'warning':''}`}><span className="tiny-dot"/>{demo?(scenario==='normal'?'家中一切井然有序':scenario==='offline'?'主流程正常，旁路待连接':'有一条环境提醒'):primary.error?'电脑连接暂不可用':!rain.valid&&!soil.valid?'等待有效采集':rain.state==='WET'||soil.state==='DRY'?'有环境状态需要留意':'环境数据持续更新'}</span><h2>小小的家，<br/>看得见的安心。</h2><p>设备与环境一目了然，把关心留给生活。</p><div className="welcome-stats"><span><b>4</b>设备入口</span><i/><span><b>{demo?(scenario==='normal'?'0':'1'):'—'}</b>待关注提醒</span><i/><span><Sun size={17}/>{demo?'演示空间':'实时空间'}</span></div></div><HouseIllustration/></Card>
        </div>
        <section aria-labelledby="device-title"><div className="section-heading"><div><h2 id="device-title">我的设备 <span className="count">4</span></h2><p>{demo?'轻触开关，体验家的响应':'旧板不回传执行状态，请进入设备页查看指令投递结果'}</p></div><div className="room-filter" role="group" aria-label="按空间筛选设备">{([{value:'all',label:'全部空间'},{value:'living',label:'客厅'},{value:'entry',label:'玄关'}] as {value:Room;label:string}[]).map(item=><button key={item.value} className={room===item.value?'selected':''} aria-pressed={room===item.value} onClick={()=>setRoom(item.value)}>{item.label}</button>)}</div></div><div className="device-grid">{deviceItems.filter(item=>room==='all'||item.room===room).map(item=>{const on=demo&&devices[item.id]; const Icon=item.icon; const text=!demo?(item.id==='camera'?'查看采集':'执行未确认'):item.id==='door'?(on?'已解锁':'已锁定'):item.id==='camera'?(on?'预览在线':'预览关闭'):(on?'已开启':'已关闭');return <Card key={item.id} className={`device-card ${on?'on running-'+item.id:''} ${item.id==='light'&&on?'light-on':''}`} padding={0}><div className="device-top"><span className={`device-icon ${item.id}`}><Icon size={24} strokeWidth={1.7}/></span><span className="room-label">{item.place}</span></div><h3>{item.label}</h3><p>{item.desc}</p><div className="device-bottom"><span><span className={`tiny-dot ${!on?'muted':''}`}/>{text}</span>{demo?<Switch label={`${item.label}演练开关`} isLabelHidden value={on} onChange={()=>toggleDevice(item.id,item.label)}/>:<a className="text-link" href={item.id==='camera'?'#vision':'#devices'}>进入 <ArrowUpRight size={14}/></a>}</div></Card>})}</div></section>
        <div className="lower-grid">
          <section aria-labelledby="environment-title"><div className="section-heading"><div><h2 id="environment-title">环境感知</h2><p>关注窗边，也关心每一抹绿意</p></div><span className="subtle-label"><Cable size={13}/>{demo?'模拟采集':'新扩展板 USB'}</span></div><div className="sensor-grid">{([{kind:'rain',title:'雨滴检测',icon:Droplets,sensor:rain,alert:rain.state==='WET',label:rain.state==='WET'?'检测到雨滴':rain.state==='DRY'?'未检测到雨滴':'等待有效数据'},{kind:'soil',title:'土壤状态',icon:Sprout,sensor:soil,alert:soil.state==='DRY',label:soil.state==='DRY'?'报告干燥':soil.state==='OK'?'未报告干燥':'等待有效数据'}] as const).map(item=><Card key={item.kind} className={`sensor-card ${item.alert?'sensor-alert':''}`} padding={0}><div className="sensor-heading"><span><item.icon size={18}/>{item.title}</span><span className={`sensor-status ${item.alert?'warn':''}`}>{item.label}</span></div><div className="sensor-value"><strong key={item.sensor.value??'unknown'}>{item.sensor.value??'—'}</strong><span>{item.sensor.value!==null?'%':''}</span><small>相对读数</small></div>{demo?<Sparkline kind={item.kind} alert={item.alert}/>:<div className="real-chart-placeholder"><Activity size={17}/>{item.sensor.valid?'当前采集有效，历史记录可在数据页查询':'等待电脑采集，超过 15 秒的记录不显示读数'}</div>}<div className="sensor-meta"><span>{demo?'演示趋势示意':`最近接收 ${primary.sample?new Date(primary.sample.created_at).toLocaleTimeString('zh-CN'):'尚无数据'}`}</span><span>原始值 {item.sensor.raw??'—'}</span></div></Card>)}</div><p className="sensor-footnote"><Info size={12}/> 相对百分比未校准为物理含水率；设备报告状态不等于现场判断。</p></section>
          <section id="events" aria-labelledby="events-title"><div className="section-heading"><div><h2 id="events-title">最近动态</h2><p>{demo?'演示场景与操作记录':'当前节点与采集状态'}</p></div><Badge label={demo?'演示':'实时'} variant="neutral"/></div><Card className="events-card" padding={0}><ol>{displayEvents.slice(0,3).map(item=><li key={item.id}><span className={`event-icon ${item.kind}`}>{item.kind==='warn'?<CircleAlert size={16}/>:item.kind==='good'?<CircleCheck size={16}/>:<Activity size={16}/>}</span><div><strong>{item.title}</strong><p>{item.detail}</p><time>{item.time}</time></div></li>)}</ol><a className="event-more" href={legacy('data')}>前往历史数据 <ArrowUpRight size={14}/><span>查看记录</span></a></Card></section>
        </div>
        <section className="capability-section" aria-label="软件功能入口"><div className="section-heading"><div><h2>探索更多能力</h2><p>从感知，到识别，再到有据可查</p></div><span className="subtle-label">设备 · 视觉 · 门禁 · 数据</span></div><div className="capability-grid">{([{title:'YOLO 视觉识别',text:'查看摄像头画面与物体检测结果',page:'vision',icon:ScanLine,color:'blue'},{title:'门禁与授权人员',text:'管理人员信息，查看人脸验证记录',page:'access',icon:ScanFace,color:'purple'},{title:'历史数据查询',text:'查看传感器记录与统计趋势',page:'data',icon:ChartNoAxesCombined,color:'teal'}]).map(item=><a key={item.page} className="capability" href={legacy(item.page)}><span className={`capability-icon ${item.color}`}><item.icon size={23}/></span><div><h3>{item.title}</h3><p>{item.text}</p></div><ArrowUpRight size={18}/></a>)}</div></section>
        </> : <Pages key={`${page}-${demo}`} page={page} ui={ui} demo={demo} devices={devices} toggleDevice={toggleDevice} notify={setNotice} primary={primary} now={clock}/>}
        <footer className="page-footer"><span><House size={13}/> 栖居 · 智能家居实验项目</span><span>{demo?'演示数据与真实设备隔离':'真实数据 · 连接状态每 3 秒更新'}<span className="footer-dot">·</span>课程项目 · 界面预览</span></footer>
      </div></main>
    </div>
    {notice && <div className="notice" role="status"><CircleCheck size={18}/>{notice}<button onClick={()=>setNotice('')} aria-label="关闭提示"><X size={14}/></button></div>}
  </div>;
}
