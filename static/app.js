const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: []};
const titles = {overview:"总览",orders:"订单",risk:"SKU风险分析",timeliness:"发货与配送时效",finance:"财务利润",returns:"退货与投诉",premium:"Premium分析",stock:"库存",prices:"价格与佣金",questions:"买家问答",transfer:"数据导入/导出",sync:"独立同步中心",rules:"商品匹配规则",settings:"系统设置"};
const syncNames = {orders:"订单",finance:"财务",returns:"退货",premium:"Premium分析",stock:"库存",prices:"价格",questions:"买家问答"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => v ? new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(v)).replaceAll("/","-") : "暂无";

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
  if(page==="risk") return loadRisk(); if(page==="transfer") return loadImports(); if(page==="sync") return loadSync();
}
function openPage(page) {
  document.querySelectorAll(".page").forEach(e=>e.classList.toggle("active",e.id===page));
  document.querySelectorAll("#nav button").forEach(e=>e.classList.toggle("active",e.dataset.page===page));
  $("#pageTitle").textContent=titles[page]; loadPage(page).catch(e=>toast(e.message,true));
}

$("#loginForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});showShell();await loadShops();await loadOverview()}catch(err){$("#loginError").textContent=err.message}});
$("#nav").addEventListener("click",e=>{if(e.target.dataset.page)openPage(e.target.dataset.page)});
$("#shopSelect").addEventListener("change",e=>{state.shop=Number(e.target.value);state.page=1;const page=$(".page.active").id;loadPage(page).catch(err=>toast(err.message,true))});
$("#searchButton").onclick=()=>{state.page=1;loadOrders().catch(e=>toast(e.message,true))};
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
