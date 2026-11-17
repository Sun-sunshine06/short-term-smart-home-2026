async function refreshSidecar() {
  const summary = document.getElementById('sidecarSummary');
  const devices = document.getElementById('sidecarDevices');
  try {
    const response = await fetch('/api/sidecar/status', {signal: AbortSignal.timeout(2000)});
    if (!response.ok) throw new Error('status unavailable');
    const status = await response.json();
    summary.textContent = !status.enabled ? '未启用旁路转发' :
      `${status.online ? '节点在线' : '节点离线或尚未连接'} · 待发送 ${status.pending}/${status.capacity} · 已发送 ${status.sent} · 合并或丢弃 ${status.dropped} · 未具备转发条件 ${status.skipped} · 传输错误 ${status.errors}`;
    devices.replaceChildren();
    const reasonNames = {missing: '缺失', invalid: '无效', unknown: '未知', out_of_range: '超出配置范围'};
    const date = value => value ? new Date(value * 1000).toLocaleString() : '尚无';
    for (const device of status.analysis?.devices || []) {
      const row = document.createElement('p');
      const expired = !status.online || !device.expires_at || Date.now() / 1000 > device.expires_at;
      const health = device.data_status === 'never_received' ? '尚未收到数据' : expired || device.data_status === 'timeout' ? '数据超时／结果已过期' :
        device.quality === 'valid' ? '数据有效' : device.quality === 'unknown' ? '数据未知' : '数据有异常';
      const issues = (device.issues || []).map(i => `${i.field}：${reasonNames[i.reason] || i.reason}`).join('，');
      const dry = !expired && device.dry_active?.length ? `；持续报告干燥：${device.dry_active.join('、')}` : '';
      row.textContent = `${device.device_id}：${health}；最近接收 ${date(device.received_at)}；最近分析 ${date(device.analyzed_at)}${issues ? '；' + issues : ''}${dry}`;
      devices.append(row);
    }
    if (status.analysis?.last_error) summary.textContent += ' · 板端存储异常';
  } catch (_) {
    summary.textContent = '暂时无法读取旁路状态，分析结果不可用';
    devices.replaceChildren();
  } finally {
    setTimeout(refreshSidecar, 3000);
  }
}
refreshSidecar();
