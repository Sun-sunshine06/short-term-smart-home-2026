export type Scenario = 'normal' | 'rain' | 'dry' | 'offline';
export type Room = 'all' | 'living' | 'entry';
export type DeviceId = 'light' | 'fan' | 'door' | 'camera';
export type DeviceState = Record<DeviceId, boolean>;
export type Sensor = { value: number | null; raw: number | null; state: string; valid: boolean };
export type EventItem = { id: string; title: string; detail: string; time: string; kind: 'good' | 'warn' | 'info' };
export const scenarios: Record<Scenario, { label: string; description: string; rain: number; soil: number }> = {
  normal: { label: '日常状态', description: '环境平稳，所有节点正常连接', rain: 12, soil: 63 },
  rain: { label: '雨天提醒', description: '雨滴状态变化，生成一条环境提醒', rain: 78, soil: 63 },
  dry: { label: '土壤干燥', description: '持续报告干燥，提示查看盆栽', rain: 12, soil: 21 },
  offline: { label: '节点离线', description: '香橙派不可用，电脑主流程继续', rain: 12, soil: 63 },
};
export const initialDevices: DeviceState = { light: true, fan: false, door: false, camera: true };
export type EdgeDevice = {
  device_id: string; data_status: string; quality: string; expires_at?: number;
  received_at?: number; analyzed_at?: number; source_seq?: number;
  valid?: Record<string, number | string>; issues?: { field: string; reason: string }[];
  dry_active?: string[]; events?: { event_id: string; kind: string; field?: string; from?: string; to?: string }[];
};
export type EdgeStatus = {
  enabled: boolean; online: boolean; pending: number; dropped: number; errors: number;
  analysis?: { node_id: string; devices: EdgeDevice[]; last_error?: string | null; record_count: number } | null;
};
export function liveSensor(device: EdgeDevice | undefined, prefix: 'rain' | 'soil', online: boolean): Sensor {
  const valid = Boolean(online && device?.data_status === 'current' && device.expires_at && device.expires_at > Date.now() / 1000);
  const value = device?.valid?.[`${prefix}_percent`];
  const raw = device?.valid?.[`${prefix}_raw`];
  const state = device?.valid?.[`${prefix}_state`];
  return {
    value: valid && typeof value === 'number' ? value : null,
    raw: valid && typeof raw === 'number' ? raw : null,
    state: valid && typeof state === 'string' ? state : 'UNKNOWN',
    valid: valid && typeof value === 'number',
  };
}
export const timeText = (stamp?: number) => stamp ? new Date(stamp * 1000).toLocaleTimeString('zh-CN', { hour12: false }) : '尚无数据';
export function scenarioEvents(scenario: Scenario): EventItem[] {
  const time = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', hour12: false});
  const common: EventItem[] = [
    {id:'analysis', title:'边缘分析已完成', detail:'收到雨滴、土壤数据副本', time, kind:'good'},
    {id:'connected', title:'家庭设备准备就绪', detail:'电脑采集与旁路分析独立运行', time, kind:'info'},
  ];
  if (scenario === 'rain') common.unshift({id:'rain',title:'检测到雨滴变化',detail:'设备报告 WET，请留意窗边环境',time,kind:'warn'});
  if (scenario === 'dry') common.unshift({id:'dry',title:'土壤持续报告干燥',detail:'已持续 60 秒，建议检查盆栽',time,kind:'warn'});
  if (scenario === 'offline') return [{id:'offline',title:'香橙派连接中断',detail:'分析结果已过期，电脑采集不受影响',time,kind:'warn'},common[1]];
  return common;
}
