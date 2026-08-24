const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], csrf:"", overviewGranularity:"week", orderStatus:"", stockSort:{key:"",order:"desc"}, pages: {timeliness:1,returns:1,rfbsReturns:1,shippingComplaints:1,receivedDisputes:1,stock:1}};
let riskItems = [];
let shippingComplaintItems=[],receivedDisputeItems=[];
let riskHighOnly = false;
let ruleData=null,mergeMemberIndex=0;
const titles = {overview:"总览",orders:"订单",risk:"订单取消分析",timeliness:"发货与配送时效",returns:"异常订单明细",complaintPlaceholder:"异常订单投诉",stock:"销量与备货建议",transfer:"数据导入/导出",sync:"数据同步中心",rules:"商品匹配规则",dingtalk:"钉钉机器人",settings:"系统设置"};
const syncNames = {orders:"订单",returns:"退货",stock:"库存"};
const syncDescriptions = {orders:"拉取订单、商品和订单状态数据",returns:"拉取退货与售后申请数据",stock:"只拉取实时库存数据，不受日期范围影响"};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => { if (!v) return "暂无"; const date=new Date(v); return Number.isNaN(date.getTime()) ? "暂无" : new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(date).replaceAll("/","-"); };
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const metric = (v, digits=2, suffix="") => v == null || v === "" ? "暂无" : `${num(v,digits)}${suffix}`;
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时 / ${num(v/24,1)} 天`;
const money = (amount,currency) => amount==null ? "金额暂无" : `${num(amount)} ${esc(currency||"")}`;
const convertedMoney = (amount,currency) => `${Number(amount).toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2})} ${esc(currency||"")}`;
const cell = (v) => v == null || v === "" ? "暂无" : `<span class="copyable" data-copy="${esc(v)}" title="点击复制">${esc(v)}</span>`;
const channelTag = (v) => `<span class="tag channel-${({FBP:"fbp",realFBS:"fbs",WHD:"whd"}[v] || "")}">${esc(v)}</span>`;
const renderAnalysisCards = cards => cards.map(card => {
  const tone=card.tone||card.rateTone,badge=card.badge||card.rate;
  return `<article class="analysis-summary-card tone-${tone}"><div class="analysis-card-head"><div class="analysis-card-icon"><morph-icon icon="${card.icon}" size="15" stroke-width="2"></morph-icon></div><span class="analysis-card-title">${card.label}</span>${badge?`<span class="analysis-rate-badge">${badge}</span>`:""}</div><strong class="analysis-card-value">${card.count}</strong><small class="analysis-card-note">${card.note}</small></article>`;
}).join("");
const returnSelects = {};
function createReturnSelect(id){
  const select=$(`#${id}`),root=select.closest("[data-return-select],[data-import-select]"),button=root.querySelector("[data-select-button]"),label=root.querySelector("[data-select-label]"),options=root.querySelector("[data-select-options]"),morph=button.querySelector("morph-icon");
  options.id=`${id}Options`;button.setAttribute("aria-controls",options.id);
  const close=()=>{options.classList.add("hidden");button.setAttribute("aria-expanded","false");morph?.morphTo("chevronDown")};
  const render=()=>{const selected=select.options[select.selectedIndex];label.textContent=selected?.textContent||"请选择";options.innerHTML=[...select.options].map(option=>`<button type="button" role="option" tabindex="-1" data-select-value="${esc(option.value)}" aria-selected="${option.selected}">${esc(option.textContent)}</button>`).join("")};
  const set=value=>{select.value=value==null?"":String(value);render()};
  const open=()=>{options.classList.remove("hidden");button.setAttribute("aria-expanded","true");morph?.morphTo("chevronUp")};
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
function trendTip(bucket){
  const isOngoing = bucket.orders === 0 && bucket.from === isoDate(new Date());
  const dateBase = bucket.from === bucket.to ? bucket.from : `${bucket.from} 至 ${bucket.to}`;
  const dateStr = esc(dateBase) + (isOngoing ? ` <span class="ozon-tip-badge">进行中</span>` : ``);
  const channels=[
    {key:"FBP",name:"FBP",color:"#005BFF"},
    {key:"realFBS",name:"realFBS",color:"#00BA68"},
    {key:"WHD",name:"WHD",color:"#FF9F0A"}
  ];
  return `
    <div class="ozon-tip-head">${dateStr}</div>
    <div class="ozon-tip-main">
      <div class="ozon-tip-main-row">
        <span class="ozon-tip-dot" style="background:#005BFF"></span>
        <span class="ozon-tip-main-title">已订购 (有效订单)</span>
        <span class="ozon-tip-main-num"><b>${num(bucket.orders,0)}</b> 单</span>
      </div>
      <div class="ozon-tip-main-gmv">${esc(gmvText(bucket.gmv))}</div>
    </div>
    <div class="ozon-tip-divider"></div>
    <div class="ozon-tip-channels">
      ${channels.map(c=>{
        const row=bucket.channels[c.key];
        return `
          <div class="ozon-tip-row">
            <span class="ozon-tip-dot" style="background:${c.color}"></span>
            <span class="ozon-tip-name">${c.name}</span>
            <span class="ozon-tip-val"><b>${num(row.orders,0)}</b> 单</span>
            <span class="ozon-tip-sub">${esc(gmvText(row.gmv))}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}
function getSplinePath(points){
  if(!points||!points.length)return "";
  if(points.length===1)return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  let d=`M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for(let i=0;i<points.length-1;i++){
    const p0=points[Math.max(0,i-1)],p1=points[i],p2=points[i+1],p3=points[Math.min(points.length-1,i+2)];
    const cp1x=p1.x+(p2.x-p0.x)/6,cp1y=p1.y+(p2.y-p0.y)/6;
    const cp2x=p2.x-(p3.x-p1.x)/6,cp2y=p2.y-(p3.y-p1.y)/6;
    d+=` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}
function renderTrendWaveLoader(granularity){
  const host=$("#orderTrend");if(!host)return;
  const count=granularity==="day"?90:12;
  const width=1000,height=360,plotLeft=46,plotRight=954,plotTop=20,plotBottom=300,plotHeight=plotBottom-plotTop;
  const availWidth=plotRight-plotLeft;
  const points=Array.from({length:count},(_,i)=>{
    const x=count>1?plotLeft+i*(availWidth/(count-1)):plotLeft+availWidth/2;
    const waveH=45+Math.sin(i*0.6)*30+((i%3)*15);
    const y=plotBottom-waveH;
    return {x,y};
  });
  const lineD=getSplinePath(points);
  const areaD=points.length>1?`${lineD} L ${points[points.length-1].x.toFixed(1)} ${plotBottom} L ${points[0].x.toFixed(1)} ${plotBottom} Z`:"";
  const ticks=[0,.5,1].map(part=>{
    const y=plotBottom-plotHeight*part;
    return `<line x1="${plotLeft}" y1="${y}" x2="${plotRight}" y2="${y}"/>`;
  }).join("");
  const defs=[
    `<linearGradient id="ozon-wave-grad" x1="0" y1="0" x2="0" y2="1">
       <stop offset="0%" stop-color="#005BFF" stop-opacity="0.18"/>
       <stop offset="100%" stop-color="#005BFF" stop-opacity="0.00"/>
     </linearGradient>`
  ];
  host.style.width="100%";
  host.innerHTML=`
    <svg class="trend-svg ozon-spline-svg ozon-wave-loading" viewBox="0 0 ${width} ${height}" role="img" aria-label="数据计算加载中...">
      <defs>${defs.join("")}</defs>
      <g class="trend-grid">${ticks}</g>
      ${areaD?`<path class="ozon-area-path ozon-pulse" d="${areaD}" fill="url(#ozon-wave-grad)"/>`:""}
      ${lineD?`<path class="ozon-line-path ozon-pulse" d="${lineD}" fill="none" stroke="#005BFF" stroke-width="2.5" stroke-dasharray="6 4"/>`:""}
    </svg>
    <div class="ozon-tooltip hidden" role="status"></div>
  `;
}
function renderOrderTrend(data){
  const host=$("#orderTrend"),buckets=data.buckets||[],count=buckets.length;
  const width=1000,height=360,plotLeft=46,plotRight=954,plotTop=20,plotBottom=300,plotHeight=plotBottom-plotTop;
  const availWidth=plotRight-plotLeft;
  const max=Math.max(1,...buckets.map(row=>row.orders));

  const points=buckets.map((b,i)=>{
    const x=count>1?plotLeft+i*(availWidth/(count-1)):plotLeft+availWidth/2;
    const y=plotBottom-(b.orders/max)*plotHeight;
    return {x,y,bucket:b,index:i};
  });

  const lineD=getSplinePath(points);
  const areaD=points.length>1?`${lineD} L ${points[points.length-1].x.toFixed(1)} ${plotBottom} L ${points[0].x.toFixed(1)} ${plotBottom} Z`:"";

  const ticks=[0,.5,1].map(part=>{
    const y=plotBottom-plotHeight*part,value=Math.ceil(max*part);
    return `<line x1="${plotLeft}" y1="${y}" x2="${plotRight}" y2="${y}"/><text x="${plotRight+10}" y="${y+4}" text-anchor="start">${value}</text>`;
  }).join("");

  const defs=[
    `<linearGradient id="ozon-area-grad" x1="0" y1="0" x2="0" y2="1">
       <stop offset="0%" stop-color="#005BFF" stop-opacity="0.22"/>
       <stop offset="70%" stop-color="#005BFF" stop-opacity="0.04"/>
       <stop offset="100%" stop-color="#005BFF" stop-opacity="0.00"/>
     </linearGradient>`
  ];

  const showDots=count<=32;
  const dotsHtml=points.map(pt=>`<circle class="ozon-dot" cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="3.5" fill="#FFFFFF" stroke="#005BFF" stroke-width="2" data-point="${pt.index}" role="img" aria-label="${esc(pt.bucket.from)}，订单${pt.bucket.orders}单"/>`).join("");

  const stepLabel=count>30?Math.ceil(count/7):1;
  const labelsHtml=points.map((pt,i)=>{
    const show=count>30?(i%stepLabel===0||i===count-1):true;
    if(!show)return "";
    const label=data.granularity==="day"?pt.bucket.from.slice(5):data.granularity==="month"?pt.bucket.from.slice(0,7):pt.bucket.from.slice(5);
    return `<text class="ozon-x" x="${pt.x.toFixed(1)}" y="332" text-anchor="middle">${esc(label)}</text>`;
  }).join("");

  const hitWidth=availWidth/Math.max(1,count);
  const hitsHtml=points.map(pt=>`<rect class="ozon-hit" x="${(pt.x-hitWidth/2).toFixed(1)}" y="${plotTop}" width="${hitWidth.toFixed(1)}" height="${plotHeight+36}" data-bucket="${pt.index}"/>`).join("");

  host.style.width="100%";
  host.innerHTML=`
    <svg class="trend-svg ozon-spline-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="有效订单量趋势平滑折线图">
      <defs>${defs.join("")}</defs>
      <g class="trend-grid">${ticks}</g>
      ${areaD?`<path class="ozon-area-path" d="${areaD}" fill="url(#ozon-area-grad)"/>`:""}
      ${lineD?`<path class="ozon-line-path" d="${lineD}" fill="none" stroke="#005BFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`:""}
      <line id="ozonCrosshair" class="ozon-crosshair hidden" x1="0" y1="${plotTop}" x2="0" y2="${plotBottom}"/>
      <g class="ozon-dots ${showDots?'':'hidden-dots'}">${dotsHtml}</g>
      <circle id="ozonActiveDot" class="ozon-active-dot hidden" cx="0" cy="0" r="5" fill="#005BFF" stroke="#FFFFFF" stroke-width="2.5"/>
      <g class="ozon-labels">${labelsHtml}</g>
      <g class="ozon-hits">${hitsHtml}</g>
    </svg>
    <div class="ozon-tooltip hidden" role="status"></div>
  `;

  const tooltip=host.querySelector(".ozon-tooltip");
  const crosshair=host.querySelector("#ozonCrosshair");
  const activeDot=host.querySelector("#ozonActiveDot");

  const showPoint=(index)=>{
    if(index<0||index>=points.length)return;
    const pt=points[index];
    tooltip.innerHTML=trendTip(pt.bucket);
    crosshair.setAttribute("x1",pt.x.toFixed(1));
    crosshair.setAttribute("x2",pt.x.toFixed(1));
    crosshair.classList.remove("hidden");
    activeDot.setAttribute("cx",pt.x.toFixed(1));
    activeDot.setAttribute("cy",pt.y.toFixed(1));
    activeDot.classList.remove("hidden");

    const stage=host.getBoundingClientRect();
    const svgEl=host.querySelector("svg");
    const svgRect=svgEl.getBoundingClientRect();
    const scale=svgRect.width/width;
    const clientX=svgRect.left+pt.x*scale;
    const cursorX=clientX-stage.left;
    const tipWidth=240;

    let targetLeft;
    if(cursorX<=stage.width*0.55){
      targetLeft=cursorX+18;
    }else{
      targetLeft=cursorX-tipWidth-18;
    }
    tooltip.style.left=`${Math.min(Math.max(8,targetLeft),stage.width-tipWidth-8)}px`;
    tooltip.classList.remove("hidden");
  };

  const hide=()=>{
    tooltip.classList.add("hidden");
    crosshair.classList.add("hidden");
    activeDot.classList.add("hidden");
  };

  host.onpointermove=e=>{
    const hit=e.target.closest("[data-bucket]");
    if(hit) showPoint(Number(hit.dataset.bucket));
  };
  host.onpointerleave=hide;
  host.querySelectorAll("[data-point]").forEach(dot=>{
    dot.onfocus=()=>showPoint(Number(dot.dataset.point));
    dot.onblur=hide;
  });

  const insightsHost=$("#trendInsights");
  if(insightsHost&&buckets.length>0){
    const maxBucket=buckets.reduce((max,b)=>b.orders>(max?.orders||0)?b:max,buckets[0]);
    const peakOrders=maxBucket?maxBucket.orders:0;
    const peakDate=maxBucket?(data.granularity==="day"?maxBucket.from.slice(5):maxBucket.from.slice(5)+" ~ "+maxBucket.to.slice(5)):"—";

    const nonZeroBuckets=buckets.filter(b=>b.orders>0);
    const totalOrders=buckets.reduce((sum,b)=>sum+b.orders,0);
    const avgCount=nonZeroBuckets.length||buckets.length||1;
    const avgOrders=Math.round(totalOrders/avgCount);
    const avgLabel=data.granularity==="day"?"日均":data.granularity==="week"?"周均":"月均";

    const latestBucket=buckets[buckets.length-1];
    const prevBucket=buckets.length>1?buckets[buckets.length-2]:null;
    const latestOrders=latestBucket?latestBucket.orders:0;

    let displayOrders=latestOrders;
    let cardTitle="最新单量";
    let growthText="最新一期";
    let growthClass="";
    let subNote="";

    if(latestOrders===0&&prevBucket&&prevBucket.orders>0){
      const prevPrevBucket=buckets.length>2?buckets[buckets.length-3]:null;
      const compGrowth=(prevPrevBucket&&prevPrevBucket.orders>0)
        ?Math.round(((prevBucket.orders-prevPrevBucket.orders)/prevPrevBucket.orders)*100)
        :null;
      displayOrders=prevBucket.orders;
      cardTitle=data.granularity==="week"?"上周单量":data.granularity==="month"?"上月单量":"昨日单量";
      growthText=compGrowth===null?"完整周期":(compGrowth>=0?`+${compGrowth}% 环比`:`${compGrowth}% 环比`);
      growthClass=compGrowth===null?"":(compGrowth>=0?"trend-up":"trend-down");
      subNote=`本期(${latestBucket.from.slice(5)}) 进行中`;
    }else if(prevBucket&&prevBucket.orders>0){
      const growth=Math.round(((latestOrders-prevBucket.orders)/prevBucket.orders)*100);
      growthText=growth>=0?`+${growth}% 环比`:`${growth}% 环比`;
      growthClass=growth>=0?"trend-up":"trend-down";
      subNote=data.granularity==="day"?"较前一日":data.granularity==="week"?"较前一周":"较前一月";
    }

    insightsHost.innerHTML=`
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="flame" size="14" stroke-width="1.8"></morph-icon>
          <span>最高峰值</span>
        </div>
        <strong>${num(peakOrders,0)}<small>单</small></strong>
        <span class="trend-insight-foot">${esc(peakDate)}</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="barChart" size="14" stroke-width="1.8"></morph-icon>
          <span>周期均值</span>
        </div>
        <strong>${num(avgOrders,0)}<small>单/${avgLabel}</small></strong>
        <span class="trend-insight-foot">共 ${nonZeroBuckets.length} 个有单${avgLabel.slice(0,1)}</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="trendingUp" size="14" stroke-width="1.8"></morph-icon>
          <span>${esc(cardTitle)}</span>
        </div>
        <strong>${num(displayOrders,0)}<small>单</small></strong>
        <span class="trend-insight-foot ${growthClass}">
          ${esc(growthText)}
          ${subNote?`<span class="trend-insight-sub">${esc(subNote)}</span>`:""}
        </span>
      </div>
    `;
  }
}
function renderOverviewPanels(data){
  const totalOrders=Math.max(1,data.totals.orders||1);
  const channels=data.channels||[];
  $("#channelGrid").innerHTML=channels.map(r=>{
    const percent=Math.min(100,Math.round((r.orders/totalOrders)*100));
    const channelClass=r.channel==="FBP"?"channel-fbp":r.channel==="realFBS"?"channel-fbs":"channel-whd";
    return `<div class="channel-card"><div class="channel-card-top"><div class="channel-card-brand">${channelTag(r.channel)}<span class="channel-share-pct">订单占比 <b>${percent}</b>%</span></div><div class="channel-track-bar"><div class="channel-track-fill ${channelClass}" style="width:${percent}%"></div></div></div><div class="channel-card-metrics"><div class="channel-metric-cell"><span class="cell-label">有效订单</span><strong class="cell-val">${num(r.orders,0)}<small>单</small></strong></div><div class="channel-metric-cell"><span class="cell-label">有效货件</span><strong class="cell-val">${num(r.pieces,0)}<small>件</small></strong></div><div class="channel-metric-cell risk"><span class="cell-label">发货后取消</span><strong class="cell-val ${r.cancelled_pieces>0?'has-risk':''}">${num(r.cancelled_pieces||0,0)}<small>件</small></strong></div></div></div>`;
  }).join("")||'<div class="overview-empty">暂无渠道数据</div>';

  $("#overviewTimeliness").innerHTML=data.timeliness.map(row=>{
    const ship=row.ship_sample_insufficient?"数据不足":hours(row.p50_ship_hours);
    const delivery=row.delivery_sample_insufficient?"数据不足":hours(row.p50_delivery_hours);
    const p90=row.delivery_sample_insufficient?"数据不足":hours(row.p90_delivery_hours);
    return `<div class="overview-timing-card"><div class="timing-card-header">${channelTag(row.channel)}</div><div class="timing-chips"><div class="timing-chip"><span class="chip-label">发货 P50</span><strong class="chip-val">${ship}</strong></div><div class="timing-chip"><span class="chip-label">配送 P50</span><strong class="chip-val">${delivery}</strong></div><div class="timing-chip"><span class="chip-label">配送 P90</span><strong class="chip-val">${p90}</strong></div></div></div>`;
  }).join("")||'<div class="overview-empty">暂无时效数据</div>';

  $("#overviewTopProducts").innerHTML=data.top_products.map((row,index)=>{
    const rankClass=index===0?"rank-gold":index===1?"rank-silver":index===2?"rank-bronze":"rank-normal";
    return `<div class="overview-product-item"><span class="overview-rank ${rankClass}">${index+1}</span><div class="product-info"><strong class="product-name" title="${esc(row.name)}">${esc(row.name)}</strong></div><div class="product-stats"><span class="stat-badge pieces"><b>${num(row.pieces,0)}</b>件</span><span class="stat-badge orders">${num(row.orders,0)}单</span><span class="stat-badge cancel ${row.cancel_rate>0.05?'is-warning':''}">取消 ${pct(row.cancel_rate)}</span></div></div>`;
  }).join("")||'<div class="overview-empty">所选范围暂无商品数据</div>';
}

function summary(id, cards) {
  $(`#${id}Summary`).innerHTML=cards.map(c=>`<div class="summary-card"><span class="muted">${esc(c[0])}</span><strong>${esc(c[1])}</strong>${c[2]?`<small class="muted">${esc(c[2])}</small>`:""}</div>`).join("");
}
function renderDataThrough(raw){const el=$("#dataThrough");if(!el)return;const timeStr=raw?(raw.length===10?raw:bj(raw)):"暂无";el.innerHTML=`<span class="pulse-dot" aria-hidden="true"></span><span class="data-through-label">数据截止</span><span class="data-through-time">${esc(timeStr)}</span>`}
function pager(name, data, loader) {
  const pages=Math.max(1,Math.ceil(data.total/data.size));
  $(`#${name}Info`).textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 条`;
  $(`#${name}Prev`).disabled=data.page<=1; $(`#${name}Next`).disabled=data.page>=pages;
  $(`#${name}Prev`).onclick=()=>{state.pages[name]--;loader()};
  $(`#${name}Next`).onclick=()=>{state.pages[name]++;loader()};
  renderDataThrough(data.data_through);
}

