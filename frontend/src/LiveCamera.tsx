import { useEffect, useRef, useState } from 'react';

type Box = [number, number, number, number, string, number];

export function LiveCamera({title, enableYolo = false}: {title: string; enableYolo?: boolean}) {
  const [detect, setDetect] = useState(false);
  const [status, setStatus] = useState('正在连接摄像头…');
  const canvas = useRef<HTMLCanvasElement>(null);
  const inference = useRef(false);
  useEffect(() => {
    if (!canvas.current) return;
    const surface = canvas.current;
    const ctx = surface.getContext('2d');
    if (!ctx) return;
    const controller = new AbortController();
    let drawn = 0, lastId = 0, start = performance.now(), lastDrawn = 0, lastInferred = 0;
    async function play() {
      while (!controller.signal.aborted) {
        try {
          const r = await fetch('/api/live/frame?after=' + lastId + '&yolo=' + Number(inference.current),
            {signal: controller.signal, cache: 'no-store'});
          if (!r.ok) throw new Error('等待摄像头重新连接…');
          const bitmap = await createImageBitmap(await r.blob());
          await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
          try {
            if (controller.signal.aborted) return;
            if (surface.width !== bitmap.width || surface.height !== bitmap.height) {
              surface.width = bitmap.width;
              surface.height = bitmap.height;
            }
            ctx!.drawImage(bitmap, 0, 0);
            ctx!.strokeStyle = '#64ffb1';
            ctx!.fillStyle = '#64ffb1';
            ctx!.lineWidth = 2;
            ctx!.font = '16px sans-serif';
            const boxes: Box[] = JSON.parse(r.headers.get('X-Boxes') || '[]');
            if (inference.current) for (const [x, y, right, bottom, label, confidence] of boxes) {
              ctx!.strokeRect(x, y, right - x, bottom - y);
              ctx!.fillText(label + ' ' + Math.round(confidence * 100) + '%', x, Math.max(18, y - 4));
            }
          } finally { bitmap.close(); }
          lastId = Number(r.headers.get('X-Frame'));
          const inferred = Number(r.headers.get('X-Inferences'));
          Object.assign(surface.dataset, {drawn: String(++drawn), received: String(lastId), inferred: String(inferred)});
          const elapsed = (performance.now() - start) / 1000;
          if (elapsed >= 1) {
            const fps = ((drawn - lastDrawn) / elapsed).toFixed(1);
            const modelFps = ((inferred - lastInferred) / elapsed).toFixed(1);
            setStatus('画面 ' + fps + ' FPS' + (inference.current ? (r.headers.get('X-Model-Error') === '1' ? ' · YOLO 不可用' : ' · YOLO ' + modelFps + ' FPS') : ''));
            lastDrawn = drawn; lastInferred = inferred; start = performance.now();
          }
        } catch {
          if (controller.signal.aborted) return;
          setStatus('等待摄像头重新连接…');
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }
    }
    void play();
    return () => controller.abort();
  }, []);
  return <section className="surface vision-view" aria-label="摄像头直播">
    <div className="view-top"><strong>{title}</strong>{enableYolo && <label><input type="checkbox" checked={detect}
      onChange={e => {inference.current = e.target.checked; setDetect(e.target.checked);}}/> 实时 YOLO 检测</label>}</div>
    <canvas ref={canvas} width={640} height={480} aria-label="摄像头实时画面"
      style={{display:'block',width:'100%',maxHeight:'55vh',objectFit:'contain',background:'#17252a'}}/>
    <div className="view-bottom">{status}</div>
  </section>;
}

const verificationMessages = {
  waiting: '正在连接实时验证…',
  busy: '正在验证…',
  offline: '等待摄像头画面',
  no_face: '未检测到人脸，请面向摄像头',
  unknown: '未匹配到授权人员',
  unavailable: '识别服务暂不可用',
  empty_gallery: '请先为授权人员添加基准照',
  invalid_gallery: '基准照无法用于识别，请更新照片',
  matched: '身份验证通过',
};

type FaceResult = {state: keyof typeof verificationMessages; name?: string; score?: number; door?: {status: string; command_id?: number}};

export function LiveFaceResult() {
  const [result, setResult] = useState<FaceResult>({state: 'waiting'});
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function verify() {
      try {
        const response = await fetch('/api/live/face', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}', cache: 'no-store', signal: controller.signal});
        const data = await response.json();
        if (!controller.signal.aborted) setResult(data.state in verificationMessages ? data : {state: 'unavailable'});
      } catch {
        if (!controller.signal.aborted) setResult({state: 'unavailable'});
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(verify, 1000);
      }
    }
    void verify();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  return <div className="face-result"><div>
    <strong role="status">{verificationMessages[result.state]}{result.state === 'matched' && ' · ' + result.name}</strong>
    {result.door && <p>{result.door.status === 'link_sent_no_ack' ? '开门指令已发往执行板' :
      result.door.status === 'failed' ? '开门指令投递失败，请检查设备连接' :
      result.door.status === 'unconfirmed' ? '开门指令投递未确认' : '采集板已接收开门指令'}
      {result.door.command_id && ' · #' + result.door.command_id}</p>}
    {typeof result.score === 'number' && <p>相似度 {result.score.toFixed(3)}</p>}
  </div></div>;
}
