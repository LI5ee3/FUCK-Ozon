const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], complaints:[], csrf:"", overviewGranularity:"week", stockSort:{key:"",order:"desc"}, pages: {timeliness:1,returns:1,rfbsReturns:1,complaints:1,stock:1}};
let riskItems=[];
let dingSavedTemplate="", dingDefaultTemplate="";
const titles = {overview:"总览",orders:"订单",risk:"SKU风险分析",timeliness:"发货与配送时效",returns:"退货与投诉",stock:"库存",transfer:"数据导入/导出",sync:"独立同步中心",rules:"商品匹配规则",dingtalk:"钉钉机器人",settings:"系统设置"};
const syncNames = {orders:"订单",returns:"退货",stock:"库存"};
const syncDescriptions = {orders:"拉取订单、商品和订单状态数据",returns:"拉取退货与售后申请数据",stock:"只拉取实时库存数据，不受日期范围影响"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => { if (!v) return "暂无"; const date=new Date(v); return Number.isNaN(date.getTime()) ? "暂无" : new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(date).replaceAll("/","-"); };
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const metric = (v, digits=2, suffix="") => v == null || v === "" ? "暂无" : `${num(v,digits)}${suffix}`;
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时 / ${num(v/24,1)} 天`;
const money = (amount,currency) => amount==null ? "金额暂无" : `${num(amount)} ${esc(currency||"")}`;
const cell = (v) => v == null || v === "" ? "暂无" : esc(v);
const channelTag = (v) => `<span class="tag channel-${({FBP:"fbp",realFBS:"fbs",WHD:"whd"}[v] || "")}">${esc(v)}</span>`;
const triText = v => v == null ? "未填写" : v ? "是" : "否";
const returnSelects = {};
function createReturnSelect(id){
  const select=$(`#${id}`),root=select.closest("[data-return-select],[data-import-select]"),button=root.querySelector("[data-select-button]"),label=root.querySelector("[data-select-label]"),options=root.querySelector("[data-select-options]");
  options.id=`${id}Options`;button.setAttribute("aria-controls",options.id);
  const close=()=>{options.classList.add("hidden");button.setAttribute("aria-expanded","false")};
  const render=()=>{const selected=select.options[select.selectedIndex];label.textContent=selected?.textContent||"请选择";options.innerHTML=[...select.options].map(option=>`<button type="button" role="option" tabindex="-1" data-select-value="${esc(option.value)}" aria-selected="${option.selected}">${esc(option.textContent)}</button>`).join("")};
  const set=value=>{select.value=value==null?"":String(value);render()};
  const open=()=>{options.classList.remove("hidden");button.setAttribute("aria-expanded","true")};
  button.onclick=()=>{options.classList.contains("hidden")?open():close()};
  select.oninvalid=e=>{e.preventDefault();button.classList.add("is-invalid");button.focus()};
  select.onchange=()=>button.classList.remove("is-invalid");
  options.onclick=e=>{const option=e.target.closest("[data-select-value]");if(!option)return;set(option.dataset.selectValue);select.dispatchEvent(new Event("change",{bubbles:true}));close();button.focus()};
  root.onkeydown=e=>{const choices=[...options.querySelectorAll("[role=option]")],current=choices.indexOf(document.activeElement);if(e.key==="Escape"){close();button.focus();return}if(e.key==="Enter"&&current>=0){e.preventDefault();document.activeElement.click();return}if(!["ArrowDown","ArrowUp"].includes(e.key))return;e.preventDefault();open();const selected=Math.max(0,choices.findIndex(option=>option.getAttribute("aria-selected")==="true")),next=current<0?selected:(current+(e.key==="ArrowDown"?1:-1)+choices.length)%choices.length;choices[next]?.focus()};
  render();return {root,close,render,set};
}
const setReturnSelect=(id,value)=>returnSelects[id]?.set(value);
const gmvText = (gmv) => gmv.missing_rate_orders
  ? `可折算GMV：¥${num(gmv.amount)}｜缺少汇率：${num(gmv.missing_rate_orders,0)}单`
  : `GMV：${gmv.currency==="CNY"?"¥":gmv.currency==="USD"?"$":""}${num(gmv.amount)} ${gmv.currency}`;
