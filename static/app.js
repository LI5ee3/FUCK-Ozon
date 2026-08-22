const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], complaints:[], csrf:"", pages: {timeliness:1,returns:1,rfbsReturns:1,complaints:1,stock:1}};
const titles = {overview:"总览",orders:"订单",risk:"SKU风险分析",timeliness:"发货与配送时效",returns:"退货与投诉",stock:"库存",transfer:"数据导入/导出",sync:"独立同步中心",rules:"商品匹配规则",dingtalk:"钉钉机器人",settings:"系统设置"};
const syncNames = {orders:"订单",returns:"退货",stock:"库存"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => { if (!v) return "暂无"; const date=new Date(v); return Number.isNaN(date.getTime()) ? "暂无" : new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(date).replaceAll("/","-"); };
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const metric = (v, digits=2, suffix="") => v == null || v === "" ? "暂无" : `${num(v,digits)}${suffix}`;
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时 / ${num(v/24,1)} 天`;
const timingMetric = (label,v,featured=false) => `<div class="timing-metric${featured?' featured':''}"><span>${label}</span><strong>${num(v,1)} 小时</strong><small>${num(v/24,1)} 天</small></div>`;
const completenessMetric = (label,v) => `<div class="completeness-metric"><span>${label}</span><strong>${pct(v)}</strong><progress max="1" value="${Number(v||0)}" aria-label="${label}完整率 ${pct(v)}"></progress></div>`;
const timingSection = (title,samples,insufficient,p50,average,p90,complete) => `<section><div class="timing-section-head"><h3>${title}</h3>${insufficient?'<span class="sample-warning">样本不足</span>':''}</div>${samples?`<div class="timing-metrics">${timingMetric("中位数 P50",p50,true)}${timingMetric("平均",average)}${timingMetric("P90 长尾",p90)}</div>`:'<div class="timing-empty">数据不足</div>'}<div class="timing-meta"><span>有效样本 ${num(samples,0)} 单</span><span>字段完整率 ${pct(complete)}</span></div></section>`;
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
  if(options.method && options.method!=="GET") options.headers={...(options.headers||{}),"X-CSRF-Token":state.csrf};
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
  const shops=[{id:0,name:"两店铺合并"},...state.shops];
  $("#shopOptions").innerHTML=shops.map(s=>`<button type="button" role="option" data-shop="${s.id}" aria-selected="${s.id===state.shop}">${esc(s.name)}</button>`).join("");
  $("#shopPickerValue").textContent=shops.find(s=>s.id===state.shop)?.name||"两店铺合并";
  $("#importShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#complaintShop").innerHTML = `<option value="">请选择</option>${options}`;
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
  $("#orderList").innerHTML=data.items.map(o=>`<article class="order-card"><div class="order-head"><div><strong>${esc(o.posting_number)}</strong> ${channelTag(o.channel)}</div><span>${esc(o.shop_name)}</span></div><div class="order-meta"><span>${bj(o.created_at)}</span><span>${esc(o.status_raw)}</span><span>${o.amount_original==null?'金额暂无':`${o.amount_original.toFixed(2)} ${esc(o.amount_currency)}`}</span></div>${o.items.map(i=>`<div class="product-row"><span title="${esc(i.product_name_raw)}">${esc(i.product_name_raw)} · SKU ${esc(i.sku)}</span><span>× ${i.quantity}</span></div>`).join("")}${o.cancel_reason_raw?`<div class="exception">${esc(o.cancel_reason_raw)}</div>`:""}${o.data_anomaly?'<div class="exception">数据异常</div>':""}</article>`).join("") || '<div class="panel muted">没有匹配订单。</div>';
  document.querySelectorAll(".order-card").forEach((card,index)=>card.insertAdjacentHTML("beforeend",`<button type="button" data-add-complaint="${esc(data.items[index].posting_number)}" data-complaint-shop="${data.items[index].shop_id}">新增投诉</button>`));
  const pages=Math.max(1,Math.ceil(data.total/data.size)); $("#pageInfo").textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 个订单`;
  $("#prevPage").disabled=state.page<=1; $("#nextPage").disabled=state.page>=pages;
}
async function loadRisk() {
  const [rows,reasons]=await Promise.all([api(`/api/risk?shop_id=${state.shop}&grouped=${$("#riskGrouped").checked}`),api(`/api/risk/reasons?shop_id=${state.shop}`)]);
  $("#riskRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)} / ${channelTag(r.channel)}</td><td title="${esc(r.product_name)}">${esc(r.sku)}</td><td class="num">${r.valid_pieces}</td><td class="risk-col">${pct(r.cancelled_rate)}</td><td class="risk-col">${pct(r.unclaimed_rate)}</td><td class="risk-col">${pct(r.customs_rate)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">暂无数据。</td></tr>';
  $("#reasonRows").innerHTML=reasons.items.map(r=>`<tr><td>${esc(r.shop_name)} / ${channelTag(r.channel)}</td><td><button class="link-button" data-reason="${esc(r.reason_raw)}">${esc(r.reason_name)}</button></td><td>${r.orders}</td><td>${r.pieces}</td></tr>`).join("")||'<tr><td colspan="4" class="muted">暂无发货后取消原因。</td></tr>';
}
async function loadTimeliness() {
  const data=await api(`/api/timeliness?shop_id=${state.shop}&page=${state.pages.timeliness}`), s=data.summary;
  summary("timeliness",[["有效订单",num(s.orders,0)],["发货有效样本",num(s.ship_samples,0)],["发货中位数 P50",s.ship_samples?hours(s.p50_ship_hours):"数据不足"],["配送中位数 P50",s.delivery_samples?hours(s.p50_delivery_hours):"数据不足"]]);
  $("#timelinessGroupRows").innerHTML=data.groups.map(r=>`<article class="timing-card"><header class="timing-card-head"><div><strong>${esc(r.shop_name)}</strong>${channelTag(r.channel)}</div><span>${num(r.orders,0)} 个订单</span></header><div class="timing-sections">${timingSection("发货时效",r.ship_samples,r.ship_sample_insufficient,r.p50_ship_hours,r.avg_ship_hours,r.p90_ship_hours,r.shipped_completeness)}${timingSection("配送时效",r.delivery_samples,r.delivery_sample_insufficient,r.p50_delivery_hours,r.avg_delivery_hours,r.p90_delivery_hours,r.delivered_completeness)}<section class="completeness"><h3>字段完整率</h3><div class="completeness-grid">${completenessMetric("创建时间",r.created_completeness)}${completenessMetric("实际发货时间",r.shipped_completeness)}${completenessMetric("实际签收时间",r.delivered_completeness)}</div></section></div></article>`).join("") || '<div class="timing-empty">暂无分组数据。</div>';
  $("#timelinessRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)} / ${channelTag(r.channel)}</td><td>${esc(r.posting_number)}</td><td>${bj(r.created_at)}</td><td>${bj(r.shipped_at)}</td><td>${bj(r.delivered_at)}</td><td class="num">${hours(r.ship_hours)}</td><td class="num">${hours(r.delivery_hours)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("timeliness",data,loadTimeliness);
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
  $("#rfbsReturnsRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.created_at)}</td><td>${cell(r.return_number)}<br><small>${cell(r.order_number)}</small></td><td>${cell(r.status_name||r.status_raw)}<br><small>${cell(r.compensation_status)}</small></td><td>${cell(r.posting_number)}</td><td><span class="cell-text" title="${esc(r.product_name)}">${cell(r.sku)} / ${cell(r.product_name)}</span>${r.buyer_comment_raw?`<br><small>买家原文：${esc(r.buyer_comment_raw)}</small>`:""}</td><td>${num(r.quantity,0)} / ${metric(r.product_amount)} ${esc(r.product_currency||"")}</td><td>${cell(r.reason_name||r.reason_raw)}<br><small>${bj(r.logistic_return_at)}</small></td></tr>`).join("") || '<tr><td colspan="8" class="muted">暂无退货申请。</td></tr>';
  pager("rfbsReturns",data,loadRfbsReturns);
}
async function loadComplaints(){const q=encodeURIComponent($("#complaintQuery").value),status=$("#complaintStatus").value,data=await api(`/api/complaints?shop_id=${state.shop}&q=${q}&status=${status}&page=${state.pages.complaints}`);state.complaints=data.items;$("#complaintsCount").textContent=data.total;$("#complaintRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${esc(r.posting_number)}</td><td>${esc(r.complaint_number)}</td><td>${bj(r.complaint_at)} / ${esc(r.channel)}</td><td>${r.resolved==null?"未填写":r.resolved?"是":"否"}</td><td>${r.package_returned==null?"未填写":r.package_returned?"是":"否"}</td><td>${r.compensation_amount==null?"暂无":`${num(r.compensation_amount)} ${esc(r.compensation_currency)}`}</td><td>${esc(r.notes||"")} <button data-edit-complaint="${r.shop_id}:${esc(r.complaint_number)}">编辑</button></td></tr>`).join("")||'<tr><td colspan="8" class="muted">暂无投诉。</td></tr>';pager("complaints",data,loadComplaints)}
const loadReturnPage=()=>Promise.all([loadReturns(),loadRfbsReturns(),loadComplaints()]);
async function loadStock() {
  const data=await api(`/api/stock?shop_id=${state.shop}&page=${state.pages.stock}`);
  summary("stock",[["在售 SKU",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.present,0)} 可售`,`预留 ${num(s.reserved,0)} · ${num(s.products,0)} 个 SKU`])]);
  $("#stockFormula").textContent=data.formula;
  $("#stockRows").innerHTML=data.items.map(r=>`<article class="stock-card"><header class="stock-card-head"><div><strong>SKU ${esc(r.sku)}</strong><small>${r.offer_id?`货号 ${esc(r.offer_id)}`:r.product_id?`商品 ${esc(r.product_id)}`:""}</small></div><div><span>${esc(r.shop_name)}</span><strong>${num(r.present,0)} 可售</strong><small>${num(r.reserved,0)} 预留</small></div></header><div class="stock-channel-grid">${r.channels.map(c=>`<section class="stock-channel"><div class="stock-channel-head">${c.channel==="库存事件"?'<span class="tag">库存事件</span>':channelTag(c.channel)}<small>${esc(c.source)}</small></div><div class="stock-channel-values"><div><span>可售</span><strong>${num(c.present,0)}</strong></div><div><span>预留</span><strong>${num(c.reserved,0)}</strong></div></div><small>${c.warehouse_id?`仓库 ${esc(c.warehouse_id)} · `:""}更新 ${bj(c.observed_at)}</small></section>`).join("")}</div><footer class="stock-card-foot"><span>近 7 天销量 <strong>${num(r.sales_7,0)}</strong></span><span>近 30 天销量 <strong>${num(r.sales_30,0)}</strong></span><span>预计可售 <strong>${r.days_available==null?"无法估算":`${num(r.days_available,1)} 天`}</strong></span></footer></article>`).join("") || '<div class="stock-empty">暂无非零库存。</div>';
  pager("stock",data,loadStock);
}
async function loadImports() {
  const rows=await api("/api/imports");
  $("#importRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${esc(r.kind)}</td><td>${esc(r.filename)}</td><td class="num">${r.row_count}</td><td>${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">暂无导入记录。</td></tr>';
}
async function loadSync() {
  const rows=await api("/api/sync");
  $("#syncRows").innerHTML=rows.map(r=>{const total=Math.max(1,Number(r.progress_total||1)),done=Number(r.progress_done||0),percent=Math.round(done/total*100),status=r.status==='failed'?'失败':r.status==='success'?'成功':'进行中';return `<tr><td>${esc(r.shop_name)}</td><td>${esc(syncNames[r.module]||r.module)}${r.run_source==='auto'?' · 自动':''}</td><td><div>${status} · ${done}/${total} · ${percent}%${r.records?` · ${num(r.records,0)} 条`:''}</div><div class="sync-progress" role="progressbar" aria-label="${esc(syncNames[r.module]||r.module)}拉取进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>${r.status==='running'&&r.current_from?`<small class="muted">当前：${esc(r.current_from.slice(0,10))} — ${esc(r.current_to.slice(0,10))}</small>`:''}</td><td>${bj(r.started_at)}</td><td class="error">${esc(r.error||'')}</td></tr>`}).join("") || '<tr><td colspan="5" class="muted">暂无拉取记录。</td></tr>';
  return rows;
}
async function loadAutoSync(){const rows=await api("/api/auto-sync-settings");$("#autoSyncCards").innerHTML=rows.map(r=>`<div class="auto-sync-card"><div class="panel-title"><strong>${esc(state.shops.find(s=>s.id===r.shop_id)?.name)} · ${esc(syncNames[r.module])}</strong><label class="check-row"><input id="autoEnabled-${r.shop_id}-${r.module}" type="checkbox" ${r.enabled?'checked':''}>启用</label></div><label>每天拉取时间（北京时间）<input id="autoTime-${r.shop_id}-${r.module}" type="time" value="${esc(r.run_time)}" required></label><label>拉取范围${r.module==='stock'?'（库存为当前快照）':'（最近 N 天）'}<input id="autoRange-${r.shop_id}-${r.module}" type="number" min="1" max="365" value="${Number(r.range_days)}" ${r.module==='stock'?'disabled':''} required></label></div>`).join("")}
async function loadDingtalk() {
  const data=await api("/api/dingtalk/settings");
  $("#dingtalkConfigured").textContent=data.configured?"机器人已配置":"机器人未配置";
  $("#dingEnabled").checked=data.daily_enabled; $("#dingTime").value=data.push_time;
  document.querySelectorAll("#dingWeekdays input").forEach(input=>input.checked=data.weekdays.includes(Number(input.value)));
  $("#dingtalkLast").textContent=data.last_run?`${data.last_run.stats_date} · ${data.last_run.status==='success'?'发送成功':data.last_run.status==='failed'?'发送失败':'发送中'}${data.last_run.sent_at?` · ${bj(data.last_run.sent_at)}`:""}${data.last_run.error?` · ${data.last_run.error}`:""}`:"暂无发送记录";
}
async function loadRules(){const data=await api("/api/product-rules");$("#ruleKeyNote").textContent=data.key_note;$("#ruleLists").innerHTML=`<h3>短名称</h3>${data.short_names.map(r=>`<p>${esc(r.key_type)}:${esc(r.key_value)} → ${esc(r.short_name)}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>合并组</h3>${data.groups.map(r=>`<p>${esc(r.name)}：${esc(r.key_type||"暂无成员")} ${esc(r.key_value||"")} ${r.key_type?`<button data-ungroup-type="${esc(r.key_type)}" data-ungroup-value="${esc(r.key_value)}">解除</button>`:""}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>品牌规则</h3>${data.brands.map(r=>`<p>${esc(r.brand_name)} · ${esc(r.keyword)} · 优先级 ${r.priority}${r.conflict?' · 冲突':''}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>匹配预览</h3>${data.products.filter(r=>r.matched_brand).slice(0,20).map(r=>`<p>${esc(r.product_name)} → ${esc(r.matched_brand)}</p>`).join("")||'<p class="muted">暂无品牌命中</p>'}`}
async function loadSettings(){$("#probeShops").innerHTML=state.shops.map(s=>`<article class="settings-shop-card"><div class="settings-shop-head"><div><span>店铺 ${s.id}</span><strong>${esc(s.name)}</strong></div><button class="primary" data-probe="${s.id}">检测连接与权限</button></div><div id="probeResult${s.id}" class="settings-probe-result"><span class="probe-state">尚未检测</span><p>检测后将在这里显示店铺身份、角色及各模块权限。</p></div></article>`).join("")}
function probeResult(result){if(!result.valid)return `<span class="probe-state is-error">连接失败</span><p>${esc(result.error||"凭据或网络异常")}</p>`;const identity=result.identity||{},company=identity.company||{},name=company.name||identity.name||"店铺身份已确认",seller=identity.seller_id||identity.client_id||"未返回",inn=company.inn||identity.inn||"未返回",roles=(result.roles||[]).join("、")||"未返回";return `<span class="probe-state is-ok">凭据有效</span><dl class="probe-facts"><div><dt>店铺身份</dt><dd>${esc(name)}</dd></div><div><dt>Seller ID</dt><dd>${esc(seller)}</dd></div><div><dt>税号 INN</dt><dd>${esc(inn)}</dd></div><div><dt>角色</dt><dd>${esc(roles)}</dd></div></dl><div class="probe-permissions">${Object.entries(result.permissions||{}).map(([module,value])=>`<span class="${value==="可用"?'is-ok':'is-missing'}"><strong>${esc(syncNames[module]||module)}</strong>${esc(value)}</span>`).join("")||'<span class="is-missing">未返回模块权限</span>'}</div>`}
async function loadPage(page) {
  if(page==="overview") return loadOverview(); if(page==="orders") return loadOrders();
  if(page==="risk") return loadRisk();
  const loaders={timeliness:loadTimeliness,returns:loadReturnPage,stock:loadStock};
  if(loaders[page]) return loaders[page](); if(page==="transfer") return loadImports(); if(page==="sync") return Promise.all([loadSync(),loadAutoSync()]); if(page==="rules") return loadRules(); if(page==="dingtalk") return loadDingtalk(); if(page==="settings") return loadSettings();
}
function openPage(page) {
  document.querySelectorAll(".page").forEach(e=>e.classList.toggle("active",e.id===page));
  document.querySelectorAll("#nav button").forEach(e=>e.classList.toggle("active",e.dataset.page===page));
  $("#pageTitle").textContent=titles[page]; loadPage(page).catch(e=>toast(e.message,true));
}

$("#loginForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});const session=await api("/api/session");state.csrf=session.csrf_token;showShell();await loadShops();await loadOverview()}catch(err){$("#loginError").textContent=err.message}});
$("#nav").addEventListener("click",e=>{const button=e.target.closest("[data-page]");if(button)openPage(button.dataset.page)});
$("#shopPickerButton").onclick=()=>{const hidden=$("#shopOptions").classList.toggle("hidden");$("#shopPickerButton").setAttribute("aria-expanded",String(!hidden))};
$("#shopOptions").onclick=e=>{const option=e.target.closest("[data-shop]");if(!option)return;state.shop=Number(option.dataset.shop);state.page=1;Object.keys(state.pages).forEach(k=>state.pages[k]=1);$("#shopPickerValue").textContent=option.textContent;document.querySelectorAll("#shopOptions [data-shop]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");const page=$(".page.active").id;loadPage(page).catch(err=>toast(err.message,true))};
$("#orderFilterForm").addEventListener("submit",e=>{e.preventDefault();state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#orderList").onclick=e=>{const posting=e.target.dataset.addComplaint;if(!posting)return;openPage("returns");$("#complaintPosting").value=posting;$("#complaintShop").value=e.target.dataset.complaintShop;document.querySelector('[data-return-tab="complaints"]').click();$("#complaintNumber").focus()};
$("#orderSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#orderFilterForm").requestSubmit()}});
$("#channelFilter").addEventListener("change",()=>{state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#riskGrouped").addEventListener("change",()=>loadRisk().catch(err=>toast(err.message,true)));
$("#returnTabs").onclick=e=>{const tab=e.target.closest("[data-return-tab]")?.dataset.returnTab;if(!tab)return;document.querySelectorAll("[data-return-tab]").forEach(button=>button.classList.toggle("active",button.dataset.returnTab===tab));document.querySelectorAll(".return-tab").forEach(panel=>panel.classList.toggle("active",panel.id===`returns-${tab}`))};
$("#complaintSearch").onsubmit=e=>{e.preventDefault();state.pages.complaints=1;loadComplaints().catch(err=>toast(err.message,true))};
$("#complaintRows").onclick=e=>{const key=e.target.dataset.editComplaint;if(!key)return;const [shop,...number]=key.split(":"),r=state.complaints.find(x=>x.shop_id===Number(shop)&&x.complaint_number===number.join(":"));if(!r)return;$("#complaintShop").value=r.shop_id;$("#complaintPosting").value=r.posting_number;$("#complaintNumber").value=r.complaint_number;$("#complaintAt").value=new Date(r.complaint_at).toISOString().slice(0,16);$("#complaintChannel").value=r.channel;$("#complaintResolved").value=r.resolved==null?"":String(Boolean(r.resolved));$("#complaintReturned").value=r.package_returned==null?"":String(Boolean(r.package_returned));$("#complaintAmount").value=r.compensation_amount??"";$("#complaintCurrency").value=r.compensation_currency??"";$("#complaintNotes").value=r.notes??"";$("#complaintForm").scrollIntoView({behavior:"smooth"})};
$("#reasonRows").onclick=async e=>{const reason=e.target.dataset.reason;if(!reason)return;const data=await api(`/api/risk/reasons?shop_id=${state.shop}&reason=${encodeURIComponent(reason)}`);$("#reasonDetails").textContent=data.details.map(r=>`${r.shop_name} / ${r.channel} / ${r.posting_number}（${r.pieces}件）`).join("；")};
$("#prevPage").onclick=()=>{state.page--;loadOrders()}; $("#nextPage").onclick=()=>{state.page++;loadOrders()};
$("#shopForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:$("#shop1").value,2:$("#shop2").value})});await loadShops();toast("店铺名称已更新")}catch(err){toast(err.message,true)}});
$("#probeShops").onclick=async e=>{const button=e.target.closest("[data-probe]");if(!button)return;const id=button.dataset.probe,target=$("#probeResult"+id);button.disabled=true;target.innerHTML='<span class="probe-state">正在检测</span><p>正在验证凭据与权限，请稍候。</p>';try{target.innerHTML=probeResult(await api(`/api/ozon/probe/${id}`,{method:"POST"}))}catch(error){target.innerHTML=probeResult({valid:false,error:error.message})}finally{button.disabled=false}};
$("#dingtalkForm").addEventListener("submit",async e=>{e.preventDefault();try{const weekdays=[...document.querySelectorAll("#dingWeekdays input:checked")].map(input=>Number(input.value));await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({daily_enabled:$("#dingEnabled").checked,push_time:$("#dingTime").value,weekdays})});toast("钉钉设置已保存");await loadDingtalk()}catch(err){toast(err.message,true)}});
$("#dingTestButton").onclick=async e=>{e.target.disabled=true;try{await api("/api/dingtalk/test",{method:"POST"});toast("测试消息已发送")}catch(err){toast(err.message,true)}finally{e.target.disabled=false}};
$("#importForm").addEventListener("submit",async e=>{e.preventDefault();const file=$("#importFile").files[0],shop=$("#importShop").value,kind=$("#importKind").value;if(!file||!shop)return;try{const result=await api(`/api/import/${kind}?shop_id=${shop}`,{method:"POST",headers:{"X-Filename":encodeURIComponent(file.name)},body:file});toast(`已导入 ${result.rows} 行`);await loadImports()}catch(err){toast(err.message,true)}});
const exportNames={orders:"订单",risk:"SKU风险及原因",timeliness:"发货配送时效",returns:"退货",complaints:"投诉",stock:"库存",rules:"商品规则"};
$("#exportButtons").innerHTML=Object.entries(exportNames).map(([key,name])=>`<button data-export="${key}">${name} JSONL</button>`).join("");
$("#exportButtons").onclick=e=>{if(e.target.dataset.export)location.href=`/api/export/${e.target.dataset.export}?shop_id=${state.shop}`};
$("#complaintForm").onsubmit=async e=>{e.preventDefault();const tri=id=>$(id).value===""?null:$(id).value==="true";await api("/api/complaints",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:Number($("#complaintShop").value),posting_number:$("#complaintPosting").value,complaint_number:$("#complaintNumber").value,complaint_at:new Date($("#complaintAt").value).toISOString(),channel:$("#complaintChannel").value,resolved:tri("#complaintResolved"),package_returned:tri("#complaintReturned"),compensation_amount:$("#complaintAmount").value||null,compensation_currency:$("#complaintCurrency").value,notes:$("#complaintNotes").value})});toast("投诉已保存");await loadComplaints()};
$("#shortNameForm").onsubmit=async e=>{e.preventDefault();await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"short_name",key_type:$("#shortKeyType").value,key_value:$("#shortKeyValue").value,short_name:$("#shortName").value})});toast("短名称已保存");await loadRules()};
$("#brandForm").onsubmit=async e=>{e.preventDefault();await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"brand",brand_name:$("#brandName").value,keyword:$("#brandKeyword").value,priority:Number($("#brandPriority").value),enabled:$("#brandEnabled").checked})});toast("品牌规则已保存");await loadRules()};
$("#groupForm").onsubmit=async e=>{e.preventDefault();const members=$("#groupMembers").value.split(/\n+/).filter(Boolean).map(line=>{const [key_type,...rest]=line.split(":");return {key_type,key_value:rest.join(":").trim()}});await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"group",name:$("#groupName").value,members})});toast("合并组已保存");await loadRules()};
$("#ruleLists").onclick=async e=>{const keyType=e.target.dataset.ungroupType;if(!keyType)return;await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"ungroup",key_type:keyType,key_value:e.target.dataset.ungroupValue})});toast("已解除合并");await loadRules()};
$("#syncButtons").innerHTML=Object.entries(syncNames).map(([key,name])=>`<button data-module="${key}">${name}拉取</button>`).join("");
$("#sync > .panel:first-child").insertAdjacentHTML("afterend",`<form id="autoSyncForm" class="panel"><div class="panel-title"><h2>自动同步设置</h2><span class="muted">三个模块独立设置</span></div><p class="muted">到达设定时间后，每天分别为两个店铺创建任务；日期型数据继续按自然月分段。</p><div id="autoSyncCards" class="auto-sync-grid"></div><button class="primary">保存自动同步设置</button></form>`);
$("#autoSyncForm").addEventListener("submit",async e=>{e.preventDefault();const values=Object.fromEntries([1,2].map(shop=>[String(shop),Object.fromEntries(Object.keys(syncNames).map(module=>[module,{enabled:$("#autoEnabled-"+shop+"-"+module).checked,run_time:$("#autoTime-"+shop+"-"+module).value,range_days:Number($("#autoRange-"+shop+"-"+module).value)}]))]));try{await api("/api/auto-sync-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(values)});toast("两店铺自动同步设置已保存");await loadAutoSync()}catch(err){toast(err.message,true)}});
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
document.addEventListener("click",e=>{if(!e.target.closest(".date-range-wrap")){$("#dateRangePanel").classList.add("hidden");$("#dateRangeButton").setAttribute("aria-expanded","false")}if(!e.target.closest(".shop-label")){$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false")}});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){$("#dateRangePanel").classList.add("hidden");$("#dateRangeButton").setAttribute("aria-expanded","false");$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false")}});
choosePreset("3months");
$("#sync > .panel:first-child > .muted").textContent="每个按钮只调用本模块；长时段按自然月串行拉取，某月失败即停止。库存仅拉取一次当前快照。";
async function waitForSync(runId,module){for(;;){const task=await api(`/api/sync/${runId}`);await loadSync();if(task.status!=="running"){if(task.status==="success")toast(`${syncNames[module]}拉取完成：${num(task.records,0)} 条`);else toast(task.error||"拉取失败",true);return}await new Promise(resolve=>setTimeout(resolve,1000))}}
$("#syncButtons").onclick=async e=>{const module=e.target.dataset.module;if(!module)return;if(!state.shop)return toast("请先在左上角选择一个店铺",true);if(rangeState.preset==="all"&&!confirm("整个时段将按自然月逐段拉取，耗时可能较长。确认开始？"))return;e.target.disabled=true;try{const task=await api(`/api/sync/${module}?shop_id=${state.shop}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:$("#syncFrom").value,to:$("#syncTo").value})});await loadSync();await waitForSync(task.run_id,module)}catch(err){toast(err.message,true);await loadSync()}finally{e.target.disabled=false}};
const systemTheme=window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(){const follow=localStorage.getItem("themeFollowSystem")==="true",dark=follow?systemTheme.matches:localStorage.getItem("theme")==="dark";document.documentElement.dataset.theme=dark?"dark":"";$("#themeFollowSystem").checked=follow;$("#themePreferenceText").textContent=follow?`已跟随系统 · 当前${dark?"深色":"浅色"}模式`:"关闭后可使用左下角按钮手动切换"}
$("#themeFollowSystem").onchange=e=>{if(!e.target.checked)localStorage.setItem("theme",document.documentElement.dataset.theme==="dark"?"dark":"light");localStorage.setItem("themeFollowSystem",String(e.target.checked));applyTheme()};
systemTheme.addEventListener("change",()=>{if(localStorage.getItem("themeFollowSystem")==="true")applyTheme()});
$("#themeButton").onclick=()=>{const dark=document.documentElement.dataset.theme!=="dark";localStorage.setItem("themeFollowSystem","false");localStorage.setItem("theme",dark?"dark":"light");applyTheme()};
$("#settingsButton").onclick=()=>openPage("settings");
applyTheme();

(async()=>{const s=await api("/api/session");if(!s.authenticated)return showLogin();state.csrf=s.csrf_token;showShell();await loadShops();await loadOverview()})().catch(e=>toast(e.message,true));