async function api(url, options={}) {
  if(options.method && options.method!=="GET") options.headers={...(options.headers||{}),"X-CSRF-Token":state.csrf};
  const response = await fetch(url, options);
  if (response.status === 401) { showLogin(); throw new Error("请重新登录"); }
  if (!response.ok) { const body = await response.json().catch(()=>({})); throw new Error(body.detail || `请求失败 ${response.status}`); }
  return response.headers.get("content-type")?.includes("json") ? response.json() : response;
}
let toastTimer = null, toastLeaveTimer = null;
function toast(message, error=false) {
  if (toastTimer) clearTimeout(toastTimer);
  if (toastLeaveTimer) clearTimeout(toastLeaveTimer);
  const notice = $("#notice");
  if (!notice) return;
  const icon = error ? "alertCircle" : (message.includes("复制") ? "copy" : "check");
  const toastEl = document.createElement("div");
  toastEl.className = `toast ${error ? 'error' : 'success'}`;
  toastEl.innerHTML = `<span class="toast-icon"><morph-icon icon="${icon}" size="16" stroke-width="2.2" spring="snappy"></morph-icon></span><span>${esc(message)}</span>`;
  notice.replaceChildren(toastEl);
  const duration = error ? 2600 : 1800;
  toastTimer = setTimeout(() => {
    toastEl.classList.add("is-leaving");
    toastLeaveTimer = setTimeout(() => {
      if (notice.contains(toastEl)) toastEl.remove();
    }, 200);
  }, duration);
}
function showLogin(){ $("#shell").classList.add("hidden"); $("#login").classList.remove("hidden"); }
function showShell(){ $("#login").classList.add("hidden"); $("#shell").classList.remove("hidden"); }

