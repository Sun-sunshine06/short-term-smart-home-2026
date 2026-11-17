import {test} from 'node:test';
import assert from 'node:assert/strict';
import {demoHistory,filterHistory,csvHistory} from '../src/pages-data.ts';
test('时间筛选包含起止端点，并按时间排序',()=>{
 const rows=demoHistory();
 const result=filterHistory([...rows].reverse(),rows[16].created_at,rows[20].created_at);
 assert.equal(result.length,5);assert.equal(result[0].id,17);assert.equal(result[4].id,21);
 assert.equal(filterHistory(rows,'2100-01-01T00:00','2100-01-02T00:00').length,0);
});
test('CSV 导出保留零值、空值并转义来源文本',()=>{
 const row={...demoHistory()[0],temperature:null,light_level:0,source:'=SUM(1,2)"'};
 const csv=csvHistory([row]);assert.ok(csv.includes('"","0"'));assert.ok(csv.includes('"\'=SUM(1,2)"""'));assert.ok(csv.startsWith('\uFEFF'));
});
