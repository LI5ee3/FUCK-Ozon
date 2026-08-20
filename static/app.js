const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], pages: {timeliness:1,finance:1,returns:1,rfbsReturns:1,stock:1}};
const titles = {overview:"总览",orders:"订单",risk:"SKU风险分析",timeliness:"发货与配送时效",finance:"财务利润",returns:"退货与投诉",stock:"库存",transfer:"数据导入/导出",sync:"独立同步中心",rules:"商品匹配规则",dingtalk:"钉钉机器人",settings:"系统设置"};
const syncNames = {orders:"订单",finance:"财务",returns:"退货",stock:"库存"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => v ? new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(v)).replaceAll("/","-") : "暂无";
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const metric = (v, digits=2, suffix="") => v == null || v === "" ? "暂无" : `${num(v,digits)}${suffix}`;
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时 / ${num(v/24,1)} 天`;
const cell = (v) => v == null || v === "" ? "暂无" : esc(v);
const channelTag = (v) => `<span class="tag channel-${({FBP:"fbp",realFBS:"fbs",WHD:"whd"}[v] || "")}">${esc(v)}</span>`;

function summary(id, cards) {
  $(`#${id}Summary`).innerHTML=cards.map(c=>`<div class="summary-card"><span class="muted">${esc(c[0])}</span><strong>${esc(c[1])}</strong>${c[2]?`<small class="muted">${esc(c[2])}</small>`:""}</div>`).join("");
}
function pager(name, data, loader) {
  const pages=Math.max(1,Math.ceil(data.total/data.size));
  $(`#${name}Info`).textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 条`;
  $(`#${name}Prev`).disabled=data.page<=1; $(`#${name}Next`).disabled=data.page>=pages;
  $(`#${name}Prev`).onclick=()=>{state.pages[name]--;loader()};
  $(`#${name}Next`).onclick=()=>{state.pages[name]++;loader()};
  $("#dataThrough").textContent=`数据截止：${data.data_through?.length===10?data.data_through:bj(data.data_through)}`;
}

async function api(url, options={}) {
  const response = await fetch(url, options);
  if (response.status === 401) { showLogin(); throw new Error("请重新登录"); }
  if (!response.ok) { const body = await response.json().catch(()=>({})); throw new Error(body.detail || `请求失败 ${response.status}`); }
  return response.headers.get("content-type")?.includes("json") ? response.json() : response;
}
function toast(message, error=false) {
  $("#notice").innerHTML = `<div class="toast${error?' error':''}">${esc(message)}</div>`;
  setTimeout(()=>$("#notice").replaceChildren(), 3500);
}
function showLogin(){ $("#shell").classList.add("hidden"); $("#login").classList.remove("hidden"); }
function showShell(){ $("#login").classList.add("hidden"); $("#shell").classList.remove("hidden"); }