async function loadShops() {
  state.shops = await api("/api/shops");
  const options = state.shops.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join("");
  const importShop=$("#importShop").value;
  const shops=[{id:0,name:"两店铺合并"},...state.shops];
  $("#shopOptions").innerHTML=shops.map(s=>`<button type="button" role="option" data-shop="${s.id}" aria-selected="${s.id===state.shop}">${esc(s.name)}</button>`).join("");
  $("#shopPickerValue").textContent=shops.find(s=>s.id===state.shop)?.name||"两店铺合并";
  $("#importShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#importShop").value = importShop;
  returnSelects.importShop?.render();
  $("#shop1").value = state.shops[0].name; $("#shop2").value = state.shops[1].name;
}
let overviewReqId = 0, trendReqId = 0;
async function loadTrend() {
  const reqId = ++trendReqId;
  const data = await api(`/api/order-trend?shop_id=${state.shop}&granularity=${state.overviewGranularity}`);
  if (reqId !== trendReqId) return;
  renderOrderTrend(data);
}
async function loadOverview() {
  const reqId = ++overviewReqId;
  const query = new URLSearchParams({shop_id:state.shop,from:overviewRange.start,to:overviewRange.end});
  const data = await api(`/api/summary?${query}`);
  if (reqId !== overviewReqId) return;
  const t = data.totals;
  $("#totalOrders").textContent=t.orders; $("#totalPieces").textContent=t.pieces;
  $("#cancelOrders").textContent=t.cancelled_orders; $("#cancelRate").textContent=pct(t.cancel_rate);
  renderDataThrough(data.data_through);
  renderOverviewPanels(data);
}
async function loadOrders() {
  $("#orderList").innerHTML = '<div class="panel order-empty"><morph-icon icon="sync" size="20" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>订单加载中…</span></div>';
  const query = new URLSearchParams({
    shop_id: state.shop,
    channel: $("#channelFilter").value,
    status: state.orderStatus || "",
    q: $("#orderSearch").value,
    page: state.page,
    from: orderRange.start,
    to: orderRange.end
  });
  try {
    const data = await api(`/api/orders?${query}`);
    state.total = data.total;

    if (data.status_counts) {
      const sc = data.status_counts;
      const elAll = $("#orderCountAll"); if (elAll) elAll.textContent = num(sc.all, 0);
      const elPending = $("#orderCountPending"); if (elPending) elPending.textContent = num(sc.pending, 0);
      const elShipping = $("#orderCountShipping"); if (elShipping) elShipping.textContent = num(sc.shipping, 0);
      const elDelivered = $("#orderCountDelivered"); if (elDelivered) elDelivered.textContent = num(sc.delivered, 0);
      const elCancelled = $("#orderCountCancelled"); if (elCancelled) elCancelled.textContent = num(sc.cancelled, 0);
    }

    $("#orderList").innerHTML = data.items.map(o => {
      const first = o.items[0];
      const extra = o.sku_types - 1;
      const cancelTag = o.status_raw === "已取消"
        ? `<span class="order-flag danger">${o.shipped ? "发货后取消" : "发货前取消"}</span>`
        : "";
      const anomalyTag = o.data_anomaly
        ? `<span class="order-flag danger">数据异常</span>`
        : "";
      const tone = o.status_raw === "已取消" || o.data_anomaly ? "danger" : o.status_raw === "已签收" ? "delivered" : /运输|配送|发货|待取件/.test(o.status_raw) ? "shipping" : "pending";
      const statusIcon = o.status_raw === "已取消" || o.data_anomaly ? "alertTriangle" : o.status_raw === "已签收" ? "checkCircle" : /运输|配送|发货|待取件/.test(o.status_raw) ? "truck" : "box";
      const statusClass = `order-status-${tone}`;

      const tCreated = o.created_at ? new Date(o.created_at).getTime() : null;
      const tShipped = o.shipped_at ? new Date(o.shipped_at).getTime() : null;
      const tDelivered = o.delivered_at ? new Date(o.delivered_at).getTime() : null;

      const shipDur = (tCreated && tShipped && tShipped >= tCreated) ? (tShipped - tCreated) / 3600000 : null;
      const deliveryDur = (tShipped && tDelivered && tDelivered >= tShipped) ? (tDelivered - tShipped) / 3600000 : null;

      const stepCreatedClass = "is-completed";
      const stepShippedClass = o.shipped_at ? "is-completed" : /运输|配送|已签收/.test(o.status_raw) ? "is-active" : o.status_raw === "已取消" ? "is-cancelled" : "is-pending";
      const stepDeliveredClass = o.delivered_at || o.status_raw === "已签收" ? "is-completed" : o.status_raw === "已取消" ? "is-cancelled" : "is-pending";

      const product = first ? `
        <div class="order-prod-main">
          <strong class="order-prod-title" title="${esc(first.product_name_raw)}">${esc(first.product_name_raw)}</strong>
          ${first.product_name_raw !== first.product_name_original ? `<span class="order-prod-orig" title="${esc(first.product_name_original)}">${esc(first.product_name_original)}</span>` : ""}
        </div>
        <div class="order-prod-meta">
          <span class="order-meta-chip">SKU <b>${cell(first.sku)}</b></span>
          <span class="order-meta-chip">货号 <b>${cell(first.offer_id)}</b></span>
          <span class="order-meta-chip qty">× <b>${num(first.quantity, 0)}</b></span>
          ${extra > 0 ? `<span class="order-meta-extra">+${extra} 种其他商品</span>` : ""}
        </div>
      ` : `<div class="order-prod-main"><strong>商品信息暂无</strong></div>`;

      return `
        <details class="order-card order-${tone}">
          <summary aria-label="订单 ${esc(o.posting_number)}，${esc(o.status_raw)}，点击展开详情">
            <div class="order-identity">
              <div class="order-id-row">
                <strong class="order-num copyable" data-copy="${esc(o.posting_number)}" title="点击复制订单号">
                  <morph-icon icon="copy" size="13" stroke-width="2"></morph-icon>
                  ${esc(o.posting_number)}
                </strong>
              </div>
              <div class="order-tags-row">
                <span class="order-shop-badge">${esc(o.shop_name)}</span>
                ${channelTag(o.channel)}
                ${cancelTag}
                ${anomalyTag}
              </div>
            </div>

            <div class="order-product-summary">
              ${product}
              ${o.cancel_reason_raw ? `<div class="order-cancel-reason-chip" title="${esc(o.cancel_reason_raw)}"><morph-icon icon="alertTriangle" size="12" stroke-width="2"></morph-icon><span>${esc(o.cancel_reason_raw)}</span></div>` : ""}
            </div>

            <div class="order-status">
              <div class="order-status-badge ${statusClass}">
                <morph-icon icon="${statusIcon}" size="13" stroke-width="2"></morph-icon>
                <span>${esc(o.status_raw)}</span>
              </div>
              <div class="order-time-stamp">
                <morph-icon icon="clock" size="12" stroke-width="1.8"></morph-icon>
                <span>${bj(o.created_at)}</span>
              </div>
              <small class="order-sku-count">${num(o.sku_types, 0)} 种 SKU · 共 ${num(o.pieces, 0)} 件</small>
            </div>

            <div class="order-amount">
              <strong class="order-price-val">${money(o.amount_original, o.amount_currency)}</strong>
              <div class="order-expand-hint">
                <span>展开详情</span>
                <morph-icon class="order-chevron" icon="chevronDown" size="14" spring="snappy" stroke-width="2"></morph-icon>
              </div>
            </div>
          </summary>

          <div class="order-details">
            <div class="order-time-grid">
              <div class="milestone-box ${stepCreatedClass}">
                <div class="milestone-box-head">
                  <morph-icon icon="shoppingBag" size="14" stroke-width="2"></morph-icon>
                  <span>创建时间</span>
                </div>
                <strong>${bj(o.created_at)}</strong>
                <small class="milestone-note">订单已生成</small>
              </div>
              <div class="milestone-box ${stepShippedClass}">
                <div class="milestone-box-head">
                  <morph-icon icon="truck" size="14" stroke-width="2"></morph-icon>
                  <span>实际发货时间</span>
                </div>
                <strong>${bj(o.shipped_at)}</strong>
                <small class="milestone-note">${shipDur ? `发货耗时 ${hours(shipDur)}` : (o.shipped_at ? "已发货" : o.status_raw === "已取消" ? "取消未发货" : "等待发运")}</small>
              </div>
              <div class="milestone-box ${stepDeliveredClass}">
                <div class="milestone-box-head">
                  <morph-icon icon="checkCircle" size="14" stroke-width="2"></morph-icon>
                  <span>实际签收时间</span>
                </div>
                <strong>${bj(o.delivered_at)}</strong>
                <small class="milestone-note">${deliveryDur ? `配送耗时 ${hours(deliveryDur)}` : (o.delivered_at ? "已签收" : o.status_raw === "已取消" ? "订单已取消" : "配送中")}</small>
              </div>
            </div>

            <div class="order-detail-products">
              <div class="order-detail-products-head">
                <span>商品明细 (${num(o.sku_types, 0)} 种 SKU · 共 ${num(o.pieces, 0)} 件)</span>
                <span>单价与小计</span>
              </div>
              ${o.items.map(i => `
                <div class="order-detail-product">
                  <div class="product-info-col">
                    <strong class="product-title">${esc(i.product_name_raw)}</strong>
                    ${i.product_name_raw !== i.product_name_original ? `<small class="product-orig-title">原始名称：${esc(i.product_name_original)}</small>` : ""}
                    <div class="product-meta-chips">
                      <span class="product-meta-chip">SKU <b>${cell(i.sku)}</b></span>
                      <span class="product-meta-chip">货号 <b>${cell(i.offer_id)}</b></span>
                    </div>
                  </div>
                  <div class="product-qty-col">
                    <span class="product-qty-badge">× ${num(i.quantity, 0)}</span>
                  </div>
                  <div class="product-price-col">
                    <strong class="product-unit-price">${i.unit_price == null ? "单价暂无" : `${num(i.unit_price)} ${esc(i.price_currency || "")}`}</strong>
                    ${i.unit_price != null && i.quantity > 1 ? `<small class="product-total-price">小计 ${num(i.unit_price * i.quantity)} ${esc(i.price_currency || "")}</small>` : ""}
                  </div>
                </div>
              `).join("") || '<div class="muted">商品明细暂无</div>'}
            </div>

            <div class="order-detail-foot">
              <div class="order-foot-meta">
                <div class="order-foot-total">
                  <span class="muted">订单合计：</span>
                  <strong class="order-total-sum">${money(o.amount_original, o.amount_currency)}</strong>
                  <span class="order-total-pieces">（共 ${num(o.pieces, 0)} 件）</span>
                </div>
                ${o.cancel_reason_raw ? `<div class="order-alert-box danger"><morph-icon icon="alertTriangle" size="14" stroke-width="2"></morph-icon><span><strong>取消原因：</strong>${esc(o.cancel_reason_raw)}</span></div>` : ""}
                ${o.data_anomaly ? `<div class="order-alert-box warning"><morph-icon icon="alertOctagon" size="14" stroke-width="2"></morph-icon><span><strong>数据异常：</strong>订单实际时效字段与状态不一致，请核对原始数据。</span></div>` : ""}
              </div>
            </div>
          </div>
        </details>
      `;
    }).join("") || '<div class="panel order-empty"><morph-icon icon="box" size="24" stroke-width="1.5"></morph-icon><span>当前筛选范围内没有找到符合条件的订单</span></div>';

    const pages = Math.max(1, Math.ceil(data.total / data.size));
    $("#pageInfo").textContent = `第 ${data.page} / ${pages} 页，共 ${data.total} 个订单`;
    $("#prevPage").disabled = state.page <= 1;
    $("#nextPage").disabled = state.page >= pages;
  } catch (error) {
    $("#orderList").innerHTML = `<div class="panel order-empty error"><morph-icon icon="alertTriangle" size="24" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></div>`;
    throw error;
  }
}
async function loadRisk() {
  const query = new URLSearchParams({shop_id: state.shop, from: riskRange.start, to: riskRange.end});
  $("#riskRows").innerHTML = '<tr><td colspan="5" class="risk-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>风险数据加载中…</span></td></tr>';
  $("#reasonRows").innerHTML = '<tr><td colspan="5" class="risk-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>取消原因加载中…</span></td></tr>';
  $("#reasonDetails").classList.add("hidden");
  try {
    const [data, reasons] = await Promise.all([api(`/api/risk?${query}`), api(`/api/risk/reasons?${query}`)]);
    const s = data.summary;

    $("#riskSummary").innerHTML = renderAnalysisCards([
      {
        icon: "package",
        label: "有效货件数",
        count: `${num(s.valid, 0)} 件`,
        rate: null,
        rateTone: "neutral",
        note: "当前筛选范围内的全部有效货件"
      },
      {
        icon: "alertTriangle",
        label: "发货后取消",
        count: s.valid ? `${num(s.cancelled, 0)} 件` : "数据不足",
        rate: s.valid ? `${pct(s.cancelled_rate)} 取消率` : null,
        rateTone: (s.cancelled_rate || 0) >= 0.15 ? "danger" : (s.cancelled_rate || 0) >= 0.05 ? "warning" : "safe",
        note: "发货后在途或配送阶段取消"
      },
      {
        icon: "userX",
        label: "买家未取货",
        count: s.valid ? `${num(s.unclaimed, 0)} 件` : "数据不足",
        rate: s.valid ? `${pct(s.unclaimed_rate)} 发生率` : null,
        rateTone: (s.unclaimed_rate || 0) >= 0.05 ? "warning" : "neutral",
        note: "5 种买家原因导致的未完成收货"
      },
      {
        icon: "shieldAlert",
        label: "通关失败",
        count: s.valid ? `${num(s.customs, 0)} 件` : "数据不足",
        rate: s.valid ? `${pct(s.customs_rate)} 拦截率` : null,
        rateTone: (s.customs_rate || 0) >= 0.02 ? "danger" : "neutral",
        note: "海关查验未通过导致的退运拦截"
      }
    ]);

    riskItems = data.items;
    renderRiskItems();

    $("#reasonRows").innerHTML = reasons.items.map(r => `
      <tr>
        <td class="risk-reason">
          <div class="risk-reason-main">
            <button class="link-button reason-link-btn" data-reason="${esc(r.reason_raw)}" title="点击展开此原因关联订单">
              <morph-icon icon="alertTriangle" size="13" stroke-width="2"></morph-icon>
              <span>${esc(r.reason_name)}</span>
            </button>
            <span class="reason-raw-text">${esc(r.reason_raw)}</span>
          </div>
        </td>
        ${reasonStatCell("综合", r.total)}
        ${reasonStatCell("FBP", r.channels.FBP)}
        ${reasonStatCell("realFBS", r.channels.realFBS)}
        ${reasonStatCell("WHD", r.channels.WHD)}
      </tr>
    `).join("") || '<tr><td colspan="5" class="risk-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前范围内暂无发货后取消原因。</span></td></tr>';
  } catch (error) {
    $("#riskSummary").innerHTML = "";
    $("#riskRows").innerHTML = `<tr><td colspan="5" class="risk-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    $("#reasonRows").innerHTML = `<tr><td colspan="5" class="risk-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
}
function renderRiskItems() {
  const keyword = $("#riskSearch").value.trim().toLocaleLowerCase();
  let items = riskItems;
  if (keyword) {
    items = items.filter(r => `${r.search_text || ""} ${r.product_name || ""}`.toLocaleLowerCase().includes(keyword));
  }
  if (riskHighOnly) {
    items = items.filter(r => (r.total?.cancelled_rate || 0) >= 0.15);
  }
  $("#riskRows").innerHTML = items.map(r => `
    <tr>
      <td class="risk-product">
        <div class="risk-prod-wrap">
          <strong class="risk-prod-title" title="${esc(r.product_name)}">${esc(r.product_name || "商品名称暂无")}</strong>
          <div class="risk-prod-meta">
            <span class="risk-shop-badge">${esc(r.shop_name)}</span>
            ${r.primary_offer_id
              ? `<span class="risk-offer-badge copyable" data-copy="${esc(r.primary_offer_id)}" title="点击复制主货号"><morph-icon icon="gitMerge" size="11" stroke-width="2"></morph-icon>主货号 <b>${esc(r.primary_offer_id)}</b></span><span class="risk-member-badge">${num(r.member_count, 0)} 个成员</span>`
              : `<span class="risk-sku-badge"><morph-icon icon="tag" size="11" stroke-width="1.8"></morph-icon>SKU <b>${cell(r.sku)}</b></span>`
            }
          </div>
        </div>
      </td>
      ${riskStatCell("综合", r.total)}
      ${riskStatCell("FBP", r.channels.FBP)}
      ${riskStatCell("realFBS", r.channels.realFBS)}
      ${riskStatCell("WHD", r.channels.WHD)}
    </tr>
  `).join("") || `<tr><td colspan="5" class="risk-empty"><morph-icon icon="shieldAlert" size="22" stroke-width="1.5"></morph-icon><span>${keyword || riskHighOnly ? "没有匹配的SKU或高危商品" : "当前范围内暂无有效货件"}</span></td></tr>`;
}
function riskStatCell(label, s) {
  if (!s || !s.valid) {
    return `
      <td class="risk-stat no-sample" data-label="${label}">
        <strong class="risk-cell-title">${label}</strong>
        <div class="risk-cell-empty">
          <span>— 无有效样本 —</span>
        </div>
      </td>
    `;
  }
  const cancelRate = s.cancelled_rate || 0;
  const rateTone = cancelRate >= 0.15 ? "danger" : cancelRate >= 0.05 ? "warning" : "safe";
  const toneIcon = cancelRate >= 0.15 ? "alertTriangle" : cancelRate >= 0.05 ? "alertCircle" : "check";

  return `
    <td class="risk-stat tone-${rateTone}" data-label="${label}">
      <strong class="risk-cell-title">${label}</strong>
      <div class="risk-cell-wrap">
        <div class="risk-cell-head">
          <span class="risk-valid-count">有效 <b>${num(s.valid, 0)}</b> 件</span>
        </div>
        <div class="risk-pill-main tone-${rateTone}">
          <morph-icon icon="${toneIcon}" size="11" stroke-width="2.2"></morph-icon>
          <strong>${pct(s.cancelled_rate)}</strong>
          <small>(${num(s.cancelled, 0)}件)</small>
        </div>
        <div class="risk-cell-subtags">
          <span class="risk-sub-chip ${s.unclaimed > 0 ? 'highlight' : ''}" title="买家未取货率：${pct(s.unclaimed_rate)} (${num(s.unclaimed, 0)}件)">
            <span class="sub-label">未取货</span>
            <b>${pct(s.unclaimed_rate)}</b>
          </span>
          <span class="risk-sub-chip ${s.customs > 0 ? 'danger-highlight' : ''}" title="通关失败率：${pct(s.customs_rate)} (${num(s.customs, 0)}件)">
            <span class="sub-label">通关失败</span>
            <b>${pct(s.customs_rate)}</b>
          </span>
        </div>
      </div>
    </td>
  `;
}
function reasonStatCell(label, s) {
  if (!s || (!s.orders && !s.pieces)) {
    return `
      <td class="reason-stat no-sample" data-label="${label}">
        <strong class="risk-cell-title">${label}</strong>
        <span class="reason-no-record">—</span>
      </td>
    `;
  }
  return `
    <td class="reason-stat" data-label="${label}">
      <strong class="risk-cell-title">${label}</strong>
      <div class="reason-cell-wrap">
        <span class="reason-pill-orders"><b>${num(s.orders, 0)}</b> 单</span>
        <span class="reason-pill-pieces"><b>${num(s.pieces, 0)}</b> 件</span>
      </div>
    </td>
  `;
}
async function loadTimeliness() {
  const query = new URLSearchParams({
    shop_id: state.shop,
    page: state.pages.timeliness,
    q: $("#timelinessSearch").value,
    from: timelinessRange.start,
    to: timelinessRange.end
  });
  $("#timelinessGroupRows").innerHTML = '<tr><td colspan="4" class="timeliness-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>时效统计加载中…</span></td></tr>';
  $("#timelinessRows").innerHTML = '<tr><td colspan="5" class="timeliness-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>订单明细加载中…</span></td></tr>';
  try {
    const data = await api(`/api/timeliness?${query}`), s = data.summary;
    $("#timelinessSummary").innerHTML = renderAnalysisCards([
      {
        icon: "shoppingBag",
        label: "有效订单数",
        count: `${num(s.orders, 0)} 单`,
        badge: "全量统计",
        tone: "neutral",
        note: "当前店铺与筛选时间范围内有效订单"
      },
      {
        icon: "box",
        label: "发货有效样本数",
        count: `${num(s.ship_samples, 0)} 单`,
        badge: s.orders ? `${pct(s.ship_samples / s.orders)} 样本率` : null,
        tone: "safe",
        note: "含真实且有效的实际发货时间"
      },
      {
        icon: "clock",
        label: "发货时效 P50",
        count: s.ship_samples ? hours(s.p50_ship_hours) : "数据不足",
        badge: s.ship_samples ? "中位数" : null,
        tone: s.ship_samples && s.p50_ship_hours <= 24 ? "safe" : s.ship_samples && s.p50_ship_hours <= 48 ? "warning" : "danger",
        note: "50% 的订单在此时间内完成出库发货"
      },
      {
        icon: "truck",
        label: "配送时效 P50",
        count: s.delivery_samples ? hours(s.p50_delivery_hours) : "数据不足",
        badge: s.delivery_samples ? "中位数" : null,
        tone: "neutral",
        note: "50% 的订单在发货后此时间内完成派送签收"
      }
    ]);

    $("#timelinessGroupRows").innerHTML = data.groups.map(r => `
      <tr>
        <td class="timeliness-identity" data-label="店铺／渠道">
          <div class="timeliness-ident-wrap">
            <strong class="timeliness-shop-name">${esc(r.shop_name)}</strong>
            ${channelTag(r.channel)}
          </div>
        </td>
        <td class="timeliness-completeness" data-label="订单与完整率">
          <div class="timeliness-complete-wrap">
            <span class="complete-total">有效订单 <b>${num(r.orders, 0)}</b></span>
            <div class="complete-chips">
              <span class="complete-chip" title="创建完整率 ${pct(r.created_completeness)}">
                <span class="sub-label">创建</span>
                <b>${pct(r.created_completeness)}</b>
              </span>
              <span class="complete-chip ${r.shipped_completeness < 0.8 ? 'warning' : ''}" title="发货完整率 ${pct(r.shipped_completeness)}">
                <span class="sub-label">发货</span>
                <b>${pct(r.shipped_completeness)}</b>
              </span>
              <span class="complete-chip ${r.delivered_completeness < 0.8 ? 'warning' : ''}" title="签收完整率 ${pct(r.delivered_completeness)}">
                <span class="sub-label">签收</span>
                <b>${pct(r.delivered_completeness)}</b>
              </span>
            </div>
          </div>
        </td>
        ${timelinessStatCell("发货时效", r.ship_samples, r.ship_sample_insufficient, r.p50_ship_hours, r.avg_ship_hours, r.p90_ship_hours)}
        ${timelinessStatCell("配送时效", r.delivery_samples, r.delivery_sample_insufficient, r.p50_delivery_hours, r.avg_delivery_hours, r.p90_delivery_hours)}
      </tr>
    `).join("") || '<tr><td colspan="4" class="timeliness-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前范围内暂无有效订单。</span></td></tr>';

    $("#timelinessRows").innerHTML = data.items.map(r => `
      <tr>
        <td data-label="店铺／渠道">
          <div class="timeliness-row-shop">
            <strong class="timeliness-shop-badge">${esc(r.shop_name)}</strong>
            ${channelTag(r.channel)}
          </div>
        </td>
        <td data-label="订单号">
          <strong class="copyable" data-copy="${esc(r.posting_number)}" title="点击复制订单号">
            <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
            ${esc(r.posting_number)}
          </strong>
        </td>
        <td data-label="创建时间" class="timeliness-cell-time">${bj(r.created_at)}</td>
        ${timelinessDetailCell("发货时间／发货耗时", r.shipped_at, r.ship_hours, r.ship_anomaly, "ship")}
        ${timelinessDetailCell("签收时间／配送耗时", r.delivered_at, r.delivery_hours, r.delivery_anomaly, "delivery")}
      </tr>
    `).join("") || '<tr><td colspan="5" class="timeliness-empty"><morph-icon icon="truck" size="20" stroke-width="1.5"></morph-icon><span>没有匹配的订单时效明细。</span></td></tr>';

    pager("timeliness", data, loadTimeliness);
  } catch (error) {
    $("#timelinessSummary").innerHTML = "";
    $("#timelinessGroupRows").innerHTML = `<tr><td colspan="4" class="timeliness-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    $("#timelinessRows").innerHTML = `<tr><td colspan="5" class="timeliness-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
}
function timelinessStatCell(label, samples, insufficient, p50, average, p90) {
  if (!samples) {
    return `
      <td class="timeliness-stat no-sample" data-label="${label}">
        <strong class="timeliness-cell-title">${label}</strong>
        <div class="timeliness-stat-empty">
          <span>— 数据不足 —</span>
        </div>
      </td>
    `;
  }
  return `
    <td class="timeliness-stat" data-label="${label}">
      <strong class="timeliness-cell-title">${label}</strong>
      <div class="timeliness-stat-wrap">
        <div class="timeliness-p50-row">
          <span class="p50-badge">
            <morph-icon icon="clock" size="12" stroke-width="2.2"></morph-icon>
            <b>P50</b> ${hours(p50)}
          </span>
          <span class="p50-sample-tag ${insufficient ? 'insufficient' : ''}">
            ${insufficient ? '<morph-icon icon="alertTriangle" size="11" stroke-width="2"></morph-icon>样本不足' : `样本 ${num(samples, 0)}`}
          </span>
        </div>
        <div class="timeliness-sub-stats">
          <span class="sub-stat">平均 <b>${hours(average)}</b></span>
          <span class="sub-stat p90-stat">P90 <b>${hours(p90)}</b></span>
        </div>
      </div>
    </td>
  `;
}
function timelinessDetailCell(label, value, duration, anomaly, type) {
  if (anomaly) {
    return `
      <td class="timeliness-detail-time" data-label="${label}">
        <div class="time-cell-wrap">
          <strong class="time-cell-dt">${value ? bj(value) : '—'}</strong>
          <span class="time-chip chip-anomaly">
            <morph-icon icon="alertTriangle" size="11" stroke-width="2"></morph-icon>
            数据异常
          </span>
        </div>
      </td>
    `;
  }
  if (!value) {
    return `
      <td class="timeliness-detail-time" data-label="${label}">
        <div class="time-cell-wrap">
          <span class="time-cell-empty">— 暂无实际时间 —</span>
        </div>
      </td>
    `;
  }
  let tone = "normal";
  if (type === "ship") {
    tone = duration != null && duration <= 24 ? "fast" : duration != null && duration <= 48 ? "normal" : "slow";
  } else {
    tone = duration != null && duration <= 120 ? "fast" : "normal";
  }
  return `
    <td class="timeliness-detail-time" data-label="${label}">
      <div class="time-cell-wrap">
        <strong class="time-cell-dt">${bj(value)}</strong>
        <span class="time-chip chip-${tone}">
          <morph-icon icon="${tone === 'fast' ? 'zap' : 'clock'}" size="11" stroke-width="2"></morph-icon>
          ${duration == null ? "数据异常" : `耗时 ${hours(duration)}`}
        </span>
      </div>
    </td>
  `;
}
function rfbsStatusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("approved") || s.includes("accepted") || s.includes("同意") || s.includes("已接收") || s.includes("已批准") || s.includes("完成")) return "safe";
  if (s.includes("rejected") || s.includes("declined") || s.includes("拒绝") || s.includes("争议") || s.includes("dispute")) return "danger";
  if (s.includes("pending") || s.includes("progress") || s.includes("审核") || s.includes("审批") || s.includes("处理中") || s.includes("在途") || s.includes("退回中")) return "warning";
  return "neutral";
}
async function loadReturns() {
  $("#returnsRows").innerHTML = '<tr><td colspan="5" class="return-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>取消明细加载中…</span></td></tr>';
  try {
    const query = new URLSearchParams({
      shop_id: state.shop,
      page: state.pages.returns,
      q: $("#returnsQuery").value,
      from: returnsRange.start,
      to: returnsRange.end
    });
    const data = await api(`/api/returns?${query}`);
    $("#returnsCount").textContent = num(data.total, 0);

    const totalQty = data.summary.shops.reduce((acc, s) => acc + (s.quantity || 0), 0);
    const summaryCards = [
      {
        icon: "xCircle",
        label: "取消总记录数",
        count: `${num(data.summary.records, 0)} 条`,
        badge: "全量取消",
        tone: "danger",
        note: "当前店铺与筛选范围内的取消单量"
      },
      {
        icon: "box",
        label: "取消商品总件数",
        count: `${num(totalQty, 0)} 件`,
        badge: "商品件数",
        tone: "warning",
        note: "所有取消记录中的商品累计件数"
      },
      ...data.summary.shops.map(s => ({
        icon: "shoppingBag",
        label: `${s.shop_name} 取消`,
        count: `${num(s.records, 0)} 条 / ${num(s.quantity, 0)} 件`,
        badge: "分店铺",
        tone: "neutral",
        note: `${s.shop_name} 的取消单量与商品件数`
      }))
    ];

    $("#returnsSummary").innerHTML = renderAnalysisCards(summaryCards);

    $("#returnsRows").innerHTML = data.items.map(r => `
      <tr>
        <td data-label="店铺／时间">
          <div class="return-shop-time">
            <strong class="return-shop-badge">${esc(r.shop_name)}</strong>
            <span class="return-time-text">取消时间：${bj(r.cancelled_at||r.occurred_at)}</span>
            ${deadlineLine(r)}
          </div>
        </td>
        <td data-label="订单号">
          <strong class="copyable" data-copy="${esc(r.posting_number)}" title="点击复制订单号">
            <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
            ${esc(r.posting_number)}
          </strong>
        </td>
        <td class="return-product" data-label="商品信息">
          <div class="return-product-cell">
            <strong class="return-product-title" title="${esc(r.product_name)}">${esc(r.product_name)}</strong>
            <div class="return-sku-chips">
              <span class="return-sku-chip copyable" data-copy="${esc(r.sku)}" title="点击复制 SKU">
                <span class="sub-label">SKU</span> <b>${esc(r.sku)}</b>
              </span>
              <span class="return-sku-chip copyable" data-copy="${esc(r.offer_id)}" title="点击复制货号">
                <span class="sub-label">货号</span> <b>${esc(r.offer_id || '—')}</b>
              </span>
            </div>
          </div>
        </td>
        <td data-label="取消件数">
          <span class="return-qty-badge"><b>${num(r.quantity, 0)}</b> 件</span>
        </td>
        <td data-label="取消原因／状态">
          <div class="return-reason-cell">
            <span class="return-reason-chip" title="${esc(r.reason_raw)}">${esc(r.reason || r.reason_raw || '—')}</span>
            <span class="return-status-sub">${esc(r.status || r.type || '已取消')}</span>
          </div>
        </td>
      </tr>
    `).join("") || '<tr><td colspan="5" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有取消记录。</span></td></tr>';

    pager("returns", data, loadReturns);
  } catch (error) {
    $("#returnsSummary").innerHTML = "";
    $("#returnsRows").innerHTML = `<tr><td colspan="5" class="return-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
}

async function loadRfbsReturns() {
  $("#rfbsReturnsRows").innerHTML = '<tr><td colspan="6" class="return-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>退货明细加载中…</span></td></tr>';
  try {
    const query = new URLSearchParams({
      shop_id: state.shop,
      page: state.pages.rfbsReturns,
      q: $("#rfbsReturnsQuery").value,
      from: returnsRange.start,
      to: returnsRange.end
    });
    const data = await api(`/api/rfbs-returns?${query}`);
    $("#rfbsReturnsCount").textContent = num(data.total, 0);

    const summaryCards = [
      {
        icon: "rotateCcw",
        label: "退货申请总数",
        count: `${num(data.summary.records, 0)} 条`,
        badge: "rFBS 退货",
        tone: "safe",
        note: "包含有效申请编号的退货申请单"
      },
      ...data.summary.shops.map(s => ({
        icon: "shoppingBag",
        label: `${s.shop_name} 退货`,
        count: `${num(s.records, 0)} 条申请`,
        badge: "分店铺",
        tone: "neutral",
        note: `${s.shop_name} 的退货申请记录`
      }))
    ];

    $("#rfbsReturnsSummary").innerHTML = renderAnalysisCards(summaryCards);

    $("#rfbsReturnsRows").innerHTML = data.items.map(r => `
      <tr>
        <td data-label="店铺／申请时间">
          <div class="return-shop-time">
            <strong class="return-shop-badge">${esc(r.shop_name)}</strong>
            <span class="return-time-text">申请时间：${bj(r.created_at)}</span>
            ${deadlineLine(r)}
          </div>
        </td>
        <td data-label="申请编号／订单号">
          <div class="return-ident-cell">
            <strong class="copyable" data-copy="${esc(r.return_number)}" title="点击复制申请编号">
              <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
              ${esc(r.return_number)}
            </strong>
            <span class="return-order-sub copyable" data-copy="${esc(r.posting_number)}" title="点击复制订单号">
              订单 ${esc(r.posting_number)}
            </span>
          </div>
        </td>
        <td class="return-product" data-label="商品信息">
          <div class="return-product-cell">
            <strong class="return-product-title" title="${esc(r.product_name)}">${esc(r.product_name)}</strong>
            <div class="return-sku-chips">
              <span class="return-sku-chip copyable" data-copy="${esc(r.sku)}" title="点击复制 SKU">
                <span class="sub-label">SKU</span> <b>${esc(r.sku)}</b>
              </span>
              <span class="return-sku-chip copyable" data-copy="${esc(r.offer_id)}" title="点击复制货号">
                <span class="sub-label">货号</span> <b>${esc(r.offer_id || '—')}</b>
              </span>
            </div>
          </div>
        </td>
        <td data-label="状态／退款">
          <div class="return-state-cell">
            <span class="return-status-pill tone-${rfbsStatusTone(r.status_raw || r.status_name)}">
              ${esc(r.status_name || r.status_raw || '待处理')}
            </span>
            <small class="return-comp-text">退款金额：<b>${r.refund_amount==null?'—':money(r.refund_amount,r.refund_currency)}</b></small>
            <small class="return-comp-text">${compensationLine(r,'platform_compensation','平台赔偿','RUB')}</small>
            <small class="return-comp-text">${compensationLine(r,'logistics_compensation','物流商赔偿','CNY')}</small>
          </div>
        </td>
        <td data-label="数量／金额">
          <div class="return-qty-money">
            <span class="return-qty-badge"><b>${num(r.quantity, 0)}</b> 件</span>
            <strong class="return-money-text">${money(r.product_amount, r.product_currency)}</strong>
          </div>
        </td>
        <td data-label="原因／退回信息">
          <div class="return-reason-logistics">
            <span class="return-reason-chip" title="${esc(r.reason_raw)}">${esc(r.reason_name || r.reason_raw || '平台未提供原因')}</span>
            <span class="return-logistics-sub">退货方式：${esc(r.return_method || '—')}</span>
            <span class="return-logistics-sub">退件结果：${esc(r.return_result || '—')}</span>
            ${r.buyer_comment_raw ? `
              <details class="return-buyer-bubble">
                <summary><morph-icon icon="messageSquare" size="11" stroke-width="2"></morph-icon> 买家留言原文</summary>
                <p lang="ru">${esc(r.buyer_comment_raw)}</p>
              </details>
            ` : ""}
          </div>
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有退货申请。</span></td></tr>';

    pager("rfbsReturns", data, loadRfbsReturns);
  } catch (error) {
    $("#rfbsReturnsSummary").innerHTML = "";
    $("#rfbsReturnsRows").innerHTML = `<tr><td colspan="6" class="return-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
}

const loadReturnPage = () => Promise.all([loadReturns(), loadRfbsReturns()]);

const nullableBool=value=>value===""?null:value==="true";
const boolSelect=value=>value==null?"":String(Boolean(value));
const localDateTime=value=>{
  if(!value)return "";const date=new Date(value);if(Number.isNaN(date.getTime()))return "";
  const parts=Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(date).filter(p=>p.type!=="literal").map(p=>[p.type,p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
};
const settlementCurrency=shopId=>state.shops.find(shop=>shop.id===Number(shopId))?.settlement_currency||(Number(shopId)===1?"USD":"CNY");
const compensationLine=(row,prefix,label,source)=>{const amount=row[`${prefix}_${source.toLowerCase()}`];if(amount==null)return `${label}：<b>—</b>`;const raw=money(amount,source),converted=row[`${prefix}_converted_amount`],target=row[`${prefix}_converted_currency`];if(row[`${prefix}_missing_rate`])return `${label}：<b>${raw}</b> · 缺少赔偿时点汇率`;if(source===target)return `${label}：<b>${raw}</b>`;return `${label}：<b>${raw} ≈ ${convertedMoney(converted,target)}</b>`};
const compensationConversion=(row,prefix,source)=>{const amount=row?.[`${prefix}_${source.toLowerCase()}`];if(amount==null)return "折算金额：—";if(row[`${prefix}_missing_rate`])return "缺少赔偿时点汇率";const target=row[`${prefix}_converted_currency`],converted=row[`${prefix}_converted_amount`],rates=row[`${prefix}_base_rates`]||{};if(source===target)return `折算金额：${convertedMoney(converted,target)}\n店铺币种相同，无需折算`;const rateText=Object.entries(rates).map(([key,value])=>`${key.replace('_','/')} ${value}`).join("｜");return `折算金额：${convertedMoney(converted,target)}${rateText?`\n采用基础汇率：${rateText}`:""}`};
const deadlineLabels={overdue:"已逾期",due_today:"今日截止",due_soon:"即将截止"};
const deadlineLine=row=>`<span class="complaint-deadline ${esc(row.complaint_deadline_status||'missing')}">投诉截止：${esc(row.complaint_deadline||'—')}${deadlineLabels[row.complaint_deadline_status]?` <b>${deadlineLabels[row.complaint_deadline_status]}</b>`:""}</span>`;
const deadlineText=row=>`投诉截止：${row.complaint_deadline||'—'}${deadlineLabels[row.complaint_deadline_status]?` · ${deadlineLabels[row.complaint_deadline_status]}`:""}`;
function activateExceptionTab(name,focus=false){
  document.querySelectorAll("[data-exception-tab]").forEach(button=>{const active=button.dataset.exceptionTab===name;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus()});
  document.querySelectorAll(".exception-tab").forEach(panel=>{const active=panel.id===`exception-${name}`;panel.classList.toggle("active",active);panel.hidden=!active});
}
async function loadShippingComplaints(){
  $("#shippingComplaintRows").innerHTML='<tr><td colspan="5" class="return-empty">发货未收货投诉加载中…</td></tr>';
  const query=new URLSearchParams({shop_id:state.shop,page:state.pages.shippingComplaints,q:$("#shippingComplaintQuery").value,status:$("#shippingComplaintStatus").value,from:complaintRange.start,to:complaintRange.end});
  const data=await api(`/api/exception-complaints/shipping?${query}`);shippingComplaintItems=data.items;$("#shippingComplaintCount").textContent=num(data.total,0);
  $("#shippingComplaintRows").innerHTML=data.items.map((row,index)=>{const first=row.items[0]||{},quantity=row.items.reduce((sum,item)=>sum+Number(item.quantity||0),0),complaints=row.complaints||[];return `<tr>
    <td data-label="店铺／订单"><strong>${esc(row.shop_name)}</strong><small class="return-order-sub copyable" data-copy="${esc(row.posting_number)}">${esc(row.posting_number)}</small>${row.data_anomaly?'<span class="return-status-pill tone-warning">数据异常</span>':""}</td>
    <td data-label="物流／时间"><strong>${esc(row.tracking_number||'—')}</strong><small>下单 ${bj(row.created_at)}</small><small>发货 ${row.shipped_at?bj(row.shipped_at):'—'}</small><small>取消 ${row.cancelled_at?bj(row.cancelled_at):'—'}</small>${deadlineLine(row)}</td>
    <td data-label="商品信息"><strong title="${esc(first.product_name)}">${esc(first.product_name||'产品名称暂无')}</strong><small>SKU ${esc(first.sku||'—')} · 货号 ${esc(first.offer_id||'—')}</small><small>${num(quantity,0)} 件${row.items.length>1?` · 另有 ${row.items.length-1} 种`:""}</small></td>
    <td data-label="金额／原因"><strong>${row.amount_original==null?'—':money(row.amount_original,row.amount_currency)}</strong><small title="${esc(row.cancel_reason_raw)}">${esc(row.cancel_reason||row.cancel_reason_raw||'原因暂缺')}</small></td>
    <td data-label="投诉记录／操作"><div class="exception-record-list">${complaints.map((c,i)=>`<button type="button" data-edit-shipping="${index}:${i}"><strong>${esc(c.complaint_number)}</strong><small>${c.resolved===1?'已完结':'处理中'} · ${bj(c.complaint_at)}</small></button>`).join("")||'<span>尚未创建投诉</span>'}</div><button type="button" class="rule-act-btn" data-new-shipping="${index}">新建投诉</button></td>
  </tr>`}).join("")||'<tr><td colspan="5" class="return-empty">当前筛选范围内没有候选订单。</td></tr>';
  pager("shippingComplaints",data,loadShippingComplaints);
}
async function loadReceivedDisputes(){
  $("#receivedDisputeRows").innerHTML='<tr><td colspan="5" class="return-empty">已收货纠纷加载中…</td></tr>';
  const query=new URLSearchParams({shop_id:state.shop,page:state.pages.receivedDisputes,q:$("#receivedDisputeQuery").value,status:$("#receivedDisputeStatus").value,from:complaintRange.start,to:complaintRange.end});
  const data=await api(`/api/exception-complaints/received?${query}`);receivedDisputeItems=data.items;$("#receivedDisputeCount").textContent=num(data.total,0);
  $("#receivedDisputeRows").innerHTML=data.items.map((row,index)=>`<tr>
    <td data-label="店铺／申请"><strong>${esc(row.shop_name)}</strong><small>请求创建 ${bj(row.created_at)}</small>${deadlineLine(row)}<small class="copyable" data-copy="${esc(row.return_number)}">${esc(row.return_number)}</small></td>
    <td data-label="订单／商品"><strong class="copyable" data-copy="${esc(row.posting_number)}">${esc(row.posting_number)}</strong><small title="${esc(row.product_name)}">${esc(row.product_name||'产品名称暂无')}</small><small>SKU ${esc(row.sku||'—')} · 货号 ${esc(row.offer_id||'—')}</small></td>
    <td data-label="金额／原因"><strong>${row.product_amount==null?'—':money(row.product_amount,row.product_currency)}</strong><small title="${esc(row.reason_raw)}">${esc(row.reason_name||row.reason_raw||'平台未提供原因')}</small>${row.buyer_comment_raw?`<details><summary>买家原文</summary><p lang="ru">${esc(row.buyer_comment_raw)}</p></details>`:""}</td>
    <td data-label="退款／退货"><strong>${esc(row.refund_type||'—')}</strong><small>退款金额 ${row.refund_amount==null?'—':money(row.refund_amount,row.refund_currency)}</small><small>${compensationLine(row,'platform_compensation','平台赔偿','RUB')}</small><small>${compensationLine(row,'logistics_compensation','物流商赔偿','CNY')}</small><small>退货方式 ${esc(row.return_method||'—')}</small></td>
    <td data-label="处理／操作"><strong>${esc(row.process_status||'—')}</strong><small>处理方式 ${esc(row.handling_method||'—')}</small><small>退件结果 ${esc(row.return_result||'—')}</small><button type="button" class="rule-act-btn" data-edit-received="${index}">编辑</button></td>
  </tr>`).join("")||'<tr><td colspan="5" class="return-empty">当前筛选范围内没有退货申请。</td></tr>';
  pager("receivedDisputes",data,loadReceivedDisputes);
}
const loadExceptionComplaints=()=>Promise.all([loadShippingComplaints(),loadReceivedDisputes()]);
async function loadStock() {
  $("#stockRows").innerHTML='<tr><td colspan="8" class="stock-empty">库存数据加载中…</td></tr>';
  try {const query=new URLSearchParams({shop_id:state.shop,page:state.pages.stock,sku:$("#stockSku").value,offer_id:$("#stockOffer").value,product_name:$("#stockProduct").value,sort_by:state.stockSort.key,sort_order:state.stockSort.order}),data=await api(`/api/stock?${query}`);
  document.querySelectorAll("[data-stock-sort-column]").forEach(th=>{const active=th.dataset.stockSortColumn===state.stockSort.key;th.setAttribute("aria-sort",active?(state.stockSort.order==="asc"?"ascending":"descending"):"none");const morph=th.querySelector("morph-icon");if(morph)morph.morphTo(active?(state.stockSort.order==="asc"?"arrowUp":"arrowDown"):"sortUpDown","snappy")});
  summary("stock",[["在售 SKU",num(data.summary.active_skus,0)],["FBP可售库存",num(data.summary.fbp_present,0)],["FBP预留库存",num(data.summary.fbp_reserved,0)],["建议FBP备货SKU",num(data.summary.replenishment_skus,0),`预计到货前缺货 ${num(data.summary.shortage_skus,0)} 个`]]);
  $("#stockUpdated").textContent=`库存更新至 ${bj(data.data_through)}｜销量更新至 ${bj(data.sales_through)}`;
  const inventory=c=>`<strong>可售 ${num(c.present,0)}</strong><small>预留 ${num(c.reserved,0)}</small>`;
  $("#stockRows").innerHTML=data.items.map(r=>{const risk=r.daily_sales<=0?"no-sales":r.days_available<30?"danger":r.days_available<90?"warning":"safe";return `<tr><td class="stock-product" data-label="商品信息"><strong title="${esc(r.display_name)}">${esc(r.display_name)}</strong>${r.short_name&&r.product_name_raw?`<small title="${esc(r.product_name_raw)}">原名 ${esc(r.product_name_raw)}</small>`:""}<small>${esc(r.shop_name)}</small><small>SKU <span class="copyable" data-copy="${esc(r.sku)}" title="点击复制 SKU">${esc(r.sku)}</span></small><small>货号 <span class="copyable" data-copy="${esc(r.offer_id)}" title="点击复制货号">${esc(r.offer_id||"暂无")}</span></small></td><td class="stock-channel-cell channel-fbp-bg" data-label="FBP">${inventory(r.channels[0])}</td><td class="stock-channel-cell channel-fbs-bg" data-label="realFBS">${inventory(r.channels[1])}</td><td class="stock-channel-cell channel-whd-bg" data-label="WHD">${inventory(r.channels[2])}</td><td class="stock-sales" data-label="有效销量"><span>7天 <b>${num(r.sales_7,0)}</b> 件</span><span>15天 <b>${num(r.sales_15,0)}</b> 件</span><span>30天 <b>${num(r.sales_30,0)}</b> 件</span></td><td class="stock-forecast" data-label="综合预测"><strong>${r.daily_sales?`${num(r.daily_sales,2)} 件/天`:"无法估算"}</strong><small>FBP可售 ${r.days_available==null?"—":`${num(r.days_available,1)} 天`}</small></td><td class="stock-decision ${risk}" data-label="FBP备货决策"><strong>${esc(r.risk_status)}</strong><small>建议备货 ${r.replenishment==null?"—":`${num(r.replenishment,0)} 件`}</small></td><td class="stock-times" data-label="数据更新"><span>库存 ${bj(r.observed_at)}</span><span>销量 ${bj(data.sales_through)}</span></td></tr>`}).join("") || '<tr><td colspan="8" class="stock-empty">当前筛选条件下没有库存或近期有效销量记录。</td></tr>';
  pager("stock",data,loadStock)}catch(error){$("#stockRows").innerHTML=`<tr><td colspan="8" class="stock-empty error">${esc(error.message)}</td></tr>`;throw error}
}
async function loadImports(isPolling = false) {
  updateExportScope();
  const tbody = $("#importRows");
  const hasRows = tbody.querySelectorAll("tr").length > 0 && !tbody.querySelector(".transfer-empty");
  if (!isPolling && !hasRows) {
    tbody.innerHTML = '<tr><td colspan="4" class="transfer-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>导入记录加载中…</span></td></tr>';
  }
  try {
    const rows = await api("/api/imports");
    tbody.innerHTML = rows.map(r => `<tr><td class="import-filename" data-label="文件"><strong title="${esc(r.filename)}">${esc(r.filename)}</strong></td><td data-label="店铺／渠道"><strong>${esc(r.shop_name)}</strong>${channelTag(r.kind)}</td><td class="num" data-label="导入行数">${num(r.row_count, 0)} 行</td><td data-label="导入时间">${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="4" class="transfer-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>暂无导入记录。</span></td></tr>';
  } catch (error) {
    if (!isPolling) {
      tbody.innerHTML = `<tr><td colspan="4" class="transfer-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>导入记录加载失败：${esc(error.message)}</span></td></tr>`;
    }
    throw error;
  }
}
async function loadSync(isPolling = false) {
  const selected = state.shop ? state.shops.find(shop => shop.id === state.shop)?.name : "请选择具体店铺";
  $("#syncManualShop").textContent = selected || "请选择具体店铺";
  const tbody = $("#syncRows");
  const hasRows = tbody.querySelectorAll("tr").length > 0 && !tbody.querySelector(".sync-message");
  if (!isPolling && !hasRows) {
    tbody.innerHTML = '<tr><td colspan="5" class="sync-message"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>拉取记录加载中…</span></td></tr>';
  }
  try {
    const rows = await api("/api/sync");
    const newHtml = rows.map(r => {
      const total = Math.max(1, Number(r.progress_total || 1)),
            done = Number(r.progress_done || 0),
            percent = Math.round(done / total * 100),
            status = r.status === 'failed' ? '失败' : r.status === 'success' ? '成功' : '进行中',
            statusIcon = r.status === 'failed' ? 'alertCircle' : r.status === 'success' ? 'check' : 'sync',
            source = r.run_source === 'auto' ? '自动' : '手动',
            module = syncNames[r.module] || r.module;
      return `<tr data-run-id="${r.id}"><td data-label="店铺"><strong>${esc(r.shop_name)}</strong></td><td data-label="模块"><strong>${esc(module)}</strong><span class="sync-source ${r.run_source === 'auto' ? 'auto' : 'manual'}">${source}</span></td><td data-label="状态"><span class="sync-state ${esc(r.status)}"><morph-icon icon="${statusIcon}" size="12" stroke-width="2.2"></morph-icon>${status}</span>${r.status === 'running' ? `<div class="sync-progress-meta"><span>${done}/${total} 段 · ${percent}%</span><span>${num(r.records, 0)} 条</span></div><div class="sync-progress" role="progressbar" aria-label="${esc(module)}拉取进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>${r.current_from ? `<small class="sync-current">当前：${esc(r.current_from.slice(0, 10))} — ${esc(r.current_to.slice(0, 10))}</small>` : ''}` : ''}</td><td data-label="开始时间">${bj(r.started_at)}</td><td data-label="错误" class="${r.error ? 'error' : 'muted'}">${esc(r.error || '—')}</td></tr>`;
    }).join("") || '<tr><td colspan="5" class="sync-message"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>暂无拉取记录。</span></td></tr>';
    tbody.innerHTML = newHtml;
    return rows;
  } catch (error) {
    if (!isPolling) {
      tbody.innerHTML = `<tr><td colspan="5" class="sync-message error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>拉取记录加载失败：${esc(error.message)}</span></td></tr>`;
    }
    throw error;
  }
}
async function loadExchangeRates(){const root=$("#exchangeRateStatus");if(!root)return;try{const data=await api("/api/exchange-rates"),rate=currency=>data.rates?.[currency]?.base_rate||"暂无";root.innerHTML=`<div><dt>最后成功同步</dt><dd>${data.last_success_at?bj(data.last_success_at):'暂无'}</dd></div><div><dt>数据截止</dt><dd>${data.data_through?bj(data.data_through):'暂无'}</dd></div><div><dt>USD/RUB 基础汇率</dt><dd>${esc(rate('USD'))}</dd></div><div><dt>CNY/RUB 基础汇率</dt><dd>${esc(rate('CNY'))}</dd></div>`}catch(error){root.innerHTML=`<div class="error"><dt>汇率状态</dt><dd>${esc(error.message)}</dd></div>`;throw error}}
function initMacaronSegmentedTime(input){if(!input||input.dataset.macaronSegBound)return;input.dataset.macaronSegBound="true";const wrap=input.closest(".auto-time-wrap");if(!wrap)return;input.style.display="none";const segWrap=document.createElement("div");segWrap.className="macaron-segmented-time";if(input.disabled)segWrap.classList.add("is-disabled");const[initialH,initialM]=(input.value||"02:00").split(":"),hourInp=document.createElement("input"),colon=document.createElement("span"),minInp=document.createElement("input");hourInp.type="text";hourInp.inputMode="numeric";hourInp.maxLength=2;hourInp.className="m-time-seg m-time-hour";hourInp.value=initialH||"02";hourInp.setAttribute("aria-label","小时");hourInp.disabled=input.disabled;colon.className="m-time-colon";colon.textContent=":";minInp.type="text";minInp.inputMode="numeric";minInp.maxLength=2;minInp.className="m-time-seg m-time-min";minInp.value=initialM||"00";minInp.setAttribute("aria-label","分钟");minInp.disabled=input.disabled;segWrap.appendChild(hourInp);segWrap.appendChild(colon);segWrap.appendChild(minInp);wrap.appendChild(segWrap);function syncValue(){let h=parseInt(hourInp.value,10),m=parseInt(minInp.value,10);if(isNaN(h))h=0;if(isNaN(m))m=0;h=Math.max(0,Math.min(23,h));m=Math.max(0,Math.min(59,m));const hStr=String(h).padStart(2,"0"),mStr=String(m).padStart(2,"0");hourInp.value=hStr;minInp.value=mStr;input.value=`${hStr}:${mStr}`;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))}hourInp.onfocus=()=>setTimeout(()=>hourInp.select(),10);minInp.onfocus=()=>setTimeout(()=>minInp.select(),10);hourInp.onclick=()=>hourInp.select();minInp.onclick=()=>minInp.select();hourInp.oninput=()=>{let val=hourInp.value.replace(/\D/g,"");if(val.length===1&&Number(val)>2){hourInp.value="0"+val;syncValue();minInp.focus();return}if(val.length>=2){hourInp.value=val.slice(0,2);syncValue();minInp.focus();return}hourInp.value=val};minInp.oninput=()=>{let val=minInp.value.replace(/\D/g,"");if(val.length===1&&Number(val)>5){minInp.value="0"+val;syncValue();return}if(val.length>=2){minInp.value=val.slice(0,2);syncValue();return}minInp.value=val};hourInp.onblur=syncValue;minInp.onblur=syncValue;hourInp.onkeydown=e=>{if(e.key==="ArrowUp"){e.preventDefault();hourInp.value=String((parseInt(hourInp.value||"0",10)+1)%24).padStart(2,"0");syncValue();hourInp.select()}else if(e.key==="ArrowDown"){e.preventDefault();hourInp.value=String((parseInt(hourInp.value||"0",10)+23)%24).padStart(2,"0");syncValue();hourInp.select()}else if(e.key==="ArrowRight"||e.key===":"||e.key==="Enter"){e.preventDefault();minInp.focus()}};minInp.onkeydown=e=>{if(e.key==="ArrowUp"){e.preventDefault();minInp.value=String((parseInt(minInp.value||"0",10)+5)%60).padStart(2,"0");syncValue();minInp.select()}else if(e.key==="ArrowDown"){e.preventDefault();minInp.value=String((parseInt(minInp.value||"0",10)+55)%60).padStart(2,"0");syncValue();minInp.select()}else if(e.key==="ArrowLeft"||(e.key==="Backspace"&&minInp.value==="")){e.preventDefault();hourInp.focus()}};hourInp.onwheel=e=>{e.preventDefault();let delta=e.deltaY<0?1:-1;hourInp.value=String((parseInt(hourInp.value||"0",10)+delta+24)%24).padStart(2,"0");syncValue();hourInp.select()};minInp.onwheel=e=>{e.preventDefault();let delta=e.deltaY<0?5:-5;minInp.value=String((parseInt(minInp.value||"0",10)+delta+60)%60).padStart(2,"0");syncValue();minInp.select()}}
function updateAutoSyncRow(toggle){const row=toggle.closest("[data-auto-row]"),enabled=toggle.checked;row.classList.toggle("is-disabled",!enabled);row.querySelectorAll("[data-auto-setting],[data-select-button]").forEach(input=>input.disabled=!enabled)}
async function saveAutoSync(){const values=Object.fromEntries([1,2].map(shop=>[String(shop),Object.fromEntries(Object.keys(syncNames).map(module=>[module,{enabled:$("#autoEnabled-"+shop+"-"+module)?.checked||false,interval_hours:Number($("#autoInterval-"+shop+"-"+module)?.value||24),range_days:module==="stock"?1:Number($("#autoRange-"+shop+"-"+module)?.value||1)}]))]));try{await api("/api/auto-sync-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(values)});toast("自动拉取设置已自动保存")}catch(err){toast(err.message,true)}}
async function loadAutoSync(){const rows=await api("/api/auto-sync-settings"),byKey=new Map(rows.map(row=>[`${row.shop_id}:${row.module}`,row])),intervals=[1,2,3,4,6,8,12,24];$("#autoSyncCards").innerHTML=[1,2].map(shop=>{const shopName=state.shops.find(item=>item.id===shop)?.name||`店铺${shop}`;return `<section class="auto-sync-shop"><h3>${esc(shopName)}</h3><div class="auto-sync-rows">${Object.keys(syncNames).map(module=>{const row=byKey.get(`${shop}:${module}`)||{enabled:false,interval_hours:24,range_days:1},selectId=`autoInterval-${shop}-${module}`;return `<article class="auto-sync-row" data-auto-row><div class="auto-sync-module"><strong>${syncNames[module]}</strong><small>${module==='stock'?'实时库存':'按日期范围'}</small></div><label class="auto-sync-toggle"><span class="settings-switch"><input id="autoEnabled-${shop}-${module}" data-auto-enabled type="checkbox" ${row.enabled?'checked':''} aria-label="${esc(shopName)}${syncNames[module]}自动拉取"><span aria-hidden="true"></span></span></label><div class="auto-sync-field"><span>拉取频率</span><div class="return-select" data-return-select><select id="${selectId}" data-auto-setting aria-label="${esc(shopName)}${syncNames[module]}拉取频率">${intervals.map(value=>`<option value="${value}" ${Number(row.interval_hours)===value?'selected':''}>每隔 ${value} 小时</option>`).join("")}</select><button type="button" data-select-button aria-haspopup="listbox" aria-expanded="false" aria-label="${esc(shopName)}${syncNames[module]}拉取频率"><span data-select-label>每隔 ${Number(row.interval_hours||24)} 小时</span><morph-icon icon="chevronDown" size="18" spring="snappy" stroke-width="1.5"></morph-icon></button><div class="return-select-options hidden" data-select-options role="listbox" aria-label="拉取频率"></div></div></div>${module==='stock'?'<div class="auto-sync-field"><span>拉取范围</span><strong class="snapshot-tag">实时</strong></div>':`<label class="auto-sync-field"><span>最近 N 天</span><input id="autoRange-${shop}-${module}" data-auto-setting type="number" min="1" max="365" value="${Number(row.range_days)}" required aria-label="${esc(shopName)}${syncNames[module]}拉取范围"></label>`}</article>`}).join("")}</div></section>`}).join("");document.querySelectorAll("#autoSyncCards select[data-auto-setting]").forEach(select=>{returnSelects[select.id]=createReturnSelect(select.id);select.onchange=()=>saveAutoSync()});document.querySelectorAll("[data-auto-enabled]").forEach(toggle=>{updateAutoSyncRow(toggle);toggle.onchange=()=>{updateAutoSyncRow(toggle);saveAutoSync()}});document.querySelectorAll("#autoSyncCards input[type=number]").forEach(input=>{input.onchange=()=>saveAutoSync()})}
async function loadDingtalk() {
  const data=await api("/api/dingtalk/settings");
  $("#dingtalkConfigured").textContent=data.configured?"已配置":"未配置";
  $("#dingEnabledStatus").textContent=data.daily_enabled?"已启用":"已停用";
  $("#dingNext").textContent=data.next_push_at?bj(data.next_push_at):"—";
  $("#dingEnabled").checked=data.daily_enabled; $("#dingTime").value=data.push_time;
  document.querySelectorAll("#dingWeekdays input").forEach(input=>input.checked=data.weekdays.includes(Number(input.value)));
  initMacaronSegmentedTime($("#dingTime"));
  const last=data.last_run,status=last?(last.status==='success'?'发送成功':last.status==='failed'?'发送失败':'发送中'):"暂无记录";
  $("#dingLastStatus").textContent=status;
  $("#dingtalkLast").innerHTML=`<div><dt>统计日期</dt><dd>${esc(last?.stats_date||'—')}</dd></div><div><dt>推送状态</dt><dd>${esc(status)}</dd></div><div><dt>实际发送时间</dt><dd>${last?.sent_at?bj(last.sent_at):'—'}</dd></div><div><dt>失败原因</dt><dd class="${last?.error?'error':''}">${esc(last?.error||'—')}</dd></div>`;
}
function addMergeMember(member={key_type:"sku",key_value:""}){const id=`mergeMemberType${++mergeMemberIndex}`,row=document.createElement("div");row.className="merge-member";row.innerHTML=`<div class="return-select" data-return-select><select id="${id}" aria-label="成员类型"><option value="sku">SKU</option><option value="offer_id">货号</option></select><button type="button" data-select-button aria-haspopup="listbox" aria-expanded="false"><span data-select-label>SKU</span><morph-icon icon="chevronDown" size="18" spring="snappy" stroke-width="1.5"></morph-icon></button><div class="return-select-options hidden" data-select-options role="listbox" aria-label="成员类型"></div></div><input class="merge-member-value" value="${esc(member.key_value)}" placeholder="输入关联 SKU 或货号" aria-label="成员值" autocomplete="off" required><button type="button" class="member-remove-btn" data-remove-member aria-label="删除成员" title="删除成员"><morph-icon icon="x" size="14" stroke-width="2"></morph-icon></button>`;$("#mergeMembers").append(row);returnSelects[id]=createReturnSelect(id);setReturnSelect(id,member.key_type);return row}
function resetMergeForm(){$("#mergeForm").reset();$("#mergeId").value="";$("#mergeMembers").replaceChildren();addMergeMember()}
async function loadRules(){const query=new URLSearchParams({q:$("#shortSearch").value.trim()}),data=await api(`/api/product-rules?${query}`);ruleData=data;$("#ruleSummary").innerHTML=`<div class="summary-card"><div class="summary-card-icon"><morph-icon icon="tag" size="24" stroke-width="1.8"></morph-icon></div><div><span>中文短名称规则</span><strong>${num(data.summary.short_names,0)}</strong></div></div><div class="summary-card"><div class="summary-card-icon"><morph-icon icon="gitMerge" size="24" stroke-width="1.8"></morph-icon></div><div><span>全局合并关系</span><strong>${num(data.summary.merges,0)}</strong></div></div>`;$("#ruleFixedRule").textContent=data.fixed_rule;$("#shortRuleRows").innerHTML=data.short_names.map(row=>`<tr><td class="copyable" data-copy="${esc(row.sku)}"><strong>${esc(row.sku)}</strong></td><td><span class="rule-short-name">${esc(row.short_name)}</span></td><td>${bj(row.updated_at)}</td><td><div class="table-actions"><button type="button" class="rule-act-btn" data-edit-short="${esc(row.sku)}"><morph-icon icon="edit" size="12" stroke-width="2"></morph-icon>编辑</button><button type="button" class="rule-act-btn is-danger" data-delete-short="${esc(row.sku)}"><morph-icon icon="trash" size="12" stroke-width="2"></morph-icon>删除</button></div></td></tr>`).join("")||'<tr><td colspan="4" class="rule-empty-cell"><div class="rule-empty-state"><morph-icon icon="tag" size="28" stroke-width="1.4"></morph-icon><span>暂无短名称规则</span></div></td></tr>';$("#mergeRuleList").innerHTML=data.groups.map(group=>`<article class="merge-rule-card ${group.status!=="active"?"is-pending":""}"><div class="merge-rule-head"><div><span>主货号</span><strong>${esc(group.primary_offer_id||"待设置")}</strong></div><small>${esc(group.product_name)}</small></div><div class="merge-tags">${group.members.map(member=>`<span>${member.key_type==="sku"?"SKU":"货号"} · ${esc(member.key_value)}</span>`).join("")}</div><div class="merge-rule-foot"><small>${group.note?esc(group.note):`更新于 ${bj(group.updated_at)}`}</small><div class="table-actions"><button type="button" class="rule-act-btn" data-edit-merge="${group.id}"><morph-icon icon="edit" size="12" stroke-width="2"></morph-icon>编辑</button><button type="button" class="rule-act-btn is-danger" data-dissolve="${group.id}"><morph-icon icon="trash" size="12" stroke-width="2"></morph-icon>解散</button></div></div></article>`).join("")||'<div class="rule-empty-card"><morph-icon icon="gitMerge" size="32" stroke-width="1.4"></morph-icon><span>暂无全局合并关系</span><small>在上方添加主货号与关联成员即可建立全局合并分析身份</small></div>';$("#ruleConflicts").classList.toggle("hidden",!data.conflicts.length);$("#ruleConflicts").innerHTML=data.conflicts.length?`<h2>待处理的旧规则冲突</h2>${data.conflicts.map(row=>`<p><strong>${esc(row.key_value)}</strong><span>${esc(row.note)}</span></p>`).join("")}`:""}
async function loadSettings(){$("#probeShops").innerHTML=state.shops.map(s=>`<article class="settings-shop-card"><div class="settings-shop-head"><div><span>店铺 ${s.id}</span><strong>${esc(s.name)}</strong></div></div><div id="probeResult${s.id}" class="settings-probe-result">${probeResult({status:"idle"})}</div></article>`).join("")}
function probeResult(result={}){const status=result.status||(result.valid===true?"success":result.valid===false?"error":"idle"),isIdle=status==="idle",isLoading=status==="loading",isOk=status==="success",isError=status==="error";let badge="";if(isIdle)badge=`<span class="probe-state is-idle"><morph-icon icon="clock" size="12" stroke-width="1.8"></morph-icon>未检测</span>`;else if(isLoading)badge=`<span class="probe-state is-running"><morph-icon icon="sync" size="12" stroke-width="2.2"></morph-icon>正在检测…</span>`;else if(isOk)badge=`<span class="probe-state is-ok"><morph-icon icon="check" size="12" stroke-width="2.2"></morph-icon>凭据有效</span>`;else badge=`<span class="probe-state is-error"><morph-icon icon="alertCircle" size="12" stroke-width="2.2"></morph-icon>连接失败</span>`;const identity=result.identity||{},company=identity.company||{},name=isOk?(company.name||identity.name||"店铺身份已确认"):"—",seller=isOk?(identity.seller_id||identity.client_id||"未返回"):"—",inn=isOk?(company.inn||identity.inn||"未返回"):"—",roles=isOk?((result.roles||[]).join("、")||"未返回"):"—",errorNote=isError?`<p class="probe-error-note">${esc(result.error||"凭据或网络异常")}</p>`:"";const perms=["orders","returns","stock"].map(k=>{const title=syncNames[k]||k;if(isIdle||isLoading)return `<span class="is-idle"><strong>${esc(title)}</strong>待检测</span>`;const val=result.permissions?.[k]||(isOk?"可用":"未返回"),ok=val==="可用";return `<span class="${ok?'is-ok':'is-missing'}"><strong><morph-icon icon="${ok?'check':'x'}" size="12" stroke-width="2.2"></morph-icon>${esc(title)}</strong>${esc(val)}</span>`}).join("");return `${badge}${errorNote}<dl class="probe-facts"><div><dt>店铺身份</dt><dd>${esc(name)}</dd></div><div><dt>Seller ID</dt><dd>${esc(seller)}</dd></div><div><dt>税号 INN</dt><dd>${esc(inn)}</dd></div><div><dt>角色</dt><dd>${esc(roles)}</dd></div></dl><div class="probe-permissions">${perms}</div>`}
async function loadPage(page) {
  if(page==="overview") return Promise.all([loadOverview(),loadTrend()]); if(page==="orders") return loadOrders();
  if(page==="risk") return loadRisk();
  const loaders={timeliness:loadTimeliness,returns:loadReturnPage,complaintPlaceholder:loadExceptionComplaints,stock:loadStock};
  if(loaders[page]) return loaders[page](); if(page==="transfer") return loadImports(); if(page==="sync") return Promise.all([loadSync(),loadAutoSync(),loadExchangeRates()]); if(page==="rules") return loadRules(); if(page==="dingtalk") return loadDingtalk(); if(page==="settings") return loadSettings();
}
function morphConfirm(morph,canonicalIcon,duration=300){if(!morph)return;clearTimeout(morph._confirmTimer);morph.morphTo("check","snappy");morph._confirmTimer=setTimeout(()=>{morph.morphTo(canonicalIcon,"snappy")},duration)}
const navIconMap={overview:"dashboard",orders:"orders",risk:"risk",timeliness:"delivery",returns:"returns",complaintPlaceholder:"messageSquareAlert",stock:"stock",transfer:"transfer",sync:"sync",rules:"rules",dingtalk:"dingtalk"};
const pageDateRangeMap={overview:"#overviewDateRange",orders:"#orderDateRange",risk:"#riskDateRange",timeliness:"#timelinessDateRange",returns:"#returnsDateRange",complaintPlaceholder:"#complaintDateRange",transfer:"#exportDateRange",sync:"#syncDateRange"};
function openPage(page) {
  document.querySelectorAll(".page").forEach(e=>e.classList.toggle("active",e.id===page));
  document.querySelectorAll("#nav button").forEach(e=>{
    const isAct=e.dataset.page===page,morph=e.querySelector("morph-icon"),icon=navIconMap[e.dataset.page];
    e.classList.toggle("active",isAct);
    if(morph&&icon){
      if(isAct)morphConfirm(morph,icon);
      else{clearTimeout(morph._confirmTimer);morph.morphTo(icon,"snappy")}
    }
  });
  Object.entries(pageDateRangeMap).forEach(([p,sel])=>{
    const el=$(sel);
    if(el) el.classList.toggle("hidden", p!==page);
  });
  const hasRange=Boolean(pageDateRangeMap[page]);
  $("#headerDateRange")?.classList.toggle("hidden", !hasRange);
  $("#pageTitle").textContent=titles[page]; loadPage(page).catch(e=>toast(e.message,true));
}

for(const id of ["importShop","importKind","shippingComplaintStatus","shippingNotReceived","shippingResolved","receivedDisputeStatus","receivedRefundType","receivedReturnMethod","receivedHandlingMethod","receivedVideo","receivedReturnResult"]) returnSelects[id]=createReturnSelect(id);
function activateReturnTab(name,focus=false){
  document.querySelectorAll("[data-return-tab]").forEach(button=>{const active=button.dataset.returnTab===name;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus()});
  document.querySelectorAll(".return-tab").forEach(panel=>{const active=panel.id===`returns-${name}`;panel.classList.toggle("active",active);panel.hidden=!active});
}
$("#loginForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});const session=await api("/api/session");state.csrf=session.csrf_token;showShell();await loadShops();await Promise.all([loadOverview(),loadTrend()])}catch(err){$("#loginError").textContent=err.message}});
$("#nav").addEventListener("click",e=>{const button=e.target.closest("[data-page]");if(button)openPage(button.dataset.page)});
$("#shopPickerButton").onclick=()=>{const hidden=$("#shopOptions").classList.toggle("hidden");$("#shopPickerButton").setAttribute("aria-expanded",String(!hidden));$("#shopPickerMorph")?.morphTo(!hidden?"chevronUp":"chevronDown","snappy")};
$("#shopOptions").onclick=e=>{const option=e.target.closest("[data-shop]");if(!option)return;state.shop=Number(option.dataset.shop);state.page=1;Object.keys(state.pages).forEach(k=>state.pages[k]=1);$("#shopPickerValue").textContent=option.textContent;document.querySelectorAll("#shopOptions [data-shop]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy");const page=$(".page.active").id;loadPage(page).catch(err=>toast(err.message,true))};
$("#channelPickerButton").onclick=()=>{const hidden=$("#channelOptions").classList.toggle("hidden");$("#channelPickerButton").setAttribute("aria-expanded",String(!hidden));$("#channelPickerMorph")?.morphTo(!hidden?"chevronUp":"chevronDown","snappy")};
$("#channelOptions").onclick=e=>{const option=e.target.closest("[data-channel]");if(!option)return;$("#channelFilter").value=option.dataset.channel;$("#channelPickerValue").textContent=option.textContent;document.querySelectorAll("#channelOptions [data-channel]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy");$("#channelFilter").dispatchEvent(new Event("change"))};
$("#orderFilterForm").addEventListener("submit",e=>{e.preventDefault();state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#orderStatusChips")?.addEventListener("click",e=>{const chip=e.target.closest("[data-order-status]");if(!chip)return;document.querySelectorAll("#orderStatusChips .status-chip").forEach(c=>{const isTarget=c===chip;c.classList.toggle("active",isTarget);c.setAttribute("aria-selected",String(isTarget))});state.orderStatus=chip.dataset.orderStatus;state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#orderSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#orderFilterForm").requestSubmit()}});
$("#channelFilter").addEventListener("change",()=>{state.page=1;loadOrders().catch(err=>toast(err.message,true))});
$("#riskSearch").addEventListener("input",renderRiskItems);
$("#riskHighToggle")?.addEventListener("click",()=>{riskHighOnly=!riskHighOnly;const btn=$("#riskHighToggle");btn.classList.toggle("active",riskHighOnly);btn.setAttribute("aria-pressed",String(riskHighOnly));renderRiskItems()});
$("#timelinessFilterForm").addEventListener("submit",e=>{e.preventDefault();state.pages.timeliness=1;loadTimeliness().catch(err=>toast(err.message,true))});
$("#timelinessClear").onclick=()=>{$("#timelinessSearch").value="";state.pages.timeliness=1;loadTimeliness().catch(err=>toast(err.message,true))};
$("#stockFilterForm").onsubmit=e=>{e.preventDefault();state.pages.stock=1;loadStock().catch(err=>toast(err.message,true))};
$("#stockClear").onclick=()=>{$("#stockFilterForm").reset();state.pages.stock=1;loadStock().catch(err=>toast(err.message,true))};
document.querySelectorAll("[data-stock-sort]").forEach(button=>button.onclick=()=>{const key=button.dataset.stockSort;state.stockSort.order=state.stockSort.key===key&&state.stockSort.order==="desc"?"asc":"desc";state.stockSort.key=key;state.pages.stock=1;document.querySelectorAll("[data-stock-sort]").forEach(btn=>{const morph=btn.querySelector("morph-icon");if(!morph)return;if(btn.dataset.stockSort===state.stockSort.key){morph.morphTo(state.stockSort.order==="asc"?"arrowUp":"arrowDown","snappy")}else{morph.morphTo("sortUpDown","snappy")}});loadStock().catch(err=>toast(err.message,true))});
$("#returnTabs").onclick=e=>{const tab=e.target.closest("[data-return-tab]")?.dataset.returnTab;if(tab)activateReturnTab(tab)};
$("#returnTabs").onkeydown=e=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;e.preventDefault();const tabs=[...$("#returnTabs").querySelectorAll("[role=tab]")],current=tabs.indexOf(document.activeElement),index=e.key==="Home"?0:e.key==="End"?tabs.length-1:(current+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;activateReturnTab(tabs[index].dataset.returnTab,true)};
$("#returnsSearch").onsubmit=e=>{e.preventDefault();state.pages.returns=1;loadReturns().catch(err=>toast(err.message,true))};
$("#returnsClear").onclick=()=>{$("#returnsQuery").value="";state.pages.returns=1;loadReturns().catch(err=>toast(err.message,true))};
$("#rfbsReturnsSearch").onsubmit=e=>{e.preventDefault();state.pages.rfbsReturns=1;loadRfbsReturns().catch(err=>toast(err.message,true))};
$("#rfbsReturnsClear").onclick=()=>{$("#rfbsReturnsQuery").value="";state.pages.rfbsReturns=1;loadRfbsReturns().catch(err=>toast(err.message,true))};
$("#exceptionComplaintTabs").onclick=e=>{const tab=e.target.closest("[data-exception-tab]")?.dataset.exceptionTab;if(tab)activateExceptionTab(tab)};
$("#exceptionComplaintTabs").onkeydown=e=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;e.preventDefault();const tabs=[...$("#exceptionComplaintTabs").querySelectorAll("[role=tab]")],current=tabs.indexOf(document.activeElement),index=e.key==="Home"?0:e.key==="End"?tabs.length-1:(current+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;activateExceptionTab(tabs[index].dataset.exceptionTab,true)};
$("#shippingComplaintFilter").onsubmit=e=>{e.preventDefault();state.pages.shippingComplaints=1;loadShippingComplaints().catch(err=>toast(err.message,true))};
$("#shippingComplaintClear").onclick=()=>{$("#shippingComplaintQuery").value="";setReturnSelect("shippingComplaintStatus","");state.pages.shippingComplaints=1;loadShippingComplaints().catch(err=>toast(err.message,true))};
$("#receivedDisputeFilter").onsubmit=e=>{e.preventDefault();state.pages.receivedDisputes=1;loadReceivedDisputes().catch(err=>toast(err.message,true))};
$("#receivedDisputeClear").onclick=()=>{$("#receivedDisputeQuery").value="";setReturnSelect("receivedDisputeStatus","");state.pages.receivedDisputes=1;loadReceivedDisputes().catch(err=>toast(err.message,true))};
function openShippingEditor(row,complaint=null){
  const editor=$("#shippingComplaintEditor"),form=$("#shippingComplaintForm");form.reset();
  $("#shippingComplaintShop").value=row.shop_id;$("#shippingComplaintPosting").value=row.posting_number;
  $("#shippingComplaintNumber").value=complaint?.complaint_number||"";$("#shippingComplaintNumber").readOnly=Boolean(complaint);$("#shippingComplaintAt").value=localDateTime(complaint?.complaint_at||new Date());
  $("#shippingComplaintChannel").value=complaint?.channel||"";$("#shippingComplaintDeadline").textContent=deadlineText(row);
  $("#shippingWarehouse").value=complaint?.warehouse||"";$("#shippingOrderProcessStatus").value=complaint?.order_process_status||"";$("#shippingComplaintState").value=complaint?.complaint_status||"";$("#shippingCompensationStatus").value=complaint?.compensation_status||"";
  $("#shippingPlatformCompensation").value=complaint?.platform_compensation_rub??"";$("#shippingPlatformAt").value=localDateTime(complaint?.platform_compensated_at);$("#shippingPlatformConversion").textContent=compensationConversion(complaint,"platform_compensation","RUB");
  $("#shippingLogisticsCompensation").value=complaint?.logistics_compensation_cny??"";$("#shippingLogisticsAt").value=localDateTime(complaint?.logistics_compensated_at);$("#shippingLogisticsConversion").textContent=compensationConversion(complaint,"logistics_compensation","CNY");$("#shippingComplaintNotes").value=complaint?.notes||"";
  setReturnSelect("shippingNotReceived",boolSelect(complaint?.not_received_return));setReturnSelect("shippingResolved",boolSelect(complaint?.resolved));
  $("#shippingComplaintEditorTitle").textContent=complaint?`编辑投诉 ${complaint.complaint_number}`:`为 ${row.posting_number} 新建投诉`;if(!editor.open)editor.showModal();$("#shippingComplaintNumber").focus();
}
$("#shippingComplaintRows").onclick=e=>{const create=e.target.closest("[data-new-shipping]")?.dataset.newShipping,edit=e.target.closest("[data-edit-shipping]")?.dataset.editShipping;if(create!=null)openShippingEditor(shippingComplaintItems[Number(create)]);if(edit){const [rowIndex,itemIndex]=edit.split(":").map(Number),row=shippingComplaintItems[rowIndex];openShippingEditor(row,row.complaints[itemIndex])}};
$("#shippingComplaintForm").onsubmit=async e=>{e.preventDefault();const at=$("#shippingComplaintAt").value;const body={shop_id:Number($("#shippingComplaintShop").value),posting_number:$("#shippingComplaintPosting").value,complaint_number:$("#shippingComplaintNumber").value.trim(),complaint_at:at?new Date(`${at}:00+08:00`).toISOString():"",channel:$("#shippingComplaintChannel").value.trim(),not_received_return:nullableBool($("#shippingNotReceived").value),warehouse:$("#shippingWarehouse").value.trim(),order_process_status:$("#shippingOrderProcessStatus").value.trim(),complaint_status:$("#shippingComplaintState").value.trim(),compensation_status:$("#shippingCompensationStatus").value.trim(),platform_compensation_rub:$("#shippingPlatformCompensation").value,platform_compensated_at:$("#shippingPlatformAt").value,logistics_compensation_cny:$("#shippingLogisticsCompensation").value,logistics_compensated_at:$("#shippingLogisticsAt").value,resolved:nullableBool($("#shippingResolved").value),package_returned:null,notes:$("#shippingComplaintNotes").value};await api("/api/exception-complaints/shipping",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});toast("投诉已保存");$("#shippingComplaintEditor").close();await loadShippingComplaints()};
$("#shippingComplaintCancel").onclick=()=>$("#shippingComplaintEditor").close();
$("#shippingComplaintEditor").onclick=e=>{if(e.target===e.currentTarget)e.currentTarget.close()};
[["shippingPlatformCompensation","shippingPlatformAt","shippingPlatformConversion"],["shippingLogisticsCompensation","shippingLogisticsAt","shippingLogisticsConversion"],["receivedPlatformCompensation","receivedPlatformAt","receivedPlatformConversion"],["receivedLogisticsCompensation","receivedLogisticsAt","receivedLogisticsConversion"]].forEach(([amount,time,result])=>[amount,time].forEach(id=>$("#"+id).addEventListener("input",()=>{$("#"+result).textContent=$("#"+amount).value||$("#"+time).value?"保存后按赔偿时点重新计算":"折算金额：—"})));
function openReceivedEditor(row){
  const editor=$("#receivedDisputeEditor"),form=$("#receivedDisputeForm");form.reset();$("#receivedDisputeShop").value=row.shop_id;$("#receivedDisputeNumber").value=row.return_number;$("#receivedDisputeEditorTitle").textContent=`${row.return_number} · ${row.shop_name}`;
  $("#receivedComplaintDeadline").textContent=deadlineText(row);setReturnSelect("receivedRefundType",row.refund_type||"");$("#receivedRefundAmount").value=row.refund_amount??"";$("#receivedRefundCurrency").value=row.refund_currency||settlementCurrency(row.shop_id);$("#receivedPlatformCompensation").value=row.platform_compensation_rub??"";$("#receivedPlatformAt").value=localDateTime(row.platform_compensated_at);$("#receivedPlatformConversion").textContent=compensationConversion(row,"platform_compensation","RUB");$("#receivedLogisticsCompensation").value=row.logistics_compensation_cny??"";$("#receivedLogisticsAt").value=localDateTime(row.logistics_compensated_at);$("#receivedLogisticsConversion").textContent=compensationConversion(row,"logistics_compensation","CNY");$("#receivedProcessStatus").value=row.process_status||"";setReturnSelect("receivedReturnMethod",row.return_method||"");$("#receivedImlNumber").value=row.iml_return_number||"";$("#receivedImlSn").value=row.iml_system_sn||"";$("#receivedBuyerTracking").value=row.buyer_tracking_number||"";setReturnSelect("receivedHandlingMethod",row.handling_method||"");setReturnSelect("receivedVideo",boolSelect(row.video_recorded));$("#receivedOutboundOrder").value=row.outbound_order_number||"";setReturnSelect("receivedReturnResult",row.return_result||"");$("#receivedDisputeNotes").value=row.notes||"";if(!editor.open)editor.showModal();
}
$("#receivedDisputeRows").onclick=e=>{const index=e.target.closest("[data-edit-received]")?.dataset.editReceived;if(index!=null)openReceivedEditor(receivedDisputeItems[Number(index)])};
$("#receivedDisputeForm").onsubmit=async e=>{e.preventDefault();const body={shop_id:Number($("#receivedDisputeShop").value),return_number:$("#receivedDisputeNumber").value,refund_type:$("#receivedRefundType").value,refund_amount:$("#receivedRefundAmount").value,refund_currency:$("#receivedRefundCurrency").value.trim(),platform_compensation_rub:$("#receivedPlatformCompensation").value,platform_compensated_at:$("#receivedPlatformAt").value,logistics_compensation_cny:$("#receivedLogisticsCompensation").value,logistics_compensated_at:$("#receivedLogisticsAt").value,process_status:$("#receivedProcessStatus").value.trim(),return_method:$("#receivedReturnMethod").value,iml_return_number:$("#receivedImlNumber").value.trim(),iml_system_sn:$("#receivedImlSn").value.trim(),buyer_tracking_number:$("#receivedBuyerTracking").value.trim(),handling_method:$("#receivedHandlingMethod").value,video_recorded:nullableBool($("#receivedVideo").value),outbound_order_number:$("#receivedOutboundOrder").value.trim(),return_result:$("#receivedReturnResult").value,notes:$("#receivedDisputeNotes").value};await api("/api/exception-complaints/received",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});toast("已收货纠纷已保存");$("#receivedDisputeEditor").close();await loadReceivedDisputes()};
$("#receivedDisputeCancel").onclick=()=>$("#receivedDisputeEditor").close();
$("#receivedDisputeEditor").onclick=e=>{if(e.target===e.currentTarget)e.currentTarget.close()};
$("#reasonRows").onclick=async e=>{const reasonBtn=e.target.closest("[data-reason]");if(!reasonBtn)return;const reason=reasonBtn.dataset.reason,target=$("#reasonDetails"),query=new URLSearchParams({shop_id:state.shop,reason,from:riskRange.start,to:riskRange.end});target.classList.remove("hidden");target.innerHTML='<div class="reason-detail-loading"><morph-icon icon="sync" size="16" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>原因对应订单加载中…</span></div>';try{const data=await api(`/api/risk/reasons?${query}`);target.innerHTML=`<div class="reason-detail-header"><div class="reason-detail-title"><morph-icon icon="alertTriangle" size="15" stroke-width="2"></morph-icon><h3>${esc(reasonBtn.textContent.trim())} · 关联订单明细</h3></div><span class="reason-detail-total">共 ${num(data.details.length,0)} 个异常订单</span></div><div class="reason-detail-grid">${data.details.map(r=>`<div class="reason-detail-card"><div class="reason-card-head"><strong class="copyable" data-copy="${esc(r.posting_number)}" title="点击复制订单号"><morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>${esc(r.posting_number)}</strong></div><div class="reason-card-foot"><span class="shop-tag">${esc(r.shop_name)}</span>${channelTag(r.channel)}<span class="pieces-count">× ${num(r.pieces,0)} 件</span></div></div>`).join("")||'<span class="muted">当前时间范围内没有对应订单。</span>'}</div>`;target.scrollIntoView({behavior:"smooth",block:"nearest"})}catch(error){target.innerHTML=`<span class="error">${esc(error.message)}</span>`}};
$("#prevPage").onclick=()=>{state.page--;loadOrders()}; $("#nextPage").onclick=()=>{state.page++;loadOrders()};
async function saveShopNames(){const s1=$("#shop1")?.value?.trim()||"",s2=$("#shop2")?.value?.trim()||"";if(!s1||!s2)return;const curr1=state.shops.find(s=>s.id===1)?.name,curr2=state.shops.find(s=>s.id===2)?.name;if(s1===curr1&&s2===curr2)return;try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:s1,2:s2})});await loadShops();toast("店铺名称已自动保存")}catch(err){toast(err.message,true)}}
$("#shopForm").addEventListener("submit",e=>{e.preventDefault();saveShopNames()});
$("#shop1").addEventListener("change",saveShopNames);
$("#shop2").addEventListener("change",saveShopNames);
$("#shop1").addEventListener("blur",saveShopNames);
$("#shop2").addEventListener("blur",saveShopNames);
$("#probeAllButton").onclick=async e=>{const btn=$("#probeAllButton");btn.disabled=true;state.shops.forEach(s=>{const el=$("#probeResult"+s.id);if(el)el.innerHTML=probeResult({status:"loading"})});try{await Promise.all(state.shops.map(async s=>{const target=$("#probeResult"+s.id);if(!target)return;try{const res=await api(`/api/ozon/probe/${s.id}`,{method:"POST"});target.innerHTML=probeResult({...res,status:res.valid?"success":"error"})}catch(error){target.innerHTML=probeResult({valid:false,error:error.message,status:"error"})}}));toast("API 连接与权限检测已完成")}catch(err){toast(err.message,true)}finally{btn.disabled=false}};
$("#dingtalkForm").addEventListener("submit",async e=>{e.preventDefault();try{const weekdays=[...document.querySelectorAll("#dingWeekdays input:checked")].map(input=>Number(input.value));await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({daily_enabled:$("#dingEnabled").checked,push_time:$("#dingTime").value,weekdays})});toast("推送计划已保存");await loadDingtalk()}catch(err){toast(err.message,true)}});
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
const exportNames={orders:["订单","订单号、渠道、时间、状态及金额"],risk:["SKU风险及原因","SKU、渠道、货件及固定取消原因"],returns:["退货","取消记录和退货申请"],complaints:["投诉","投诉编号、状态、赔付及备注"]};
$("#exportButtons").innerHTML=Object.entries(exportNames).map(([key,[name,description]])=>`<article class="export-card"><div><strong>${name}</strong><p>${description}</p><small>受当前时间范围影响</small></div><button type="button" data-export="${key}">导出</button></article>`).join("");
function updateExportScope(){const shop=state.shop?state.shops.find(item=>item.id===state.shop)?.name:"两店铺合并";$("#exportScope").textContent=`当前店铺：${shop||"两店铺合并"}｜时间范围：${exportRange.start} 至 ${exportRange.end}`}
$("#exportButtons").onclick=e=>{const button=e.target.closest("[data-export]"),module=button?.dataset.export;if(!module)return;const query=new URLSearchParams({shop_id:state.shop,date_from:exportRange.start,date_to:exportRange.end});button.disabled=true;const text=button.textContent;button.textContent="正在准备…";location.href=`/api/export/${module}?${query}`;setTimeout(()=>{button.disabled=false;button.textContent=text},800)};
$("#shortNameForm").onsubmit=async e=>{e.preventDefault();const sku=$("#shortSku").value.trim(),short_name=$("#shortName").value.trim();if(!sku){$("#shortSku").focus();return toast("请输入 SKU",true)}if(!short_name){$("#shortName").focus();return toast("请输入中文短名称",true)}await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"short_name",sku,short_name})});toast("短名称已保存");$("#shortNameForm").reset();await loadRules()};
$("#shortReset").onclick=()=>$("#shortNameForm").reset();$("#shortSearchForm").onsubmit=e=>{e.preventDefault();loadRules().catch(error=>toast(error.message,true))};$("#shortSearchClear").onclick=()=>{$("#shortSearch").value="";loadRules().catch(error=>toast(error.message,true))};
$("#shortRuleRows").onclick=async e=>{const edit=e.target.closest("[data-edit-short]")?.dataset.editShort,remove=e.target.closest("[data-delete-short]")?.dataset.deleteShort;if(edit){const row=ruleData.short_names.find(value=>value.sku===edit);$("#shortSku").value=row.sku;$("#shortName").value=row.short_name;$("#shortName").focus()}if(remove){await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"delete_short_name",sku:remove})});toast("短名称已删除");await loadRules()}};
$("#addMergeMember").onclick=()=>addMergeMember();$("#mergeMembers").onclick=e=>{if(e.target.closest("[data-remove-member]"))e.target.closest(".merge-member").remove()};$("#mergeReset").onclick=resetMergeForm;
$("#mergeForm").onsubmit=async e=>{e.preventDefault();const primary_offer_id=$("#primaryOffer").value.trim();if(!primary_offer_id){$("#primaryOffer").focus();return toast("请输入主货号",true)}const members=[...$("#mergeMembers").querySelectorAll(".merge-member")].map(row=>({key_type:row.querySelector("select").value,key_value:row.querySelector(".merge-member-value").value.trim()})).filter(m=>m.key_value);await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"merge",id:Number($("#mergeId").value||0),primary_offer_id,primary_sku:$("#primarySku").value.trim(),members})});toast("全局合并已保存");resetMergeForm();await loadRules()};
$("#mergeRuleList").onclick=async e=>{const edit=Number(e.target.closest("[data-edit-merge]")?.dataset.editMerge||0),dissolve=Number(e.target.closest("[data-dissolve]")?.dataset.dissolve||0);if(edit){const group=ruleData.groups.find(value=>value.id===edit);$("#mergeId").value=group.id;$("#primaryOffer").value=group.primary_offer_id||"";$("#primarySku").value=group.primary_sku||"";$("#mergeMembers").replaceChildren();group.members.filter(member=>!(member.key_type==="offer_id"&&member.key_value===group.primary_offer_id)).forEach(addMergeMember);if(!$("#mergeMembers").children.length)addMergeMember();$("#primaryOffer").focus()}if(dissolve){await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"dissolve",id:dissolve})});toast("合并关系已解散");resetMergeForm();await loadRules()}};
resetMergeForm();
$("#syncButtons").innerHTML=Object.entries(syncNames).map(([key,name])=>`<article class="sync-manual-card" data-sync-module="${key}"><div><strong>${name}</strong><p>${syncDescriptions[key]}</p></div><button class="primary" type="button" data-module="${key}">拉取</button></article>`).join("");
const today=new Date(); today.setHours(0,0,0,0);
const isoDate=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const localDate=value=>{const [year,month,day]=value.split("-").map(Number);return new Date(year,month-1,day)};
const shiftDays=(date,amount)=>new Date(date.getFullYear(),date.getMonth(),date.getDate()+amount);
const shiftMonths=(date,amount)=>new Date(date.getFullYear(),date.getMonth()+amount,1);
const threeMonthsAgo=(()=>{const target=new Date(today.getFullYear(),today.getMonth()-3,1);target.setDate(Math.min(today.getDate(),new Date(target.getFullYear(),target.getMonth()+1,0).getDate()));return target})();
const monthNames=["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
const formatShortDate=dStr=>{const parts=dStr.split("-");return `${parts[1]}.${parts[2]}`};
const formatRangeDisplay=(start,end,presetText)=>{
  if(presetText)return presetText;
  if(start===end)return formatShortDate(start);
  const [sY]=start.split("-"),[eY]=end.split("-");
  if(sY===eY)return `${formatShortDate(start)} - ${formatShortDate(end)}`;
  return `${sY.slice(2)}.${formatShortDate(start)} - ${eY.slice(2)}.${formatShortDate(end)}`;
};
function createDateRange(rootId,onChange){
  const root=$(rootId);if(!root)return null;
  const range={start:isoDate(threeMonthsAgo),end:isoDate(today),selecting:false,view:new Date(today.getFullYear(),today.getMonth(),1),preset:"3months"};
  root.innerHTML=`<div class="date-range-wrap"><button class="date-range-pill" data-range-role="button" type="button" aria-haspopup="dialog" aria-expanded="false" title="时间范围：${range.start} 至 ${range.end}"><morph-icon icon="calendar" size="14" spring="snappy" stroke-width="1.8"></morph-icon><span class="date-range-text" data-range-role="label">近三个月</span><morph-icon icon="chevronDown" size="14" spring="snappy" stroke-width="1.8"></morph-icon></button><div class="date-range-panel header-date-panel hidden" data-range-role="panel" role="dialog" aria-label="选择日期范围"><div class="range-calendars"><div class="range-calendar"><div class="range-month-head"><button data-range-role="prev" type="button" aria-label="上个月"><morph-icon icon="chevronLeft" size="16" spring="snappy" stroke-width="1.5"></morph-icon></button><strong data-range-role="month-a"></strong><span></span></div><div class="range-weekdays"><span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>周日</span></div><div class="range-days" data-range-role="days-a"></div></div><div class="range-calendar"><div class="range-month-head"><span></span><strong data-range-role="month-b"></strong><button data-range-role="next" type="button" aria-label="下个月"><morph-icon icon="chevronRight" size="16" spring="snappy" stroke-width="1.5"></morph-icon></button></div><div class="range-weekdays"><span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>周日</span></div><div class="range-days" data-range-role="days-b"></div></div></div><div class="range-presets"><button type="button" data-range="today">今天</button><button type="button" data-range="3days">3天内</button><button type="button" data-range="7days">7天内</button><button type="button" data-range="3months">近三个月</button><button type="button" data-range="all">全部时间</button></div></div></div>`;
  const find=role=>root.querySelector(`[data-range-role="${role}"]`),label=find("label"),panel=find("panel"),button=find("button"),caret=button.querySelector("morph-icon:last-of-type");
  const month=(value,title,days)=>{title.textContent=`${monthNames[value.getMonth()]} ${value.getFullYear()}年`;const first=new Date(value.getFullYear(),value.getMonth(),1),last=new Date(value.getFullYear(),value.getMonth()+1,0),items=[];for(let index=0;index<(first.getDay()+6)%7;index++)items.push('<span class="range-blank"></span>');for(let day=1;day<=last.getDate();day++){const current=new Date(value.getFullYear(),value.getMonth(),day),key=isoDate(current),weekend=current.getDay()===0||current.getDay()===6,inRange=key>=range.start&&key<=range.end,edge=key===range.start||key===range.end;items.push(`<button type="button" data-date="${key}" class="${weekend?'weekend ':''}${inRange?'in-range ':''}${edge?'range-edge ':''}${key===isoDate(today)?'today':''}" aria-label="${value.getFullYear()}年${value.getMonth()+1}月${day}日">${day}</button>`)}days.innerHTML=items.join("")};
  const render=()=>{month(range.view,find("month-a"),find("days-a"));month(shiftMonths(range.view,1),find("month-b"),find("days-b"));root.querySelectorAll("[data-range]").forEach(item=>item.classList.toggle("active",item.dataset.range===range.preset))};
  const set=(start,end,presetName="",notify=true)=>{
    range.start=isoDate(start);range.end=isoDate(end);range.selecting=false;range.preset=presetName;
    const choices={today:"今天","3days":"3天内","7days":"7天内","3months":"近三个月",all:"全部时间"};
    const presetText=choices[presetName]||"";
    label.textContent=formatRangeDisplay(range.start,range.end,presetText);
    button.title=`时间范围：${range.start} 至 ${range.end}`;
    render();if(notify)onChange(range);
  };
  const preset=(name,notify=true)=>{const choices={today:[today,today],"3days":[shiftDays(today,-2),today],"7days":[shiftDays(today,-6),today],"3months":[threeMonthsAgo,today],all:[new Date(2020,0,1),today]};set(...choices[name],name,notify)};
  root.onclick=e=>{
    if(e.target.closest(".date-range-pill,.date-range-button")){
      const hidden=panel.classList.toggle("hidden");
      button.setAttribute("aria-expanded",String(!hidden));
      if(caret)caret.morphTo(!hidden?"chevronUp":"chevronDown","snappy");
      render();return;
    }
    const role=e.target.closest("[data-range-role]")?.dataset.rangeRole;
    if(role==="prev"||role==="next"){range.view=shiftMonths(range.view,role==="prev"?-1:1);render();return}
    if(e.target.dataset.range){preset(e.target.dataset.range);panel.classList.add("hidden");button.setAttribute("aria-expanded","false");if(caret)caret.morphTo("chevronDown","snappy");return}
    const value=e.target.dataset.date;if(!value)return;
    if(!range.selecting){
      range.start=value;range.end=value;range.selecting=true;range.preset="";
      label.textContent=`${formatShortDate(value)} - …`;
      button.title=`已选起始日期：${value}，请选择结束日期`;
      render();
    }else{
      const first=localDate(range.start),second=localDate(value);
      set(first<=second?first:second,first<=second?second:first,"");
      panel.classList.add("hidden");button.setAttribute("aria-expanded","false");
      if(caret)caret.morphTo("chevronDown","snappy");
    }
  };
  preset("3months",false);return range;
}
const overviewRange=createDateRange("#overviewDateRange",()=>loadOverview().catch(error=>toast(error.message,true)));
const orderRange=createDateRange("#orderDateRange",()=>{state.page=1;loadOrders().catch(error=>toast(error.message,true))});
const riskRange=createDateRange("#riskDateRange",()=>loadRisk().catch(error=>toast(error.message,true)));
const timelinessRange=createDateRange("#timelinessDateRange",()=>{state.pages.timeliness=1;loadTimeliness().catch(error=>toast(error.message,true))});
const returnsRange=createDateRange("#returnsDateRange",()=>{state.pages.returns=state.pages.rfbsReturns=1;loadReturnPage().catch(error=>toast(error.message,true))});
const complaintRange=createDateRange("#complaintDateRange",()=>{state.pages.shippingComplaints=state.pages.receivedDisputes=1;loadExceptionComplaints().catch(error=>toast(error.message,true))});
const exportRange=createDateRange("#exportDateRange",()=>updateExportScope());
const syncRange=createDateRange("#syncDateRange",()=>{});
const exchangeRateRange=createDateRange("#exchangeRateDateRange",()=>{});
document.addEventListener("click",e=>{const copyEl=e.target.closest(".copyable,[data-copy]");if(copyEl){const val=copyEl.dataset.copy?.trim();if(val&&val!=="暂无"&&val!=="—"){const done=()=>toast(`已复制：${val}`);if(navigator.clipboard?.writeText){navigator.clipboard.writeText(val).then(done).catch(()=>{const ta=document.createElement("textarea");ta.value=val;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();done()})}else{const ta=document.createElement("textarea");ta.value=val;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();done()}if(e.target.closest("summary"))e.preventDefault();e.stopPropagation();return}}const path=e.composedPath();if(!path.some(el=>el.classList?.contains?.("date-range-panel")||el.classList?.contains?.("date-range-pill")||el.classList?.contains?.("date-range-button"))){document.querySelectorAll(".date-range-panel:not(.hidden)").forEach(panel=>panel.classList.add("hidden"));document.querySelectorAll(".date-range-pill[aria-expanded=true],.date-range-button[aria-expanded=true]").forEach(button=>{button.setAttribute("aria-expanded","false");button.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")})}if(!path.some(el=>el.id==="shopPickerButton"||el.id==="shopOptions")){$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy")}if(!path.some(el=>el.id==="channelPickerButton"||el.id==="channelOptions")){$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy")}if(!path.some(el=>el.hasAttribute?.("data-select-button")||el.hasAttribute?.("data-select-options")))Object.values(returnSelects).forEach(select=>select.close());if(!e.target.closest("#orderTrend"))$("#orderTrend .trend-tooltip")?.classList.add("hidden")});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){document.querySelectorAll(".date-range-panel").forEach(panel=>panel.classList.add("hidden"));document.querySelectorAll(".date-range-pill,.date-range-button").forEach(button=>{button.setAttribute("aria-expanded","false");button.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")});$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy");$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy");Object.values(returnSelects).forEach(select=>select.close())}});
$("#trendGranularity").onclick=async e=>{const btn=e.target.closest("button[data-granularity]");if(!btn)return;const value=btn.dataset.granularity;if(!value||value===state.overviewGranularity)return;state.overviewGranularity=value;$("#trendGranularity").querySelectorAll("button").forEach(b=>b.classList.toggle("active",b===btn));renderTrendWaveLoader(value);try{await loadTrend()}catch(error){toast(error.message,true)}};
async function waitForSync(runId, module) {
  for (;;) {
    const task = await api(`/api/sync/${runId}`);
    await loadSync(true);
    if (task.status !== "running") {
      if (task.status === "success") toast(`${syncNames[module]}拉取完成：${num(task.records, 0)} 条`);
      else toast(task.error || "拉取失败", true);
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}
$("#syncButtons").onclick = async e => {
  const button = e.target.closest("[data-module]"), module = button?.dataset.module;
  if (!module) return;
  if (!state.shop) return toast("请先在左上角选择一个店铺", true);
  if (syncRange.preset === "all" && !confirm("整个时段将按自然月逐段拉取，耗时可能较长。确认开始？")) return;
  const text = button.textContent;
  button.disabled = true;
  button.textContent = "拉取中…";
  try {
    const task = await api(`/api/sync/${module}?shop_id=${state.shop}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from: syncRange.start, to: syncRange.end })
    });
    await loadSync(true);
    await waitForSync(task.run_id, module);
  } catch (err) {
    toast(err.message, true);
    await loadSync(true);
  } finally {
    button.disabled = false;
    button.textContent = text;
  }
};
$("#exchangeRateButton").onclick=async()=>{const button=$("#exchangeRateButton"),text=button.textContent;button.disabled=true;button.textContent="拉取中…";try{const result=await api("/api/exchange-rates/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:exchangeRateRange.start,to:exchangeRateRange.end})});toast(`汇率拉取完成：${num(result.records,0)} 条`);await loadExchangeRates()}catch(error){toast(error.message,true)}finally{button.disabled=false;button.textContent=text}};
const systemTheme=window.matchMedia("(prefers-color-scheme: dark)");
function getThemeMode(){const follow=localStorage.getItem("themeFollowSystem");if(follow==="false")return localStorage.getItem("theme")==="dark"?"dark":"light";return "system"}
function applyTheme(){const mode=getThemeMode(),dark=mode==="system"?systemTheme.matches:mode==="dark";document.documentElement.dataset.theme=dark?"dark":"";document.querySelectorAll("#themeSegmented button").forEach(btn=>{const active=btn.dataset.themeMode===mode;btn.classList.toggle("active",active);btn.setAttribute("aria-checked",String(active))});const themeMorph=document.getElementById("themeMorphIcon");if(themeMorph)themeMorph.morphTo(dark?"moon":"sun","snappy")}
function setThemeMode(mode){if(mode==="system"){localStorage.setItem("themeFollowSystem","true");localStorage.removeItem("theme")}else{localStorage.setItem("themeFollowSystem","false");localStorage.setItem("theme",mode)}applyTheme();toast(`外观已切换为：${mode==="system"?"跟随系统":mode==="light"?"浅色模式":"深色模式"}`)}
$("#themeSegmented")?.addEventListener("click",e=>{const btn=e.target.closest("[data-theme-mode]");if(btn)setThemeMode(btn.dataset.themeMode)});
systemTheme.addEventListener("change",()=>{if(getThemeMode()==="system")applyTheme()});
$("#themeButton").onclick=()=>{const currentDark=document.documentElement.dataset.theme==="dark";setThemeMode(currentDark?"light":"dark")};
$("#settingsButton").onclick=()=>{const sMorph=$("#settingsMorphIcon");if(sMorph)morphConfirm(sMorph,"settings");openPage("settings")};
applyTheme();
(async()=>{const s=await api("/api/session");if(!s.authenticated)return showLogin();state.csrf=s.csrf_token;showShell();await loadShops();await Promise.all([loadOverview(),loadTrend()])})().catch(e=>toast(e.message,true));