function trendTip(bucket){return `<strong>${esc(bucket.from===bucket.to?bucket.from:`${bucket.from} 至 ${bucket.to}`)}</strong><span>总订单：${num(bucket.orders,0)}</span><span>${esc(gmvText(bucket.gmv))}</span>${["FBP","realFBS","WHD"].map(channel=>{const row=bucket.channels[channel];return `<span>${channel}：${num(row.orders,0)}单｜${esc(gmvText(row.gmv))}</span>`}).join("")}`}
function renderOrderTrend(data){
  const host=$("#orderTrend"),buckets=[...data.buckets].reverse(),width=Math.max(620,buckets.length*68+64),height=300,plotTop=18,plotBottom=242,plotHeight=plotBottom-plotTop,max=Math.max(1,...buckets.map(row=>row.orders)),barWidth=36;
  const ticks=[0,.25,.5,.75,1].map(part=>{const y=plotBottom-plotHeight*part,value=Math.ceil(max*part);return `<line x1="48" y1="${y}" x2="${width-12}" y2="${y}"/><text x="42" y="${y+4}" text-anchor="end">${value}</text>`}).join("");
  const bars=buckets.map((bucket,index)=>{const x=58+index*68;let y=plotBottom;const segments=["FBP","realFBS","WHD"].map(channel=>{const value=bucket.channels[channel].orders,h=plotHeight*value/max;y-=h;return h?`<rect class="trend-segment channel-${channel==="FBP"?"fbp":channel==="realFBS"?"fbs":"whd"}" x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="3" data-bucket="${index}" tabindex="0" role="img" aria-label="${esc(channel)} ${value}单"><title>${esc(channel)} ${value}单</title></rect>`:""}).join("");const label=data.granularity==="day"?bucket.from.slice(5):data.granularity==="month"?bucket.from.slice(0,7):bucket.from.slice(5);return `<g>${segments}<rect class="trend-hit" x="${x}" y="${plotTop}" width="${barWidth}" height="${plotHeight}" data-bucket="${index}" tabindex="0" role="img" aria-label="${esc(bucket.from)}至${esc(bucket.to)}，总订单${bucket.orders}单"/><text class="trend-x" x="${x+barWidth/2}" y="266" text-anchor="middle">${esc(label)}</text></g>`}).join("");
  host.style.width=`${width}px`;host.innerHTML=`<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="有效订单量趋势，纵轴从0开始"><g class="trend-grid">${ticks}</g>${bars}</svg><div class="trend-tooltip hidden" role="status"></div>`;
  const tooltip=host.querySelector(".trend-tooltip"),show=(target)=>{const index=Number(target.dataset.bucket),box=target.getBoundingClientRect(),stage=host.getBoundingClientRect();tooltip.innerHTML=trendTip(buckets[index]);tooltip.style.left=`${Math.min(Math.max(8,box.left-stage.left+box.width/2-130),width-272)}px`;tooltip.classList.remove("hidden")};
  host.onpointerover=e=>{const target=e.target.closest("[data-bucket]");if(target)show(target)};host.onpointerout=e=>{if(!e.relatedTarget?.closest?.("[data-bucket]"))tooltip.classList.add("hidden")};host.querySelectorAll("[data-bucket]").forEach(target=>{target.onfocus=()=>show(target);target.onblur=()=>tooltip.classList.add("hidden")});host.onclick=e=>{const target=e.target.closest("[data-bucket]");if(target){show(target);e.stopPropagation()}};
}
function renderOverviewPanels(data){
  const e=data.exceptions,alerts=[
    ["未完结投诉",e.unresolved_complaints,"当前状态","returns"],
    ["待处理退货申请",e.pending_returns,"当前状态","returns"],
    ["缺货 SKU",e.stockout_skus,"当前最新库存","stock"],
    ["7天内低库存 SKU",e.low_stock_skus,"当前最新库存","stock"],
    ["数据异常订单",e.anomaly_orders,"所选时间范围","orders"]];
  $("#overviewExceptions").innerHTML=alerts.map(row=>`<button type="button" data-overview-page="${row[3]}"><span>${esc(row[0])}</span><strong>${row[1]==null?"数据不足":num(row[1],0)}</strong><small>${esc(row[2])}</small></button>`).join("");
  $("#overviewTimeliness").innerHTML=data.timeliness.map(row=>{const ship=row.ship_sample_insufficient?"数据不足":hours(row.p50_ship_hours),delivery=row.delivery_sample_insufficient?"数据不足":hours(row.p50_delivery_hours),p90=row.delivery_sample_insufficient?"数据不足":hours(row.p90_delivery_hours);return `<div class="overview-timing-row"><div>${channelTag(row.channel)}</div><div><span>发货 P50</span><strong>${ship}</strong></div><div><span>配送 P50</span><strong>${delivery}</strong></div><div><span>配送 P90</span><strong>${p90}</strong></div></div>`}).join("");
  $("#overviewTopProducts").innerHTML=data.top_products.map((row,index)=>`<div class="overview-product-row"><span class="overview-rank">${index+1}</span><strong title="${esc(row.name)}">${esc(row.name)}</strong><span><b>${num(row.pieces,0)}</b> 件</span><span>${num(row.orders,0)} 单</span><span>取消率 ${pct(row.cancel_rate)}</span></div>`).join("")||'<div class="overview-empty">所选范围暂无商品数据</div>';
}

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
  const complaintShop = $("#complaintShop").value,importShop=$("#importShop").value;
  const shops=[{id:0,name:"两店铺合并"},...state.shops];
  $("#shopOptions").innerHTML=shops.map(s=>`<button type="button" role="option" data-shop="${s.id}" aria-selected="${s.id===state.shop}">${esc(s.name)}</button>`).join("");
  $("#shopPickerValue").textContent=shops.find(s=>s.id===state.shop)?.name||"两店铺合并";
  $("#importShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#importShop").value = importShop;
  $("#complaintShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#complaintShop").value = complaintShop;
  returnSelects.importShop?.render();
  returnSelects.complaintShop?.render();
  $("#shop1").value = state.shops[0].name; $("#shop2").value = state.shops[1].name;
}
async function loadOverview() {
  const query=new URLSearchParams({shop_id:state.shop,from:overviewRange.start,to:overviewRange.end,granularity:state.overviewGranularity});
  const data = await api(`/api/summary?${query}`), t=data.totals;
  $("#totalOrders").textContent=t.orders; $("#totalPieces").textContent=t.pieces;
  $("#cancelOrders").textContent=t.cancelled_orders; $("#cancelRate").textContent=pct(t.cancel_rate);
  $("#dataThrough").textContent=`数据截止：${bj(data.data_through)}`;
  $("#channelRows").innerHTML=data.channels.map(r=>`<tr><td>${channelTag(r.channel)}</td><td class="num">${r.orders}</td><td class="num">${r.pieces}</td><td class="risk-col">${r.cancelled_pieces||0}</td></tr>`).join("") || '<tr><td colspan="4" class="muted">暂无数据，请先导入。</td></tr>';
  renderOrderTrend(data);
  renderOverviewPanels(data);
}
async function loadOrders() {
  $("#orderList").innerHTML='<div class="panel order-empty">订单加载中…</div>';
  const query=new URLSearchParams({shop_id:state.shop,channel:$("#channelFilter").value,q:$("#orderSearch").value,page:state.page,from:orderRange.start,to:orderRange.end});
  try {
    const data=await api(`/api/orders?${query}`);state.total=data.total;
    $("#orderList").innerHTML=data.items.map(o=>{const first=o.items[0],extra=o.sku_types-1,cancelTag=o.status_raw==="已取消"?`<span class="order-flag danger">${o.shipped?"发货后取消":"发货前取消"}</span>`:"",anomaly=o.data_anomaly?'<span class="order-flag danger">数据异常</span>':"",tone=o.status_raw==="已取消"||o.data_anomaly?"danger":o.status_raw==="已签收"?"delivered":/运输|配送|发货|待取件/.test(o.status_raw)?"shipping":"pending",product=first?`<strong title="${esc(first.product_name_raw)}">${esc(first.product_name_raw)}</strong><small>SKU ${cell(first.sku)} · 货号 ${cell(first.offer_id)} · × ${num(first.quantity,0)}${extra?` · 另有${extra}种商品`:""}</small>`:'<strong>商品信息暂无</strong>';
      return `<details class="order-card order-${tone}"><summary aria-label="订单 ${esc(o.posting_number)}，${esc(o.status_raw)}，点击展开详情"><div class="order-identity"><strong>${esc(o.posting_number)}</strong><span>${esc(o.shop_name)} ${channelTag(o.channel)}</span><span class="order-flags">${cancelTag}${anomaly}</span></div><div class="order-product-summary">${product}${o.cancel_reason_raw?`<span class="order-cancel-reason" title="${esc(o.cancel_reason_raw)}">${esc(o.cancel_reason_raw)}</span>`:""}</div><div class="order-status"><span class="order-status-badge">${esc(o.status_raw)}</span><small>${bj(o.created_at)}</small><small>${num(o.sku_types,0)} 种 SKU · ${num(o.pieces,0)} 件</small></div><div class="order-amount"><strong>${money(o.amount_original,o.amount_currency)}</strong><small>展开查看详情</small></div></summary><div class="order-details"><div class="order-time-grid"><div><span>创建时间</span><strong>${bj(o.created_at)}</strong></div><div><span>实际发货时间</span><strong>${bj(o.shipped_at)}</strong></div><div><span>实际签收时间</span><strong>${bj(o.delivered_at)}</strong></div></div><div class="order-detail-products">${o.items.map(i=>`<div class="order-detail-product"><div><strong>${esc(i.product_name_raw)}</strong>${i.product_name_raw!==i.product_name_original?`<small>原始名称：${esc(i.product_name_original)}</small>`:""}</div><span>SKU ${cell(i.sku)}</span><span>货号 ${cell(i.offer_id)}</span><span>× ${num(i.quantity,0)}</span><span>${i.unit_price==null?"单价暂无":`${num(i.unit_price)} ${esc(i.price_currency||"")}`}</span></div>`).join("")||'<div class="muted">商品明细暂无</div>'}</div><div class="order-detail-foot"><div><strong>共 ${num(o.pieces,0)} 件</strong><span>${money(o.amount_original,o.amount_currency)}</span></div>${o.cancel_reason_raw?`<p class="exception"><strong>取消原因：</strong>${esc(o.cancel_reason_raw)}</p>`:""}${o.data_anomaly?'<p class="exception"><strong>数据异常：</strong>订单实际时效字段与状态不一致，请核对原始数据。</p>':""}<button type="button" data-add-complaint="${esc(o.posting_number)}" data-complaint-shop="${o.shop_id}">新增投诉</button></div></div></details>`}).join("")||'<div class="panel order-empty">当前筛选范围内没有订单。</div>';
    const pages=Math.max(1,Math.ceil(data.total/data.size)); $("#pageInfo").textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 个订单`;
    $("#prevPage").disabled=state.page<=1; $("#nextPage").disabled=state.page>=pages;
  } catch(error) { $("#orderList").innerHTML=`<div class="panel order-empty error">${esc(error.message)}</div>`; throw error; }
}
async function loadRisk() {
  const query=new URLSearchParams({shop_id:state.shop,grouped:$("#riskGrouped").checked,from:riskRange.start,to:riskRange.end});
  $("#riskRows").innerHTML='<tr><td colspan="5" class="risk-empty">风险数据加载中…</td></tr>';$("#reasonRows").innerHTML='<tr><td colspan="5" class="risk-empty">取消原因加载中…</td></tr>';$("#reasonDetails").classList.add("hidden");
  try {
    const [data,reasons]=await Promise.all([api(`/api/risk?${query}`),api(`/api/risk/reasons?${query}`)]),s=data.summary;
    const riskValue=(count,rate)=>s.valid?`${num(count,0)} 件 · ${pct(rate)}`:"数据不足";
    $("#riskSummary").innerHTML=[["有效货件数",num(s.valid,0),"当前筛选范围"],["发货后取消",riskValue(s.cancelled,s.cancelled_rate),"取消货件 / 有效货件"],["买家未取货",riskValue(s.unclaimed,s.unclaimed_rate),"五种平台固定原因"],["通关失败",riskValue(s.customs,s.customs_rate),"指定平台固定原因"]].map(([label,value,note])=>`<article><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`).join("");
    riskItems=data.items;renderRiskItems();
    $("#reasonRows").innerHTML=reasons.items.map(r=>`<tr><td class="risk-reason"><button class="link-button" data-reason="${esc(r.reason_raw)}" title="${esc(r.reason_raw)}">${esc(r.reason_name)}</button><span>${esc(r.reason_raw)}</span></td>${reasonStatCell("综合",r.total)}${reasonStatCell("FBP",r.channels.FBP)}${reasonStatCell("realFBS",r.channels.realFBS)}${reasonStatCell("WHD",r.channels.WHD)}</tr>`).join("")||'<tr><td colspan="5" class="risk-empty">当前范围内暂无发货后取消原因。</td></tr>';
  } catch(error) {$("#riskSummary").innerHTML="";$("#riskRows").innerHTML=`<tr><td colspan="5" class="risk-empty error">${esc(error.message)}</td></tr>`;$("#reasonRows").innerHTML=`<tr><td colspan="5" class="risk-empty error">${esc(error.message)}</td></tr>`;throw error}
}
function renderRiskItems(){const keyword=$("#riskSearch").value.trim().toLocaleLowerCase(),items=keyword?riskItems.filter(r=>`${r.search_text||""} ${r.product_name||""} ${r.group_name||""}`.toLocaleLowerCase().includes(keyword)):riskItems;$("#riskRows").innerHTML=items.map(r=>`<tr><td class="risk-product"><strong title="${esc(r.product_name)}">${esc(r.product_name||"商品名称暂无")}</strong><span>${esc(r.shop_name)}</span>${r.group_name?`<span>${esc(r.group_name)} · ${num(r.member_count,0)} 个成员 SKU</span>`:`<span>SKU ${cell(r.sku)}</span>`}</td>${riskStatCell("综合",r.total)}${riskStatCell("FBP",r.channels.FBP)}${riskStatCell("realFBS",r.channels.realFBS)}${riskStatCell("WHD",r.channels.WHD)}</tr>`).join("")||`<tr><td colspan="5" class="risk-empty">${keyword?"没有匹配的SKU、货号或商品。":"当前范围内暂无有效货件。"}</td></tr>`}
function riskStatCell(label,s){return `<td class="risk-stat" data-label="${label}"><strong class="risk-cell-title">${label}</strong>${!s||!s.valid?'<span class="risk-no-sample">无有效样本</span>':`<span>有效货件 <b>${num(s.valid,0)}</b></span><span>取消率 <b>${pct(s.cancelled_rate)}</b>（${num(s.cancelled,0)}/${num(s.valid,0)}件）</span><span>买家未取货率 <b>${pct(s.unclaimed_rate)}</b>（${num(s.unclaimed,0)}/${num(s.valid,0)}件）</span><span>通关失败率 <b>${pct(s.customs_rate)}</b>（${num(s.customs,0)}/${num(s.valid,0)}件）</span>`}</td>`}
function reasonStatCell(label,s){return `<td class="reason-stat" data-label="${label}"><strong class="risk-cell-title">${label}</strong>${s.orders||s.pieces?`<span>${num(s.orders,0)} 个订单</span><span>${num(s.pieces,0)} 件</span>`:'<span class="risk-no-sample">无记录</span>'}</td>`}
async function loadTimeliness() {
  const query=new URLSearchParams({shop_id:state.shop,page:state.pages.timeliness,q:$("#timelinessSearch").value,from:timelinessRange.start,to:timelinessRange.end});
  $("#timelinessGroupRows").innerHTML='<tr><td colspan="4" class="timeliness-empty">时效统计加载中…</td></tr>';$("#timelinessRows").innerHTML='<tr><td colspan="5" class="timeliness-empty">订单明细加载中…</td></tr>';
  try {
    const data=await api(`/api/timeliness?${query}`),s=data.summary;
    $("#timelinessSummary").innerHTML=[["有效订单数",num(s.orders,0),"当前店铺与时间范围"],["发货有效样本数",num(s.ship_samples,0),"仅真实且有效的实际时间"],["发货时效 P50",s.ship_samples?hours(s.p50_ship_hours):"数据不足","中位数"],["配送时效 P50",s.delivery_samples?hours(s.p50_delivery_hours):"数据不足","中位数"]].map(([label,value,note])=>`<article><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`).join("");
    $("#timelinessGroupRows").innerHTML=data.groups.map(r=>`<tr><td class="timeliness-identity" data-label="店铺／渠道"><strong>${esc(r.shop_name)}</strong>${channelTag(r.channel)}</td><td class="timeliness-completeness" data-label="订单与完整率"><span>有效订单 <b>${num(r.orders,0)}</b></span><span>创建完整率 <b>${pct(r.created_completeness)}</b></span><span>发货完整率 <b>${pct(r.shipped_completeness)}</b></span><span>签收完整率 <b>${pct(r.delivered_completeness)}</b></span></td>${timelinessStatCell("发货时效",r.ship_samples,r.ship_sample_insufficient,r.p50_ship_hours,r.avg_ship_hours,r.p90_ship_hours)}${timelinessStatCell("配送时效",r.delivery_samples,r.delivery_sample_insufficient,r.p50_delivery_hours,r.avg_delivery_hours,r.p90_delivery_hours)}</tr>`).join("")||'<tr><td colspan="4" class="timeliness-empty">当前范围内暂无有效订单。</td></tr>';
    $("#timelinessRows").innerHTML=data.items.map(r=>`<tr><td data-label="店铺／渠道"><strong>${esc(r.shop_name)}</strong>${channelTag(r.channel)}</td><td data-label="订单号"><strong>${esc(r.posting_number)}</strong></td><td data-label="创建时间">${bj(r.created_at)}</td>${timelinessDetailCell("发货时间／发货耗时",r.shipped_at,r.ship_hours,r.ship_anomaly)}${timelinessDetailCell("签收时间／配送耗时",r.delivered_at,r.delivery_hours,r.delivery_anomaly)}</tr>`).join("")||'<tr><td colspan="5" class="timeliness-empty">没有匹配的订单时效明细。</td></tr>';
    pager("timeliness",data,loadTimeliness);
  } catch(error){$("#timelinessSummary").innerHTML="";$("#timelinessGroupRows").innerHTML=`<tr><td colspan="4" class="timeliness-empty error">${esc(error.message)}</td></tr>`;$("#timelinessRows").innerHTML=`<tr><td colspan="5" class="timeliness-empty error">${esc(error.message)}</td></tr>`;throw error}
}
function timelinessStatCell(label,samples,insufficient,p50,average,p90){return `<td class="timeliness-stat" data-label="${label}"><strong class="timeliness-cell-title">${label}</strong>${samples?`<strong class="timeliness-p50">P50 ${hours(p50)}</strong><span>平均 ${hours(average)}</span><span class="timeliness-p90">P90 ${hours(p90)}</span><small>有效样本 ${num(samples,0)} 单${insufficient?' · <b>样本不足</b>':''}</small>`:'<span class="timeliness-no-data">数据不足</span>'}</td>`}
function timelinessDetailCell(label,value,duration,anomaly){return `<td class="timeliness-detail-time" data-label="${label}">${anomaly?'<strong class="timeliness-anomaly">数据异常</strong><small>实际时间无法计算</small>':value?`<strong>${bj(value)}</strong><small>${duration==null?"数据异常":hours(duration)}</small>`:'<strong class="muted">实际时间暂无</strong>'}</td>`}
async function loadReturns() {
  $("#returnsRows").innerHTML='<tr><td colspan="5" class="return-empty">取消明细加载中…</td></tr>';
  try { const query=new URLSearchParams({shop_id:state.shop,page:state.pages.returns,q:$("#returnsQuery").value,from:returnsRange.start,to:returnsRange.end}),data=await api(`/api/returns?${query}`);
  $("#returnsCount").textContent=data.total;
  summary("returns",[["取消记录",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.quantity,0)} 件`])]);
  $("#returnsRows").innerHTML=data.items.map(r=>`<tr><td data-label="店铺／时间"><strong>${esc(r.shop_name)}</strong><small>${bj(r.occurred_at)}</small></td><td data-label="订单号">${cell(r.posting_number)}</td><td class="return-product" data-label="商品信息"><strong title="${esc(r.product_name)}">${cell(r.product_name)}</strong><small>SKU ${cell(r.sku)} · 货号 ${cell(r.offer_id)}</small></td><td data-label="数量"><strong>${num(r.quantity,0)} 件</strong></td><td data-label="取消原因／状态"><strong title="${esc(r.reason_raw)}">${cell(r.reason)}</strong><small>${cell(r.status||r.type)}</small></td></tr>`).join("") || '<tr><td colspan="5" class="return-empty">当前筛选范围内没有取消记录。</td></tr>';
  pager("returns",data,loadReturns);
  } catch(error){$("#returnsRows").innerHTML=`<tr><td colspan="5" class="return-empty error">${esc(error.message)}</td></tr>`;throw error}
}
async function loadRfbsReturns() {
  $("#rfbsReturnsRows").innerHTML='<tr><td colspan="6" class="return-empty">退货明细加载中…</td></tr>';
  try { const query=new URLSearchParams({shop_id:state.shop,page:state.pages.rfbsReturns,q:$("#rfbsReturnsQuery").value,from:returnsRange.start,to:returnsRange.end}),data=await api(`/api/rfbs-returns?${query}`);
  $("#rfbsReturnsCount").textContent=data.total;
  summary("rfbsReturns",[["退货申请",num(data.summary.records,0)],...data.summary.shops.map(s=>[s.shop_name,`${num(s.records,0)} 条申请`])]);
  $("#rfbsReturnsRows").innerHTML=data.items.map(r=>`<tr><td data-label="店铺／申请时间"><strong>${esc(r.shop_name)}</strong><small>${bj(r.created_at)}</small></td><td data-label="申请编号／订单号"><strong>${cell(r.return_number)}</strong><small>订单 ${cell(r.posting_number)}</small></td><td class="return-product" data-label="商品信息"><strong title="${esc(r.product_name)}">${cell(r.product_name)}</strong><small>SKU ${cell(r.sku)} · 货号 ${cell(r.offer_id)}</small></td><td data-label="状态／赔偿"><strong>${cell(r.status_name||r.status_raw)}</strong><small>赔偿 ${cell(r.compensation_status)}</small></td><td data-label="数量／金额"><strong>${num(r.quantity,0)} 件</strong><small>${money(r.product_amount,r.product_currency)}</small></td><td data-label="原因／退回信息"><strong title="${esc(r.reason_raw)}">${cell(r.reason_name||r.reason_raw)}</strong><small>退回 ${bj(r.logistic_return_at)}</small>${r.buyer_comment_raw?`<details class="return-text"><summary>买家原文</summary><p lang="ru">${esc(r.buyer_comment_raw)}</p></details>`:""}</td></tr>`).join("") || '<tr><td colspan="6" class="return-empty">当前筛选范围内没有退货申请。</td></tr>';
  pager("rfbsReturns",data,loadRfbsReturns);
  } catch(error){$("#rfbsReturnsRows").innerHTML=`<tr><td colspan="6" class="return-empty error">${esc(error.message)}</td></tr>`;throw error}
}
async function loadComplaints(){
  $("#complaintRows").innerHTML='<tr><td colspan="5" class="return-empty">投诉记录加载中…</td></tr>';
  try { const query=new URLSearchParams({shop_id:state.shop,q:$("#complaintQuery").value,status:$("#complaintStatus").value,page:state.pages.complaints,from:returnsRange.start,to:returnsRange.end}),data=await api(`/api/complaints?${query}`);state.complaints=data.items;$("#complaintsCount").textContent=data.total;$("#complaintRows").innerHTML=data.items.map(r=>`<tr><td data-label="店铺／订单号"><strong>${esc(r.shop_name)}</strong><small>${esc(r.posting_number)}</small></td><td data-label="投诉编号／时间／渠道"><strong>${esc(r.complaint_number)}</strong><small>${bj(r.complaint_at)} · ${esc(r.channel)}</small></td><td data-label="完结状态"><span class="complaint-state ${r.resolved==1?'done':r.resolved==0?'open':''}">${triText(r.resolved)}</span></td><td data-label="包裹／赔付"><strong>退回 ${triText(r.package_returned)}</strong><small>${r.compensation_amount==null?"赔付暂无":`${num(r.compensation_amount)} ${esc(r.compensation_currency)}`}</small></td><td class="complaint-note-cell" data-label="备注／操作"><span title="${esc(r.notes)}">${esc(r.notes||"备注暂无")}</span><button type="button" data-edit-complaint="${r.shop_id}:${esc(r.complaint_number)}">编辑</button></td></tr>`).join("")||'<tr><td colspan="5" class="return-empty">当前筛选范围内没有投诉记录。</td></tr>';pager("complaints",data,loadComplaints)
  } catch(error){$("#complaintRows").innerHTML=`<tr><td colspan="5" class="return-empty error">${esc(error.message)}</td></tr>`;throw error}
}
const loadReturnPage=()=>Promise.all([loadReturns(),loadRfbsReturns(),loadComplaints()]);
async function loadStock() {
  $("#stockRows").innerHTML='<tr><td colspan="8" class="stock-empty">库存数据加载中…</td></tr>';
  try {const query=new URLSearchParams({shop_id:state.shop,page:state.pages.stock,sku:$("#stockSku").value,offer_id:$("#stockOffer").value,product_name:$("#stockProduct").value,sort_by:state.stockSort.key,sort_order:state.stockSort.order}),data=await api(`/api/stock?${query}`);
  document.querySelectorAll("[data-stock-sort-column]").forEach(th=>{const active=th.dataset.stockSortColumn===state.stockSort.key;th.setAttribute("aria-sort",active?(state.stockSort.order==="asc"?"ascending":"descending"):"none");th.querySelector("span").textContent=active?(state.stockSort.order==="asc"?"↑":"↓"):"↕"});
  summary("stock",[["在售 SKU",num(data.summary.active_skus,0)],["FBP可售库存",num(data.summary.fbp_present,0)],["FBP预留库存",num(data.summary.fbp_reserved,0)],["建议FBP备货SKU",num(data.summary.replenishment_skus,0),`预计到货前缺货 ${num(data.summary.shortage_skus,0)} 个`]]);
  $("#stockUpdated").textContent=`库存更新至 ${bj(data.data_through)}｜销量更新至 ${bj(data.sales_through)}`;
  const inventory=c=>`<strong>可售 ${num(c.present,0)}</strong><small>预留 ${num(c.reserved,0)}</small>`;
  $("#stockRows").innerHTML=data.items.map(r=>{const risk=r.daily_sales<=0?"no-sales":r.days_available<30?"danger":r.days_available<90?"warning":"safe";return `<tr><td class="stock-product" data-label="商品信息"><strong title="${esc(r.display_name)}">${esc(r.display_name)}</strong>${r.short_name&&r.product_name_raw?`<small title="${esc(r.product_name_raw)}">原名 ${esc(r.product_name_raw)}</small>`:""}<small>${esc(r.shop_name)} · SKU ${esc(r.sku)} · 货号 ${esc(r.offer_id||"暂无")}</small></td><td class="stock-channel-cell channel-fbp-bg" data-label="FBP">${inventory(r.channels[0])}</td><td class="stock-channel-cell channel-fbs-bg" data-label="realFBS">${inventory(r.channels[1])}</td><td class="stock-channel-cell channel-whd-bg" data-label="WHD">${inventory(r.channels[2])}</td><td class="stock-sales" data-label="有效销量"><span>7天 <b>${num(r.sales_7,0)}</b> 件</span><span>15天 <b>${num(r.sales_15,0)}</b> 件</span><span>30天 <b>${num(r.sales_30,0)}</b> 件</span></td><td class="stock-forecast" data-label="综合预测"><strong>${r.daily_sales?`${num(r.daily_sales,2)} 件/天`:"无法估算"}</strong><small>FBP可售 ${r.days_available==null?"—":`${num(r.days_available,1)} 天`}</small></td><td class="stock-decision ${risk}" data-label="FBP备货决策"><strong>${esc(r.risk_status)}</strong><small>建议备货 ${r.replenishment==null?"—":`${num(r.replenishment,0)} 件`}</small></td><td class="stock-times" data-label="数据更新"><span>库存 ${bj(r.observed_at)}</span><span>销量 ${bj(data.sales_through)}</span></td></tr>`}).join("") || '<tr><td colspan="8" class="stock-empty">当前筛选条件下没有库存或近期有效销量记录。</td></tr>';
  pager("stock",data,loadStock)}catch(error){$("#stockRows").innerHTML=`<tr><td colspan="8" class="stock-empty error">${esc(error.message)}</td></tr>`;throw error}
}
async function loadImports() {
  updateExportScope();
  $("#importRows").innerHTML='<tr><td colspan="4" class="transfer-empty">导入记录加载中…</td></tr>';
  const rows=await api("/api/imports");
  $("#importRows").innerHTML=rows.map(r=>`<tr><td class="import-filename" data-label="文件"><strong title="${esc(r.filename)}">${esc(r.filename)}</strong></td><td data-label="店铺／渠道"><strong>${esc(r.shop_name)}</strong>${channelTag(r.kind)}</td><td class="num" data-label="导入行数">${num(r.row_count,0)} 行</td><td data-label="导入时间">${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="4" class="transfer-empty">暂无导入记录。</td></tr>';
}
async function loadSync() {
  const selected=state.shop?state.shops.find(shop=>shop.id===state.shop)?.name:"请选择具体店铺";$("#syncManualShop").textContent=selected||"请选择具体店铺";
  $("#syncRows").innerHTML='<tr><td colspan="5" class="sync-message">拉取记录加载中…</td></tr>';
  try {const rows=await api("/api/sync");
  $("#syncRows").innerHTML=rows.map(r=>{const total=Math.max(1,Number(r.progress_total||1)),done=Number(r.progress_done||0),percent=Math.round(done/total*100),status=r.status==='failed'?'失败':r.status==='success'?'成功':'进行中',source=r.run_source==='auto'?'自动':'手动',module=syncNames[r.module]||r.module;return `<tr><td data-label="店铺"><strong>${esc(r.shop_name)}</strong></td><td data-label="模块"><strong>${esc(module)}</strong><span class="sync-source ${r.run_source==='auto'?'auto':'manual'}">${source}</span></td><td data-label="状态"><span class="sync-state ${esc(r.status)}">${status}</span>${r.status==='running'?`<div class="sync-progress-meta"><span>${done}/${total} 段 · ${percent}%</span><span>${num(r.records,0)} 条</span></div><div class="sync-progress" role="progressbar" aria-label="${esc(module)}拉取进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>${r.current_from?`<small class="sync-current">当前：${esc(r.current_from.slice(0,10))} — ${esc(r.current_to.slice(0,10))}</small>`:''}`:''}</td><td data-label="开始时间">${bj(r.started_at)}</td><td data-label="错误" class="${r.error?'error':'muted'}">${esc(r.error||'—')}</td></tr>`}).join("") || '<tr><td colspan="5" class="sync-message">暂无拉取记录。</td></tr>';
  return rows}catch(error){$("#syncRows").innerHTML=`<tr><td colspan="5" class="sync-message error">拉取记录加载失败：${esc(error.message)}</td></tr>`;throw error}
}
function updateAutoSyncRow(toggle){const row=toggle.closest("[data-auto-row]"),enabled=toggle.checked;row.classList.toggle("is-disabled",!enabled);row.querySelectorAll("[data-auto-setting]").forEach(input=>input.disabled=!enabled);if(!enabled){const error=row.querySelector(".auto-field-error");error?.classList.add("hidden")}}
function validateAutoTime(input,show=true){const valid=/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(input.value)&&input.checkValidity(),error=$("#"+input.getAttribute("aria-describedby"));input.setAttribute("aria-invalid",String(show&&!valid));error?.classList.toggle("hidden",!show||valid);return valid}
async function loadAutoSync(){const rows=await api("/api/auto-sync-settings"),byKey=new Map(rows.map(row=>[`${row.shop_id}:${row.module}`,row]));$("#autoSyncCards").innerHTML=[1,2].map(shop=>{const shopName=state.shops.find(item=>item.id===shop)?.name||`店铺${shop}`;return `<section class="auto-sync-shop"><h3>${esc(shopName)}</h3><div class="auto-sync-rows">${Object.keys(syncNames).map(module=>{const row=byKey.get(`${shop}:${module}`)||{enabled:false,run_time:"02:00",range_days:1},errorId=`autoTimeError-${shop}-${module}`;return `<article class="auto-sync-row" data-auto-row><div class="auto-sync-module"><strong>${syncNames[module]}</strong><small>${module==='stock'?'实时库存':'按日期范围'}</small></div><label class="auto-sync-toggle"><span class="settings-switch"><input id="autoEnabled-${shop}-${module}" data-auto-enabled type="checkbox" ${row.enabled?'checked':''} aria-label="${esc(shopName)}${syncNames[module]}自动拉取"><span aria-hidden="true"></span></span></label><label class="auto-sync-field"><span>每天拉取时间</span><span class="auto-time-wrap"><svg aria-hidden="true"><use href="/static/tabler-icons.svg#clock"/></svg><input id="autoTime-${shop}-${module}" data-auto-setting type="time" step="60" value="${esc(row.run_time)}" required aria-label="${esc(shopName)}${syncNames[module]}每天拉取时间" aria-describedby="${errorId}"></span><small class="auto-time-zone">北京时间</small><small id="${errorId}" class="auto-field-error hidden">请输入有效时间</small></label>${module==='stock'?'<div class="auto-sync-field"><span>拉取范围</span><strong class="snapshot-tag">实时库存</strong></div>':`<label class="auto-sync-field"><span>最近 N 天</span><input id="autoRange-${shop}-${module}" data-auto-setting type="number" min="1" max="365" value="${Number(row.range_days)}" required aria-label="${esc(shopName)}${syncNames[module]}拉取范围"></label>`}</article>`}).join("")}</div></section>`}).join("");document.querySelectorAll("[data-auto-enabled]").forEach(toggle=>{updateAutoSyncRow(toggle);toggle.onchange=()=>updateAutoSyncRow(toggle)});document.querySelectorAll("#autoSyncForm input[type=time]").forEach(input=>{input.onblur=()=>{if(!input.disabled)validateAutoTime(input)};input.oninput=()=>validateAutoTime(input,false)})}
async function loadDingtalk(refreshTemplate=true) {
  const data=await api("/api/dingtalk/settings");
  $("#dingtalkConfigured").textContent=data.configured?"已配置":"未配置";
  $("#dingEnabledStatus").textContent=data.daily_enabled?"已启用":"已停用";
  $("#dingNext").textContent=data.next_push_at?bj(data.next_push_at):"—";
  $("#dingEnabled").checked=data.daily_enabled; $("#dingTime").value=data.push_time;
  document.querySelectorAll("#dingWeekdays input").forEach(input=>input.checked=data.weekdays.includes(Number(input.value)));
  dingSavedTemplate=data.template;dingDefaultTemplate=data.default_template;if(refreshTemplate)$("#dingTemplate").value=data.template;
  updateDingTemplateSaved();
  const last=data.last_run,status=last?(last.status==='success'?'发送成功':last.status==='failed'?'发送失败':'发送中'):"暂无记录";
  $("#dingLastStatus").textContent=status;
  $("#dingtalkLast").innerHTML=`<div><dt>统计日期</dt><dd>${esc(last?.stats_date||'—')}</dd></div><div><dt>推送状态</dt><dd>${esc(status)}</dd></div><div><dt>实际发送时间</dt><dd>${last?.sent_at?bj(last.sent_at):'—'}</dd></div><div><dt>失败原因</dt><dd class="${last?.error?'error':''}">${esc(last?.error||'—')}</dd></div>`;
}
function updateDingTemplateSaved(){const saved=$("#dingTemplate").value===dingSavedTemplate;$("#dingTemplateSaved").textContent=saved?"当前模板已保存":"当前模板有未保存修改";$("#dingTemplateSaved").classList.toggle("unsaved",!saved)}
async function loadRules(){const data=await api("/api/product-rules");$("#ruleKeyNote").textContent=data.key_note;$("#ruleLists").innerHTML=`<h3>短名称</h3>${data.short_names.map(r=>`<p>${esc(r.key_type)}:${esc(r.key_value)} → ${esc(r.short_name)}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>合并组</h3>${data.groups.map(r=>`<p>${esc(r.name)}：${esc(r.key_type||"暂无成员")} ${esc(r.key_value||"")} ${r.key_type?`<button data-ungroup-type="${esc(r.key_type)}" data-ungroup-value="${esc(r.key_value)}">解除</button>`:""}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>品牌规则</h3>${data.brands.map(r=>`<p>${esc(r.brand_name)} · ${esc(r.keyword)} · 优先级 ${r.priority}${r.conflict?' · 冲突':''}</p>`).join("")||'<p class="muted">暂无</p>'}<h3>匹配预览</h3>${data.products.filter(r=>r.matched_brand).slice(0,20).map(r=>`<p>${esc(r.product_name)} → ${esc(r.matched_brand)}</p>`).join("")||'<p class="muted">暂无品牌命中</p>'}`}
async function loadSettings(){$("#probeShops").innerHTML=state.shops.map(s=>`<article class="settings-shop-card"><div class="settings-shop-head"><div><span>店铺 ${s.id}</span><strong>${esc(s.name)}</strong></div><button class="primary" data-probe="${s.id}">检测连接与权限</button></div><div id="probeResult${s.id}" class="settings-probe-result hidden"></div></article>`).join("")}
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

for(const id of ["complaintShop","complaintResolved","complaintReturned","complaintStatus","importShop","importKind"]) returnSelects[id]=createReturnSelect(id);
function activateReturnTab(name,focus=false){
  document.querySelectorAll("[data-return-tab]").forEach(button=>{const active=button.dataset.returnTab===name;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus()});
  document.querySelectorAll(".return-tab").forEach(panel=>{const active=panel.id===`returns-${name}`;panel.classList.toggle("active",active);panel.hidden=!active});
}
function resetComplaintForm(close=false){$("#complaintForm").reset();setReturnSelect("complaintShop","");setReturnSelect("complaintResolved","");setReturnSelect("complaintReturned","");$("#complaintEditorTitle").textContent="新增投诉";if(close)$("#complaintEditor").open=false}

$("#loginForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});const session=await api("/api/session");state.csrf=session.csrf_token;showShell();await loadShops();await loadOverview()}catch(err){$("#loginError").textContent=err.message}});
$("#nav").addEventListener("click",e=>{const button=e.target.closest("[data-page]");if(button)openPage(button.dataset.page)});
$("#shopPickerButton").onclick=()=>{const hidden=$("#shopOptions").classList.toggle("hidden");$("#shopPickerButton").setAttribute("aria-expanded",String(!hidden))};
$("#shopOptions").onclick=e=>{const option=e.target.closest("[data-shop]");if(!option)return;state.shop=Number(option.dataset.shop);state.page=1;Object.keys(state.pages).forEach(k=>state.pages[k]=1);$("#shopPickerValue").textContent=option.textContent;document.querySelectorAll("#shopOptions [data-shop]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");const page=$(".page.active").id;loadPage(page).catch(err=>toast(err.message,true))};
$("#channelPickerButton").onclick=()=>{const hidden=$("#channelOptions").classList.toggle("hidden");$("#channelPickerButton").setAttribute("aria-expanded",String(!hidden))};
$("#channelOptions").onclick=e=>{const option=e.target.closest("[data-channel]");if(!option)return;$("#channelFilter").value=option.dataset.channel;$("#channelPickerValue").textContent=option.textContent;document.querySelectorAll("#channelOptions [data-channel]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelFilter").dispatchEvent(new Event("change"))};
$("#orderFilterForm").addEventListener("submit",e=>{e.preventDefault();state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#orderList").onclick=e=>{const button=e.target.closest("[data-add-complaint]"),posting=button?.dataset.addComplaint;if(!posting)return;openPage("returns");resetComplaintForm();$("#complaintPosting").value=posting;setReturnSelect("complaintShop",button.dataset.complaintShop);activateReturnTab("complaints");$("#complaintEditor").open=true;$("#complaintNumber").focus()};
$("#orderSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#orderFilterForm").requestSubmit()}});
$("#channelFilter").addEventListener("change",()=>{state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#riskGrouped").addEventListener("change",()=>loadRisk().catch(err=>toast(err.message,true)));
$("#riskSearch").addEventListener("input",renderRiskItems);
$("#timelinessFilterForm").addEventListener("submit",e=>{e.preventDefault();state.pages.timeliness=1;loadTimeliness().catch(err=>toast(err.message,true))});
$("#timelinessClear").onclick=()=>{$("#timelinessSearch").value="";state.pages.timeliness=1;loadTimeliness().catch(err=>toast(err.message,true))};
$("#stockFilterForm").onsubmit=e=>{e.preventDefault();state.pages.stock=1;loadStock().catch(err=>toast(err.message,true))};
$("#stockClear").onclick=()=>{$("#stockFilterForm").reset();state.pages.stock=1;loadStock().catch(err=>toast(err.message,true))};
document.querySelectorAll("[data-stock-sort]").forEach(button=>button.onclick=()=>{const key=button.dataset.stockSort;state.stockSort.order=state.stockSort.key===key&&state.stockSort.order==="desc"?"asc":"desc";state.stockSort.key=key;state.pages.stock=1;loadStock().catch(err=>toast(err.message,true))});
$("#returnTabs").onclick=e=>{const tab=e.target.closest("[data-return-tab]")?.dataset.returnTab;if(tab)activateReturnTab(tab)};
$("#returnTabs").onkeydown=e=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;e.preventDefault();const tabs=[...$("#returnTabs").querySelectorAll("[role=tab]")],current=tabs.indexOf(document.activeElement),index=e.key==="Home"?0:e.key==="End"?tabs.length-1:(current+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;activateReturnTab(tabs[index].dataset.returnTab,true)};
$("#returnsSearch").onsubmit=e=>{e.preventDefault();state.pages.returns=1;loadReturns().catch(err=>toast(err.message,true))};
$("#returnsClear").onclick=()=>{$("#returnsQuery").value="";state.pages.returns=1;loadReturns().catch(err=>toast(err.message,true))};
$("#rfbsReturnsSearch").onsubmit=e=>{e.preventDefault();state.pages.rfbsReturns=1;loadRfbsReturns().catch(err=>toast(err.message,true))};
$("#rfbsReturnsClear").onclick=()=>{$("#rfbsReturnsQuery").value="";state.pages.rfbsReturns=1;loadRfbsReturns().catch(err=>toast(err.message,true))};
$("#complaintSearch").onsubmit=e=>{e.preventDefault();state.pages.complaints=1;loadComplaints().catch(err=>toast(err.message,true))};
$("#complaintRows").onclick=e=>{const key=e.target.dataset.editComplaint;if(!key)return;const [shop,...number]=key.split(":"),r=state.complaints.find(x=>x.shop_id===Number(shop)&&x.complaint_number===number.join(":"));if(!r)return;setReturnSelect("complaintShop",r.shop_id);$("#complaintPosting").value=r.posting_number;$("#complaintNumber").value=r.complaint_number;$("#complaintAt").value=new Date(new Date(r.complaint_at).getTime()+8*3600000).toISOString().slice(0,16);$("#complaintChannel").value=r.channel;setReturnSelect("complaintResolved",r.resolved==null?"":String(Boolean(r.resolved)));setReturnSelect("complaintReturned",r.package_returned==null?"":String(Boolean(r.package_returned)));$("#complaintAmount").value=r.compensation_amount??"";$("#complaintCurrency").value=r.compensation_currency??"";$("#complaintNotes").value=r.notes??"";$("#complaintEditorTitle").textContent=`编辑投诉·${r.complaint_number}`;$("#complaintEditor").open=true;$("#complaintEditor").scrollIntoView({behavior:"smooth"})};
$("#complaintReset").onclick=()=>resetComplaintForm();
$("#reasonRows").onclick=async e=>{const reason=e.target.closest("[data-reason]")?.dataset.reason;if(!reason)return;const target=$("#reasonDetails"),query=new URLSearchParams({shop_id:state.shop,reason,from:riskRange.start,to:riskRange.end});target.classList.remove("hidden");target.innerHTML="原因订单加载中…";try{const data=await api(`/api/risk/reasons?${query}`);target.innerHTML=`<h3>${esc(e.target.textContent)}对应订单</h3><div>${data.details.map(r=>`<span>${esc(r.shop_name)} · ${channelTag(r.channel)} · ${esc(r.posting_number)} · ${num(r.pieces,0)}件</span>`).join("")||'<span class="muted">当前时间范围内没有对应订单。</span>'}</div>`}catch(error){target.innerHTML=`<span class="error">${esc(error.message)}</span>`}};
$("#prevPage").onclick=()=>{state.page--;loadOrders()}; $("#nextPage").onclick=()=>{state.page++;loadOrders()};
$("#shopForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:$("#shop1").value,2:$("#shop2").value})});await loadShops();toast("店铺名称已更新")}catch(err){toast(err.message,true)}});
$("#probeShops").onclick=async e=>{const button=e.target.closest("[data-probe]");if(!button)return;const id=button.dataset.probe,target=$("#probeResult"+id);button.disabled=true;target.classList.remove("hidden");target.innerHTML='<span class="probe-state">正在检测</span><p>正在验证凭据与权限，请稍候。</p>';try{target.innerHTML=probeResult(await api(`/api/ozon/probe/${id}`,{method:"POST"}))}catch(error){target.innerHTML=probeResult({valid:false,error:error.message})}finally{button.disabled=false}};
$("#dingtalkForm").addEventListener("submit",async e=>{e.preventDefault();try{const weekdays=[...document.querySelectorAll("#dingWeekdays input:checked")].map(input=>Number(input.value));await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({daily_enabled:$("#dingEnabled").checked,push_time:$("#dingTime").value,weekdays})});toast("推送计划已保存");await loadDingtalk(false)}catch(err){toast(err.message,true)}});
$("#dingTemplate").oninput=updateDingTemplateSaved;
$("#dingResetTemplate").onclick=()=>{$("#dingTemplate").value=dingDefaultTemplate;updateDingTemplateSaved()};
$("#dingPreviewButton").onclick=async e=>{e.target.disabled=true;try{const data=await api("/api/dingtalk/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({template:$("#dingTemplate").value})});$("#dingPreview").textContent=data.message}catch(err){toast(err.message,true)}finally{e.target.disabled=false}};
$("#dingSaveTemplate").onclick=async e=>{e.target.disabled=true;try{const data=await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({template:$("#dingTemplate").value})});dingSavedTemplate=data.template;updateDingTemplateSaved();toast("消息模板已保存")}catch(err){toast(err.message,true)}finally{e.target.disabled=false}};
$("#dingTestButton").onclick=async e=>{e.target.disabled=true;try{await api("/api/dingtalk/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({template:$("#dingTemplate").value})});toast("测试消息已发送")}catch(err){toast(err.message,true)}finally{e.target.disabled=false}};
let importing=false;
const importFileValid=file=>file?.name.toLowerCase().endsWith(".csv");
function updateImportReady(message=""){
  const file=$("#importFile").files[0],ready=Boolean($("#importShop").value&&$("#importKind").value&&importFileValid(file));
  $("#importSubmit").disabled=importing||!ready;
  if(message)$("#importStatus").textContent=message;else if(!importing)$("#importStatus").textContent=ready?"已就绪，可以导入":"请选择店铺、渠道和 CSV 文件";
}
function showImportFile(file){
  const valid=importFileValid(file);$("#importFileName").textContent=file?.name||"尚未选择文件";$("#importFileName").title=file?.name||"";$("#importFileSize").textContent=file?`${num(file.size/1024,1)} KB${valid?"":" · 仅支持 .csv"}`:"仅支持 .csv，最大 50MB";$("#importChooseFile").textContent=file?"更换文件":"选择文件";$("#importFilePanel").classList.toggle("is-invalid",Boolean(file&&!valid));updateImportReady(file&&!valid?"请选择 CSV 文件":"");
}
$("#importChooseFile").onclick=()=>$("#importFile").click();
$("#importFilePanel").onclick=e=>{if(!e.target.closest("button"))$("#importFile").click()};
$("#importFile").onchange=()=>showImportFile($("#importFile").files[0]);
for(const id of ["importShop","importKind"])$("#"+id).addEventListener("change",()=>updateImportReady());
$("#importFilePanel").ondragover=e=>{e.preventDefault();e.currentTarget.classList.add("is-dragging")};
$("#importFilePanel").ondragleave=e=>e.currentTarget.classList.remove("is-dragging");
$("#importFilePanel").ondrop=e=>{e.preventDefault();e.currentTarget.classList.remove("is-dragging");const file=e.dataTransfer.files[0];if(!file)return;const transfer=new DataTransfer();transfer.items.add(file);$("#importFile").files=transfer.files;showImportFile(file)};
$("#importForm").addEventListener("submit",async e=>{e.preventDefault();if(importing)return;const file=$("#importFile").files[0],shop=$("#importShop").value,kind=$("#importKind").value;if(!file||!shop||!kind||!importFileValid(file)){updateImportReady("请完整选择店铺、渠道和 CSV 文件");return}importing=true;$("#importSubmit").textContent="正在导入";updateImportReady("正在导入，请稍候…");try{const result=await api(`/api/import/${kind}?shop_id=${shop}`,{method:"POST",headers:{"X-Filename":encodeURIComponent(file.name)},body:file});$("#importFile").value="";showImportFile();updateImportReady(`成功导入 ${num(result.rows,0)} 行`);toast(`已导入 ${result.rows} 行`);await loadImports()}catch(err){updateImportReady(`导入失败：${err.message}`);toast(err.message,true)}finally{importing=false;$("#importSubmit").textContent="导入数据";updateImportReady($("#importStatus").textContent)}});
const exportNames={orders:["订单","订单号、渠道、时间、状态及金额"],risk:["SKU风险及原因","SKU、渠道、货件及固定取消原因"],timeliness:["发货配送时效","创建、实际发货和实际签收时间"],returns:["退货","取消记录和退货申请"],complaints:["投诉","投诉编号、状态、赔付及备注"],stock:["库存","库存来源、仓库和库存数量"],rules:["商品规则","短名称、合并组和品牌规则"]};
$("#exportButtons").innerHTML=Object.entries(exportNames).map(([key,[name,description]])=>`<article class="export-card"><div><strong>${name}</strong><p>${description}</p><small>${key==="rules"?"当前规则，不受时间筛选影响":"受当前时间范围影响"}</small></div><button type="button" data-export="${key}">导出</button></article>`).join("");
function updateExportScope(){const shop=state.shop?state.shops.find(item=>item.id===state.shop)?.name:"两店铺合并";$("#exportScope").textContent=`当前店铺：${shop||"两店铺合并"}｜时间范围：${exportRange.start} 至 ${exportRange.end}`}
$("#exportButtons").onclick=e=>{const button=e.target.closest("[data-export]"),module=button?.dataset.export;if(!module)return;const query=new URLSearchParams({shop_id:state.shop});if(module!=="rules"){query.set("date_from",exportRange.start);query.set("date_to",exportRange.end)}button.disabled=true;const text=button.textContent;button.textContent="正在准备…";location.href=`/api/export/${module}?${query}`;setTimeout(()=>{button.disabled=false;button.textContent=text},800)};
$("#complaintForm").onsubmit=async e=>{e.preventDefault();const tri=id=>$(id).value===""?null:$(id).value==="true";await api("/api/complaints",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:Number($("#complaintShop").value),posting_number:$("#complaintPosting").value,complaint_number:$("#complaintNumber").value,complaint_at:new Date(`${$("#complaintAt").value}:00+08:00`).toISOString(),channel:$("#complaintChannel").value,resolved:tri("#complaintResolved"),package_returned:tri("#complaintReturned"),compensation_amount:$("#complaintAmount").value||null,compensation_currency:$("#complaintCurrency").value,notes:$("#complaintNotes").value})});toast("投诉已保存");resetComplaintForm(true);state.pages.complaints=1;await loadComplaints()};
$("#shortNameForm").onsubmit=async e=>{e.preventDefault();await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"short_name",key_type:$("#shortKeyType").value,key_value:$("#shortKeyValue").value,short_name:$("#shortName").value})});toast("短名称已保存");await loadRules()};
$("#brandForm").onsubmit=async e=>{e.preventDefault();await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"brand",brand_name:$("#brandName").value,keyword:$("#brandKeyword").value,priority:Number($("#brandPriority").value),enabled:$("#brandEnabled").checked})});toast("品牌规则已保存");await loadRules()};
$("#groupForm").onsubmit=async e=>{e.preventDefault();const members=$("#groupMembers").value.split(/\n+/).filter(Boolean).map(line=>{const [key_type,...rest]=line.split(":");return {key_type,key_value:rest.join(":").trim()}});await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"group",name:$("#groupName").value,members})});toast("合并组已保存");await loadRules()};
$("#ruleLists").onclick=async e=>{const keyType=e.target.dataset.ungroupType;if(!keyType)return;await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"ungroup",key_type:keyType,key_value:e.target.dataset.ungroupValue})});toast("已解除合并");await loadRules()};
$("#syncButtons").innerHTML=Object.entries(syncNames).map(([key,name])=>`<article class="sync-manual-card" data-sync-module="${key}"><div><strong>${name}</strong><p>${syncDescriptions[key]}</p></div><button class="primary" type="button" data-module="${key}">拉取${name}</button></article>`).join("");
$("#autoSyncForm").addEventListener("submit",async e=>{e.preventDefault();const enabledTimes=[...document.querySelectorAll("#autoSyncForm [data-auto-enabled]:checked")].map(toggle=>$("#autoTime-"+toggle.id.slice("autoEnabled-".length))),timesValid=enabledTimes.map(input=>validateAutoTime(input)).every(Boolean);if(!timesValid||!e.currentTarget.reportValidity()){toast("请检查自动拉取设置",true);return}const values=Object.fromEntries([1,2].map(shop=>[String(shop),Object.fromEntries(Object.keys(syncNames).map(module=>[module,{enabled:$("#autoEnabled-"+shop+"-"+module).checked,run_time:$("#autoTime-"+shop+"-"+module).value,range_days:module==="stock"?1:Number($("#autoRange-"+shop+"-"+module).value)}]))]));try{await api("/api/auto-sync-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(values)});toast("两店铺自动拉取设置已保存");await loadAutoSync()}catch(err){toast(err.message,true)}});
const today=new Date(); today.setHours(0,0,0,0);
const isoDate=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const localDate=value=>{const [year,month,day]=value.split("-").map(Number);return new Date(year,month-1,day)};
const shiftDays=(date,amount)=>new Date(date.getFullYear(),date.getMonth(),date.getDate()+amount);
const shiftMonths=(date,amount)=>new Date(date.getFullYear(),date.getMonth()+amount,1);
const threeMonthsAgo=(()=>{const target=new Date(today.getFullYear(),today.getMonth()-3,1);target.setDate(Math.min(today.getDate(),new Date(target.getFullYear(),target.getMonth()+1,0).getDate()));return target})();
const monthNames=["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
function createDateRange(rootId,onChange){
  const root=$(rootId),range={start:isoDate(threeMonthsAgo),end:isoDate(today),selecting:false,view:new Date(today.getFullYear(),today.getMonth(),1),preset:"3months"};
  root.innerHTML=`<div class="date-range-wrap"><button class="date-range-button" data-range-role="button" type="button" aria-haspopup="dialog" aria-expanded="false"><span>日期范围：</span><strong data-range-role="label">近三个月</strong><span aria-hidden="true">⌄</span></button><div class="date-range-panel hidden" data-range-role="panel" role="dialog" aria-label="选择日期范围"><div class="range-calendars"><div class="range-calendar"><div class="range-month-head"><button data-range-role="prev" type="button" aria-label="上个月">‹</button><strong data-range-role="month-a"></strong><span></span></div><div class="range-weekdays"><span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>周日</span></div><div class="range-days" data-range-role="days-a"></div></div><div class="range-calendar"><div class="range-month-head"><span></span><strong data-range-role="month-b"></strong><button data-range-role="next" type="button" aria-label="下个月">›</button></div><div class="range-weekdays"><span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>周日</span></div><div class="range-days" data-range-role="days-b"></div></div></div><div class="range-presets"><button type="button" data-range="today">今天</button><button type="button" data-range="3days">3天内</button><button type="button" data-range="7days">7天内</button><button type="button" data-range="3months">近三个月</button><button type="button" data-range="all">全部时间</button></div></div></div>`;
  const find=role=>root.querySelector(`[data-range-role="${role}"]`),label=find("label"),panel=find("panel"),button=find("button");
  const month=(value,title,days)=>{title.textContent=`${monthNames[value.getMonth()]} ${value.getFullYear()}年`;const first=new Date(value.getFullYear(),value.getMonth(),1),last=new Date(value.getFullYear(),value.getMonth()+1,0),items=[];for(let index=0;index<(first.getDay()+6)%7;index++)items.push('<span class="range-blank"></span>');for(let day=1;day<=last.getDate();day++){const current=new Date(value.getFullYear(),value.getMonth(),day),key=isoDate(current),weekend=current.getDay()===0||current.getDay()===6,inRange=key>=range.start&&key<=range.end,edge=key===range.start||key===range.end;items.push(`<button type="button" data-date="${key}" class="${weekend?'weekend ':''}${inRange?'in-range ':''}${edge?'range-edge ':''}${key===isoDate(today)?'today':''}" aria-label="${value.getFullYear()}年${value.getMonth()+1}月${day}日">${day}</button>`)}days.innerHTML=items.join("")};
  const render=()=>{month(range.view,find("month-a"),find("days-a"));month(shiftMonths(range.view,1),find("month-b"),find("days-b"));root.querySelectorAll("[data-range]").forEach(item=>item.classList.toggle("active",item.dataset.range===range.preset))};
  const set=(start,end,text,preset="",notify=true)=>{range.start=isoDate(start);range.end=isoDate(end);range.selecting=false;range.preset=preset;label.textContent=text;render();if(notify)onChange(range)};
  const preset=(name,notify=true)=>{const choices={today:[today,today,"今天"],"3days":[shiftDays(today,-2),today,"3天内"],"7days":[shiftDays(today,-6),today,"7天内"],"3months":[threeMonthsAgo,today,"近三个月"],all:[new Date(2020,0,1),today,"全部时间"]};set(...choices[name],name,notify)};
  root.onclick=e=>{const role=e.target.closest("[data-range-role]")?.dataset.rangeRole;if(role==="button"){const hidden=panel.classList.toggle("hidden");button.setAttribute("aria-expanded",String(!hidden));render();return}if(role==="prev"||role==="next"){range.view=shiftMonths(range.view,role==="prev"?-1:1);render();return}if(e.target.dataset.range){preset(e.target.dataset.range);panel.classList.add("hidden");button.setAttribute("aria-expanded","false");return}const value=e.target.dataset.date;if(!value)return;if(!range.selecting){range.start=value;range.end=value;range.selecting=true;range.preset="";label.textContent=`${value.replaceAll("-","/")} – 请选择结束日期`;render()}else{const first=localDate(range.start),second=localDate(value);set(first<=second?first:second,first<=second?second:first,`${isoDate(first<=second?first:second).replaceAll("-","/")} – ${isoDate(first<=second?second:first).replaceAll("-","/")}`);panel.classList.add("hidden");button.setAttribute("aria-expanded","false")}};
  preset("3months",false);return range;
}
const overviewRange=createDateRange("#overviewDateRange",()=>loadOverview().catch(error=>toast(error.message,true)));
const orderRange=createDateRange("#orderDateRange",()=>{state.page=1;loadOrders().catch(error=>toast(error.message,true))});
const riskRange=createDateRange("#riskDateRange",()=>loadRisk().catch(error=>toast(error.message,true)));
const timelinessRange=createDateRange("#timelinessDateRange",()=>{state.pages.timeliness=1;loadTimeliness().catch(error=>toast(error.message,true))});
const returnsRange=createDateRange("#returnsDateRange",()=>{state.pages.returns=state.pages.rfbsReturns=state.pages.complaints=1;loadReturnPage().catch(error=>toast(error.message,true))});
const exportRange=createDateRange("#exportDateRange",()=>updateExportScope());
const syncRange=createDateRange("#syncDateRange",()=>{});
document.addEventListener("click",e=>{if(!e.target.closest(".date-range-wrap"))document.querySelectorAll(".date-range-panel").forEach(panel=>panel.classList.add("hidden"));if(!e.target.closest(".shop-label")){$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false")}if(!e.target.closest(".channel-picker")){$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false")}if(!e.target.closest("[data-return-select],[data-import-select]"))Object.values(returnSelects).forEach(select=>select.close());if(!e.target.closest("#orderTrend"))$("#orderTrend .trend-tooltip")?.classList.add("hidden")});
$("#overviewExceptions").onclick=e=>{const page=e.target.closest("[data-overview-page]")?.dataset.overviewPage;if(page)openPage(page)};
document.addEventListener("keydown",e=>{if(e.key==="Escape"){document.querySelectorAll(".date-range-panel").forEach(panel=>panel.classList.add("hidden"));document.querySelectorAll(".date-range-button").forEach(button=>button.setAttribute("aria-expanded","false"));$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");Object.values(returnSelects).forEach(select=>select.close())}});
$("#trendGranularity").onclick=e=>{const value=e.target.dataset.granularity;if(!value)return;state.overviewGranularity=value;$("#trendGranularity").querySelectorAll("button").forEach(button=>button.classList.toggle("active",button===e.target));loadOverview().catch(error=>toast(error.message,true))};
async function waitForSync(runId,module){for(;;){const task=await api(`/api/sync/${runId}`);await loadSync();if(task.status!=="running"){if(task.status==="success")toast(`${syncNames[module]}拉取完成：${num(task.records,0)} 条`);else toast(task.error||"拉取失败",true);return}await new Promise(resolve=>setTimeout(resolve,1000))}}
$("#syncButtons").onclick=async e=>{const button=e.target.closest("[data-module]"),module=button?.dataset.module;if(!module)return;if(!state.shop)return toast("请先在左上角选择一个店铺",true);if(syncRange.preset==="all"&&!confirm("整个时段将按自然月逐段拉取，耗时可能较长。确认开始？"))return;const text=button.textContent;button.disabled=true;button.textContent="拉取中…";try{const task=await api(`/api/sync/${module}?shop_id=${state.shop}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:syncRange.start,to:syncRange.end})});await loadSync();await waitForSync(task.run_id,module)}catch(err){toast(err.message,true);await loadSync()}finally{button.disabled=false;button.textContent=text}};
const systemTheme=window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(){const follow=localStorage.getItem("themeFollowSystem")==="true",dark=follow?systemTheme.matches:localStorage.getItem("theme")==="dark";document.documentElement.dataset.theme=dark?"dark":"";$("#themeFollowSystem").checked=follow;$("#themePreferenceText").textContent=follow?`已跟随系统 · 当前${dark?"深色":"浅色"}模式`:"关闭后可使用左下角按钮手动切换"}
$("#themeFollowSystem").onchange=e=>{if(!e.target.checked)localStorage.setItem("theme",document.documentElement.dataset.theme==="dark"?"dark":"light");localStorage.setItem("themeFollowSystem",String(e.target.checked));applyTheme()};
systemTheme.addEventListener("change",()=>{if(localStorage.getItem("themeFollowSystem")==="true")applyTheme()});
$("#themeButton").onclick=()=>{const dark=document.documentElement.dataset.theme!=="dark";localStorage.setItem("themeFollowSystem","false");localStorage.setItem("theme",dark?"dark":"light");applyTheme()};
$("#settingsButton").onclick=()=>openPage("settings");
applyTheme();

(async()=>{const s=await api("/api/session");if(!s.authenticated)return showLogin();state.csrf=s.csrf_token;showShell();await loadShops();await loadOverview()})().catch(e=>toast(e.message,true));