async function loadShops() {
  state.shops = await api("/api/shops");
  const options = state.shops.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join("");
  $("#shopSelect").innerHTML = `<option value="0">两店铺合并（人民币）</option>${options}`;
  $("#importShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#shop1").value = state.shops[0].name; $("#shop2").value = state.shops[1].name;
}
async function loadOverview() {
  const data = await api(`/api/summary?shop_id=${state.shop}`), t=data.totals;
  $("#totalOrders").textContent=t.orders; $("#totalPieces").textContent=t.pieces;
  $("#cancelOrders").textContent=t.cancelled_orders; $("#cancelRate").textContent=pct(t.cancel_rate);
  $("#dataThrough").textContent=`数据截止：${bj(data.data_through)}`;
  $("#channelRows").innerHTML=data.channels.map(r=>`<tr><td>${channelTag(r.channel)}</td><td class="num">${r.orders}</td><td class="num">${r.pieces}</td><td class="risk-col">${r.cancelled_pieces||0}</td></tr>`).join("") || '<tr><td colspan="4" class="muted">暂无数据，请先导入。</td></tr>';
}
async function loadOrders() {
  const q=encodeURIComponent($("#orderSearch").value), channel=encodeURIComponent($("#channelFilter").value);
  const data=await api(`/api/orders?shop_id=${state.shop}&channel=${channel}&q=${q}&page=${state.page}`); state.total=data.total;
  $("#orderList").innerHTML=data.items.map(o=>`<article class="order-card"><div class="order-head"><div><strong>${esc(o.posting_number)}</strong> ${channelTag(o.channel)}</div><span>${esc(o.shop_name)}</span></div><div class="order-meta"><span>${bj(o.created_at)}</span><span>${esc(o.status_raw)}</span><span>${o.amount_original==null?'金额暂无':`${o.amount_original.toFixed(2)} ${esc(o.amount_currency)}`}</span></div>${o.items.map(i=>`<div class="product-row"><span title="${esc(i.product_name_raw)}">${esc(i.product_name_raw)} · SKU ${esc(i.sku)}</span><span>× ${i.quantity}</span></div>`).join("")}<div class="muted">${o.cost_cny==null?'成本暂无':`订单总成本 ¥${o.cost_cny.toFixed(4)}${o.items.length>1?'；SKU成本暂无':''}`}</div>${o.cancel_reason_raw?`<div class="exception">${esc(o.cancel_reason_raw)}</div>`:""}${o.data_anomaly?'<div class="exception">数据异常</div>':""}</article>`).join("") || '<div class="panel muted">没有匹配订单。</div>';
  const pages=Math.max(1,Math.ceil(data.total/data.size)); $("#pageInfo").textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 个订单`;
  $("#prevPage").disabled=state.page<=1; $("#nextPage").disabled=state.page>=pages;
}
async function loadRisk() {
  const rows=await api(`/api/risk?shop_id=${state.shop}`);
  $("#riskRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)} / ${channelTag(r.channel)}</td><td title="${esc(r.product_name)}">${esc(r.sku)}</td><td class="num">${r.valid_pieces}</td><td class="risk-col">${pct(r.cancelled_rate)}</td><td class="risk-col">${pct(r.unclaimed_rate)}</td><td class="risk-col">${pct(r.customs_rate)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">暂无数据。</td></tr>';
}
async function loadTimeliness() {
  const data=await api(`/api/timeliness?shop_id=${state.shop}&page=${state.pages.timeliness}`), s=data.summary;
  summary("timeliness",[["有效订单",num(s.orders,0)],["已有发货时间",num(s.shipped_orders,0)],["平均发货耗时",hours(s.avg_ship_hours)],["平均配送耗时",hours(s.avg_delivery_hours)]]);
  $("#timelinessRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)} / ${channelTag(r.channel)}</td><td>${esc(r.posting_number)}</td><td>${bj(r.created_at)}</td><td>${bj(r.shipped_at)}</td><td>${bj(r.delivered_at)}</td><td class="num">${hours(r.ship_hours)}</td><td class="num">${hours(r.delivery_hours)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("timeliness",data,loadTimeliness);
}
async function loadFinance() {
  const data=await api(`/api/finance?shop_id=${state.shop}&page=${state.pages.finance}`);
  summary("finance",[["流水记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.amount)} ${s.currency}`,`销售计提 ${num(s.accruals)} · 销售佣金 ${num(s.commission)}`])]);
  $("#financeRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.occurred_at)}</td><td>${cell(r.operation_type)}</td><td>${cell(r.posting_number)}</td><td class="num">${metric(r.amount)} ${esc(r.currency)}</td><td class="num">${metric(r.accruals)} ${esc(r.currency)}</td><td class="num">${metric(r.commission)} ${esc(r.currency)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("finance",data,loadFinance);
}
async function loadReturns() {
  const data=await api(`/api/returns?shop_id=${state.shop}&page=${state.pages.returns}`);
  $("#returnsCount").textContent=data.total;
  summary("returns",[["取消记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.quantity,0)} 件`,`共 ${num(s.records,0)} 条记录`])]);
  $("#returnsRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.occurred_at)}</td><td>${cell(r.posting_number)}</td><td><span class="cell-text" title="${esc(r.product_name)}">${cell(r.sku)} / ${cell(r.product_name)}</span></td><td class="num">${num(r.quantity,0)}</td><td><span class="cell-text" title="${esc(r.reason)}">${cell(r.reason)}</span></td><td>${cell(r.status||r.type)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("returns",data,loadReturns);
}
async function loadRfbsReturns() {
  const data=await api(`/api/rfbs-returns?shop_id=${state.shop}&page=${state.pages.rfbsReturns}`);
  $("#rfbsReturnsCount").textContent=data.total;
  summary("rfbsReturns",[["退货申请",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.records,0)} 条申请`])]);
  $("#rfbsReturnsRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.created_at)}</td><td>${cell(r.return_number)}</td><td>${cell(r.status_name||r.status_raw)}</td><td>${cell(r.posting_number)}</td><td><span class="cell-text" title="${esc(r.product_name)}">${cell(r.sku)} / ${cell(r.product_name)}</span></td></tr>`).join("") || '<tr><td colspan="6" class="muted">暂无退货申请。</td></tr>';
  pager("rfbsReturns",data,loadRfbsReturns);
}
const loadReturnPage=()=>Promise.all([loadReturns(),loadRfbsReturns()]);
async function loadStock() {
  const data=await api(`/api/stock?shop_id=${state.shop}&page=${state.pages.stock}`);
  summary("stock",[["最新商品",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.present,0)} 可用`,`商品 ${num(s.products,0)} · 预留 ${num(s.reserved,0)}`])]);
  $("#stockRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${cell(r.offer_id)}</td><td>${cell(r.product_id)}</td><td>${cell(r.types)}</td><td class="num">${num(r.present,0)}</td><td class="num">${num(r.reserved,0)}</td><td>${bj(r.observed_at)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("stock",data,loadStock);
}
async function loadImports() {
  const rows=await api("/api/imports");
  $("#importRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${esc(r.kind)}</td><td>${esc(r.filename)}</td><td class="num">${r.row_count}</td><td>${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">暂无导入记录。</td></tr>';
}
async function loadSync() {
  const rows=await api("/api/sync");
  $("#syncRows").innerHTML=rows.map(r=>{const total=Math.max(1,Number(r.progress_total||1)),done=Number(r.progress_done||0),percent=Math.round(done/total*100),status=r.status==='failed'?'失败':r.status==='success'?'成功':'进行中';return `<tr><td>${esc(r.shop_name)}</td><td>${esc(syncNames[r.module]||r.module)}</td><td><div>${status} · ${done}/${total} · ${percent}%${r.records?` · ${num(r.records,0)} 条`:''}</div><div class="sync-progress" role="progressbar" aria-label="${esc(syncNames[r.module]||r.module)}拉取进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>${r.status==='running'&&r.current_from?`<small class="muted">当前：${esc(r.current_from.slice(0,10))} — ${esc(r.current_to.slice(0,10))}</small>`:''}</td><td>${bj(r.started_at)}</td><td class="error">${esc(r.error||'')}</td></tr>`}).join("") || '<tr><td colspan="5" class="muted">暂无拉取记录。</td></tr>';
  return rows;
}
async function loadDingtalk() {
  const data=await api("/api/dingtalk/settings");
  $("#dingtalkConfigured").textContent=data.configured?"机器人已配置":"机器人未配置";
  $("#dingEnabled").checked=data.daily_enabled; $("#dingTime").value=data.push_time;
  document.querySelectorAll("#dingWeekdays input").forEach(input=>input.checked=data.weekdays.includes(Number(input.value)));
  $("#dingtalkLast").textContent=data.last_run?`${data.last_run.stats_date} · ${data.last_run.status==='success'?'发送成功':data.last_run.status==='failed'?'发送失败':'发送中'}${data.last_run.sent_at?` · ${bj(data.last_run.sent_at)}`:""}${data.last_run.error?` · ${data.last_run.error}`:""}`:"暂无发送记录";
}
async function loadPushSettings() {
  const shops=await api("/api/ozon/push-settings");
  $("#pushShops").innerHTML=shops.map(s=>`<div class="summary-card"><div class="panel-title"><strong>${esc(s.name)}</strong><span class="tag">${esc(s.connection_status)}</span></div><label>seller_id<input id="pushSeller${s.id}" inputmode="numeric" value="${esc(s.seller_id||'')}" required></label><label>回调URL<input id="pushUrl${s.id}" value="${esc(s.callback_url)}" readonly></label><button type="button" data-copy-push="${s.id}">复制回调URL</button><p class="muted">最近 Ping：${bj(s.last_ping_at)}<br>最近业务事件：${bj(s.last_business_event_at)}<br>最近失败：${bj(s.last_failure_at)}${s.last_error?` · ${esc(s.last_error)}`:""}</p><small class="muted">${s.event_types.map(esc).join(" · ")}</small></div>`).join("");
}
async function loadPage(page) {
  if(page==="overview") return loadOverview(); if(page==="orders") return loadOrders();
  if(page==="risk") return loadRisk();
  const loaders={timeliness:loadTimeliness,finance:loadFinance,returns:loadReturnPage,stock:loadStock};
  if(loaders[page]) return loaders[page](); if(page==="transfer") return loadImports(); if(page==="sync") return loadSync(); if(page==="dingtalk") return loadDingtalk(); if(page==="settings") return loadPushSettings();
}
function openPage(page) {
  document.querySelectorAll(".page").forEach(e=>e.classList.toggle("active",e.id===page));
  document.querySelectorAll("#nav button").forEach(e=>e.classList.toggle("active",e.dataset.page===page));
  $("#pageTitle").textContent=titles[page]; loadPage(page).catch(e=>toast(e.message,true));
}

$("#loginForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});showShell();await loadShops();await loadOverview()}catch(err){$("#loginError").textContent=err.message}});
$("#nav").addEventListener("click",e=>{if(e.target.dataset.page)openPage(e.target.dataset.page)});
$("#shopSelect").addEventListener("change",e=>{state.shop=Number(e.target.value);state.page=1;Object.keys(state.pages).forEach(k=>state.pages[k]=1);const page=$(".page.active").id;loadPage(page).catch(err=>toast(err.message,true))});
$("#orderFilterForm").addEventListener("submit",e=>{e.preventDefault();state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#orderSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#orderFilterForm").requestSubmit()}});
$("#channelFilter").addEventListener("change",()=>{state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#returnTabs").onclick=e=>{const tab=e.target.closest("[data-return-tab]")?.dataset.returnTab;if(!tab)return;document.querySelectorAll("[data-return-tab]").forEach(button=>button.classList.toggle("active",button.dataset.returnTab===tab));document.querySelectorAll(".return-tab").forEach(panel=>panel.classList.toggle("active",panel.id===`returns-${tab}`))};
$("#prevPage").onclick=()=>{state.page--;loadOrders()}; $("#nextPage").onclick=()=>{state.page++;loadOrders()};
$("#shopForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:$("#shop1").value,2:$("#shop2").value})});await loadShops();await loadPushSettings();toast("店铺名称已更新")}catch(err){toast(err.message,true)}});
$("#pushForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/ozon/push-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:$("#pushSeller1").value,2:$("#pushSeller2").value})});await loadPushSettings();toast("seller_id 已保存")}catch(err){toast(err.message,true)}});
$("#pushShops").addEventListener("click",async e=>{const id=e.target.dataset.copyPush;if(!id)return;await navigator.clipboard.writeText($("#pushUrl"+id).value);toast("回调URL已复制")});
$("#dingtalkForm").addEventListener("submit",async e=>{e.preventDefault();try{const weekdays=[...document.querySelectorAll("#dingWeekdays input:checked")].map(input=>Number(input.value));await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({daily_enabled:$("#dingEnabled").checked,push_time:$("#dingTime").value,weekdays})});toast("钉钉设置已保存");await loadDingtalk()}catch(err){toast(err.message,true)}});
$("#dingTestButton").onclick=async e=>{e.target.disabled=true;try{await api("/api/dingtalk/test",{method:"POST"});toast("测试消息已发送")}catch(err){toast(err.message,true)}finally{e.target.disabled=false}};
$("#importForm").addEventListener("submit",async e=>{e.preventDefault();const file=$("#importFile").files[0],shop=$("#importShop").value,kind=$("#importKind").value;if(!file||!shop)return;try{const result=await api(`/api/import/${kind}?shop_id=${shop}`,{method:"POST",headers:{"X-Filename":encodeURIComponent(file.name)},body:file});toast(`已导入 ${result.rows} 行`);await loadImports()}catch(err){toast(err.message,true)}});
$("#exportOrders").onclick=()=>{location.href=`/api/export/orders?shop_id=${state.shop}`};
$("#syncButtons").innerHTML=Object.entries(syncNames).map(([key,name])=>`<button data-module="${key}">${name}拉取</button>`).join("");
const today=new Date(); today.setHours(0,0,0,0);
const isoDate=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const localDate=value=>{const [year,month,day]=value.split("-").map(Number);return new Date(year,month-1,day)};
const shiftDays=(date,amount)=>new Date(date.getFullYear(),date.getMonth(),date.getDate()+amount);
const shiftMonths=(date,amount)=>new Date(date.getFullYear(),date.getMonth()+amount,1);
const threeMonthsAgo=(()=>{const target=new Date(today.getFullYear(),today.getMonth()-3,1);target.setDate(Math.min(today.getDate(),new Date(target.getFullYear(),target.getMonth()+1,0).getDate()));return target})();
const rangeState={start:isoDate(threeMonthsAgo),end:isoDate(today),selecting:false,view:new Date(today.getFullYear(),today.getMonth(),1),preset:"3months"};
const monthNames=["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
function setRange(start,end,label,preset="") {
  rangeState.start=isoDate(start); rangeState.end=isoDate(end); rangeState.selecting=false; rangeState.preset=preset;
  $("#syncFrom").value=rangeState.start; $("#syncTo").value=rangeState.end; $("#dateRangeLabel").textContent=label;
  renderRange();
}
function rangeMonth(date,targetTitle,targetDays) {
  $(targetTitle).textContent=`${monthNames[date.getMonth()]} ${date.getFullYear()}年`;
  const first=new Date(date.getFullYear(),date.getMonth(),1),last=new Date(date.getFullYear(),date.getMonth()+1,0);
  const blanks=(first.getDay()+6)%7,days=[];
  for(let index=0;index<blanks;index++)days.push('<span class="range-blank"></span>');
  for(let day=1;day<=last.getDate();day++){
    const current=new Date(date.getFullYear(),date.getMonth(),day),key=isoDate(current),weekend=current.getDay()===0||current.getDay()===6;
    const inRange=key>=rangeState.start&&key<=rangeState.end,edge=key===rangeState.start||key===rangeState.end;
    days.push(`<button type="button" data-date="${key}" class="${weekend?'weekend ':''}${inRange?'in-range ':''}${edge?'range-edge ':''}${key===isoDate(today)?'today':''}" aria-label="${date.getFullYear()}年${date.getMonth()+1}月${day}日">${day}</button>`);
  }
  $(targetDays).innerHTML=days.join("");
}
function renderRange() {
  rangeMonth(rangeState.view,"#rangeMonthA","#rangeDaysA");
  rangeMonth(shiftMonths(rangeState.view,1),"#rangeMonthB","#rangeDaysB");
  document.querySelectorAll("#rangePresets button").forEach(button=>button.classList.toggle("active",button.dataset.range===rangeState.preset));
}
function choosePreset(name) {
  const choices={today:[today,today,"今天"],"3days":[shiftDays(today,-2),today,"3天内"],"7days":[shiftDays(today,-6),today,"7天内"],"3months":[threeMonthsAgo,today,"三个月内"],all:[new Date(2020,0,1),today,"整个时段"]};
  setRange(...choices[name],name);
}
$("#dateRangeButton").onclick=()=>{const open=$("#dateRangePanel").classList.toggle("hidden");$("#dateRangeButton").setAttribute("aria-expanded",String(!open));renderRange()};
$("#rangePrev").onclick=()=>{rangeState.view=shiftMonths(rangeState.view,-1);renderRange()};
$("#rangeNext").onclick=()=>{rangeState.view=shiftMonths(rangeState.view,1);renderRange()};
$("#rangePresets").onclick=e=>{if(e.target.dataset.range)choosePreset(e.target.dataset.range)};
$("#dateRangePanel").onclick=e=>{e.stopPropagation();const value=e.target.dataset.date;if(!value)return;if(!rangeState.selecting){rangeState.start=value;rangeState.end=value;rangeState.selecting=true;rangeState.preset="";$("#dateRangeLabel").textContent=`${value.replaceAll("-","/")} – 请选择结束日期`}else{const first=localDate(rangeState.start),second=localDate(value);setRange(first<=second?first:second,first<=second?second:first,`${isoDate(first<=second?first:second).replaceAll("-","/")} – ${isoDate(first<=second?second:first).replaceAll("-","/")}`)}$("#syncFrom").value=rangeState.start;$("#syncTo").value=rangeState.end;renderRange()};
document.addEventListener("click",e=>{if(!e.target.closest(".date-range-wrap")){$("#dateRangePanel").classList.add("hidden");$("#dateRangeButton").setAttribute("aria-expanded","false")}});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){$("#dateRangePanel").classList.add("hidden");$("#dateRangeButton").setAttribute("aria-expanded","false")}});
choosePreset("3months");
$("#sync > .panel:first-child > .muted").textContent="每个按钮只调用本模块；长时段按自然月串行拉取，某月失败即停止。库存仅拉取一次当前快照。";
async function waitForSync(runId,module){for(;;){const task=await api(`/api/sync/${runId}`);await loadSync();if(task.status!=="running"){if(task.status==="success")toast(`${syncNames[module]}拉取完成：${num(task.records,0)} 条`);else toast(task.error||"拉取失败",true);return}await new Promise(resolve=>setTimeout(resolve,1000))}}
$("#syncButtons").onclick=async e=>{const module=e.target.dataset.module;if(!module)return;if(!state.shop)return toast("请先在左上角选择一个店铺",true);if(rangeState.preset==="all"&&!confirm("整个时段将按自然月逐段拉取，耗时可能较长。确认开始？"))return;e.target.disabled=true;try{const task=await api(`/api/sync/${module}?shop_id=${state.shop}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:$("#syncFrom").value,to:$("#syncTo").value})});await loadSync();await waitForSync(task.run_id,module)}catch(err){toast(err.message,true);await loadSync()}finally{e.target.disabled=false}};
$("#themeButton").onclick=()=>{const dark=document.documentElement.dataset.theme!=="dark";document.documentElement.dataset.theme=dark?"dark":"";localStorage.setItem("theme",dark?"dark":"light")};
$("#logoutButton").onclick=async()=>{await api("/api/logout",{method:"POST"});showLogin()};
if(localStorage.getItem("theme")==="dark")document.documentElement.dataset.theme="dark";

(async()=>{const s=await api("/api/session");if(!s.authenticated)return showLogin();showShell();await loadShops();await loadOverview()})().catch(e=>toast(e.message,true));
