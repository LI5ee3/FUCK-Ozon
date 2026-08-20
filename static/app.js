const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], pages: {timeliness:1,finance:1,returns:1,premium:1,stock:1,prices:1,questions:1}};
const titles = {overview:"总览",orders:"订单",risk:"SKU风险分析",timeliness:"发货与配送时效",finance:"财务利润",returns:"退货与投诉",premium:"Premium分析",stock:"库存",prices:"价格与佣金",questions:"买家问答",transfer:"数据导入/导出",sync:"独立同步中心",rules:"商品匹配规则",settings:"系统设置"};
const syncNames = {orders:"订单",finance:"财务",returns:"退货",premium:"Premium分析",stock:"库存",prices:"价格",questions:"买家问答"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => v ? new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(v)).replaceAll("/","-") : "暂无";
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const metric = (v, digits=2, suffix="") => v == null || v === "" ? "暂无" : `${num(v,digits)}${suffix}`;
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时`;
const cell = (v) => v == null || v === "" ? "暂无" : esc(v);

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
  $("#channelRows").innerHTML=data.channels.map(r=>`<tr><td><span class="tag">${r.channel}</span></td><td class="num">${r.orders}</td><td class="num">${r.pieces}</td><td class="risk-col">${r.cancelled_pieces||0}</td></tr>`).join("") || '<tr><td colspan="4" class="muted">暂无数据，请先导入。</td></tr>';
}
async function loadOrders() {
  const q=encodeURIComponent($("#orderSearch").value), channel=encodeURIComponent($("#channelFilter").value);
  const data=await api(`/api/orders?shop_id=${state.shop}&channel=${channel}&q=${q}&page=${state.page}`); state.total=data.total;
  $("#orderList").innerHTML=data.items.map(o=>`<article class="order-card"><div class="order-head"><div><strong>${esc(o.posting_number)}</strong> <span class="tag">${o.channel}</span></div><span>${esc(o.shop_name)}</span></div><div class="order-meta"><span>${bj(o.created_at)}</span><span>${esc(o.status_raw)}</span><span>${o.amount_original==null?'金额暂无':`${o.amount_original.toFixed(2)} ${esc(o.amount_currency)}`}</span></div>${o.items.map(i=>`<div class="product-row"><span title="${esc(i.product_name_raw)}">${esc(i.product_name_raw)} · SKU ${esc(i.sku)}</span><span>× ${i.quantity}</span></div>`).join("")}<div class="muted">${o.cost_cny==null?'成本暂无':`订单总成本 ¥${o.cost_cny.toFixed(4)}${o.items.length>1?'；SKU成本暂无':''}`}</div>${o.cancel_reason_raw?`<div class="exception">${esc(o.cancel_reason_raw)}</div>`:""}${o.data_anomaly?'<div class="exception">数据异常</div>':""}</article>`).join("") || '<div class="panel muted">没有匹配订单。</div>';
  const pages=Math.max(1,Math.ceil(data.total/data.size)); $("#pageInfo").textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 个订单`;
  $("#prevPage").disabled=state.page<=1; $("#nextPage").disabled=state.page>=pages;
}
async function loadRisk() {
  const rows=await api(`/api/risk?shop_id=${state.shop}`);
  $("#riskRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)} / <span class="tag">${r.channel}</span></td><td title="${esc(r.product_name)}">${esc(r.sku)}</td><td class="num">${r.valid_pieces}</td><td class="risk-col">${pct(r.cancelled_rate)}</td><td class="risk-col">${pct(r.unclaimed_rate)}</td><td class="risk-col">${pct(r.customs_rate)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">暂无数据。</td></tr>';
}
async function loadTimeliness() {
  const data=await api(`/api/timeliness?shop_id=${state.shop}&page=${state.pages.timeliness}`), s=data.summary;
  summary("timeliness",[["有效订单",num(s.orders,0)],["已有发货时间",num(s.shipped_orders,0)],["平均发货耗时",hours(s.avg_ship_hours)],["平均配送耗时",hours(s.avg_delivery_hours)]]);
  $("#timelinessRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)} / <span class="tag">${esc(r.channel)}</span></td><td>${esc(r.posting_number)}</td><td>${bj(r.created_at)}</td><td>${bj(r.shipped_at)}</td><td>${bj(r.delivered_at)}</td><td class="num">${hours(r.ship_hours)}</td><td class="num">${hours(r.delivery_hours)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
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
  summary("returns",[["退货记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.quantity,0)} 件`,`共 ${num(s.records,0)} 条记录`])]);
  $("#returnsRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.occurred_at)}</td><td>${cell(r.posting_number)}</td><td><span class="cell-text" title="${esc(r.product_name)}">${cell(r.sku)} / ${cell(r.product_name)}</span></td><td class="num">${num(r.quantity,0)}</td><td><span class="cell-text" title="${esc(r.reason)}">${cell(r.reason)}</span></td><td>${cell(r.status||r.type)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("returns",data,loadReturns);
}
async function loadPremium() {
  const data=await api(`/api/premium?shop_id=${state.shop}&page=${state.pages.premium}`);
  summary("premium",[["日 / SKU 记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.revenue)} 收入`,`API 原始值 · 下单 ${num(s.ordered_units,0)} · 送达 ${num(s.delivered_units,0)} · 退货 ${num(s.returns,0)} · 取消 ${num(s.cancellations,0)}`])]);
  $("#premiumRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${cell(r.day)}</td><td><span class="cell-text" title="${esc(r.product_name)}">${cell(r.sku)} / ${cell(r.product_name)}</span></td><td class="num">${metric(r.revenue)}</td><td class="num">${metric(r.ordered_units,0)}</td><td class="num">${metric(r.delivered_units,0)}</td><td class="num">${metric(r.returns,0)}</td><td class="num">${metric(r.cancellations,0)}</td></tr>`).join("") || '<tr><td colspan="8" class="muted">暂无数据。</td></tr>';
  pager("premium",data,loadPremium);
}
async function loadStock() {
  const data=await api(`/api/stock?shop_id=${state.shop}&page=${state.pages.stock}`);
  summary("stock",[["最新商品",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.present,0)} 可用`,`商品 ${num(s.products,0)} · 预留 ${num(s.reserved,0)}`])]);
  $("#stockRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${cell(r.offer_id)}</td><td>${cell(r.product_id)}</td><td>${cell(r.types)}</td><td class="num">${num(r.present,0)}</td><td class="num">${num(r.reserved,0)}</td><td>${bj(r.observed_at)}</td></tr>`).join("") || '<tr><td colspan="7" class="muted">暂无数据。</td></tr>';
  pager("stock",data,loadStock);
}
async function loadPrices() {
  const data=await api(`/api/prices?shop_id=${state.shop}&page=${state.pages.prices}`);
  summary("prices",[["最新商品",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.products,0)} 个商品`,`参加活动 ${num(s.in_action,0)}`])]);
  $("#pricesRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${cell(r.offer_id)}</td><td>${cell(r.product_id)}</td><td class="num">${metric(r.price)} ${cell(r.currency)}</td><td class="num">${metric(r.marketing_price)} ${cell(r.currency)}</td><td class="num">${metric(r.net_price)} ${cell(r.currency)}</td><td class="num">${metric(r.min_price)} ${cell(r.currency)}</td><td class="num">${metric(r.sales_percent_fbo,2,"%")}</td><td class="num">${metric(r.sales_percent_fbs,2,"%")}</td><td>${r.in_action?'是':'否'}</td></tr>`).join("") || '<tr><td colspan="10" class="muted">暂无数据。</td></tr>';
  pager("prices",data,loadPrices);
}
async function loadQuestions() {
  const data=await api(`/api/questions?shop_id=${state.shop}&page=${state.pages.questions}`);
  summary("questions",[["问题记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.answered,0)} 已回答`,`共 ${num(s.records,0)} 个问题`])]);
  $("#questionsRows").innerHTML=data.items.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${bj(r.published_at)}</td><td>${cell(r.sku)}</td><td>${cell(r.status)}</td><td><span class="cell-text" title="${esc(r.text)}">${cell(r.text)}</span></td><td class="num">${metric(r.answers_count,0)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">暂无数据。</td></tr>';
  pager("questions",data,loadQuestions);
}
async function loadImports() {
  const rows=await api("/api/imports");
  $("#importRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${esc(r.kind)}</td><td>${esc(r.filename)}</td><td class="num">${r.row_count}</td><td>${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">暂无导入记录。</td></tr>';
}
async function loadSync() {
  const rows=await api("/api/sync");
  $("#syncRows").innerHTML=rows.map(r=>`<tr><td>${esc(r.shop_name)}</td><td>${esc(syncNames[r.module]||r.module)}</td><td>${r.status==='failed'?'失败':r.status==='success'?'成功':'进行中'}</td><td>${bj(r.started_at)}</td><td class="error">${esc(r.error||'')}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">暂无拉取记录。</td></tr>';
}
async function loadPage(page) {
  if(page==="overview") return loadOverview(); if(page==="orders") return loadOrders();
  if(page==="risk") return loadRisk();
  const loaders={timeliness:loadTimeliness,finance:loadFinance,returns:loadReturns,premium:loadPremium,stock:loadStock,prices:loadPrices,questions:loadQuestions};
  if(loaders[page]) return loaders[page](); if(page==="transfer") return loadImports(); if(page==="sync") return loadSync();
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
$("#prevPage").onclick=()=>{state.page--;loadOrders()}; $("#nextPage").onclick=()=>{state.page++;loadOrders()};
$("#shopForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:$("#shop1").value,2:$("#shop2").value})});await loadShops();toast("店铺名称已更新")}catch(err){toast(err.message,true)}});
$("#importForm").addEventListener("submit",async e=>{e.preventDefault();const file=$("#importFile").files[0],shop=$("#importShop").value,kind=$("#importKind").value;if(!file||!shop)return;try{const result=await api(`/api/import/${kind}?shop_id=${shop}`,{method:"POST",headers:{"X-Filename":encodeURIComponent(file.name)},body:file});toast(`已导入 ${result.rows} 行`);await loadImports()}catch(err){toast(err.message,true)}});
$("#exportOrders").onclick=()=>{location.href=`/api/export/orders?shop_id=${state.shop}`};
$("#syncButtons").innerHTML=Object.entries(syncNames).map(([key,name])=>`<button data-module="${key}">${name}拉取</button>`).join("");
const today=new Date(),threeMonthsAgo=new Date(today);threeMonthsAgo.setMonth(today.getMonth()-3);$("#syncFrom").value=threeMonthsAgo.toISOString().slice(0,10);$("#syncTo").value=today.toISOString().slice(0,10);
$("#syncButtons").onclick=async e=>{const module=e.target.dataset.module;if(!module)return;if(!state.shop)return toast("请先在左上角选择一个店铺",true);e.target.disabled=true;try{const result=await api(`/api/sync/${module}?shop_id=${state.shop}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:$("#syncFrom").value,to:$("#syncTo").value})});toast(`${syncNames[module]}拉取完成：${result.records} 条`);loadSync()}catch(err){toast(err.message,true);loadSync()}finally{e.target.disabled=false}};
$("#themeButton").onclick=()=>{const dark=document.documentElement.dataset.theme!=="dark";document.documentElement.dataset.theme=dark?"dark":"";localStorage.setItem("theme",dark?"dark":"light")};
$("#logoutButton").onclick=async()=>{await api("/api/logout",{method:"POST"});showLogin()};
if(localStorage.getItem("theme")==="dark")document.documentElement.dataset.theme="dark";

(async()=>{const s=await api("/api/session");if(!s.authenticated)return showLogin();showShell();await loadShops();await loadOverview()})().catch(e=>toast(e.message,true));
