const $ = (s) => document.querySelector(s);
const state = {shop: 0, page: 1, total: 0, shops: [], csrf:"", overviewGranularity:"week", orderStatus:"", stockSort:{key:"",order:"desc"}, pages: {timeliness:1,returns:1,rfbsReturns:1,shippingComplaints:1,receivedDisputes:1,stock:1,analyticsData:1,productQueries:1,productQueryDetails:1}};
let riskItems = [];
let shippingComplaintItems=[],receivedDisputeItems=[];
let riskHighOnly = false;
let ruleData=null,mergeMemberIndex=0;
let pushSubscriptionState={},pushSubscriptionLoadToken=0;
const titles = {overview:"总览",orders:"订单",analytics:"流量与搜索分析",risk:"订单取消分析",timeliness:"发货与配送时效",returns:"异常订单明细",complaintPlaceholder:"异常订单投诉",stock:"销量与备货建议",profit:"利润测算",transfer:"数据导入/导出",sync:"数据同步中心",rules:"商品匹配规则",pushSubscriptions:"推送订阅管理",dingtalk:"钉钉机器人",settings:"系统设置"};
const profitCalculator = window.ProfitCalculator;
const profitCostLabels = {purchase_cost:"采购成本",cross_border_shipping:"跨境运费",last_mile_shipping:"末端运费",warehouse_fee:"仓库处理费",commission:"平台佣金",advertising:"广告费用",international_logistics:"国际组织物流费",bank_fee:"银行手续费",insurance:"保险",packing:"打包成本",other_cost:"其他费用"};
const profitPathLabels = {FBP:"FBP",realFBS_hongkong:"realFBS · 香港",realFBS_shenzhen:"realFBS · 深圳"};
const profitStatusLabels = {implemented:"已接入",missing_input:"待输入",not_implemented:"未接入规则"};
const syncNames = {orders:"订单",returns:"退货",stock:"库存"};
const PUSH_EVENT_FALLBACK_TYPES=[
  "TYPE_NEW_POSTING","TYPE_POSTING_CANCELLED","TYPE_STATE_CHANGED",
  "TYPE_FBO_POSTING_NEW","TYPE_FBO_POSTING_CANCELLED","TYPE_FBO_POSTING_STATE_CHANGED",
  "TYPE_STOCKS_CHANGED","TYPE_FBO_STOCKS_CHANGED","TYPE_ORDER_NEW",
  "TYPE_ORDER_CANCELLED","TYPE_ORDER_STATE_CHANGED"
];
const PUSH_EVENT_LABELS={
  TYPE_NEW_POSTING:"新建 FBS 货件",
  TYPE_POSTING_CANCELLED:"FBS 货件取消",
  TYPE_STATE_CHANGED:"FBS 货件状态变化",
  TYPE_FBO_POSTING_NEW:"新建 FBO 货件",
  TYPE_FBO_POSTING_CANCELLED:"FBO 货件取消",
  TYPE_FBO_POSTING_STATE_CHANGED:"FBO 货件状态变化",
  TYPE_STOCKS_CHANGED:"FBS 库存变化",
  TYPE_FBO_STOCKS_CHANGED:"FBO 库存变化",
  TYPE_ORDER_NEW:"新建订单",
  TYPE_ORDER_CANCELLED:"订单取消",
  TYPE_ORDER_STATE_CHANGED:"订单状态变化"
};
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const bj = (v) => { if (!v) return "暂无"; const date=new Date(v); return Number.isNaN(date.getTime()) ? "暂无" : new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(date).replaceAll("/","-"); };
const num = (v, digits=2) => Number(v || 0).toLocaleString("zh-CN",{maximumFractionDigits:digits});
const hours = (v) => v == null ? "暂无" : `${num(v,1)} 小时 / ${num(v/24,1)} 天`;
const money = (amount,currency) => amount==null ? "金额暂无" : `${num(amount)} ${esc(currency||"")}`;
const convertedMoney = (amount,currency) => `${Number(amount).toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2})} ${esc(currency||"")}`;
const cell = (v) => v == null || v === "" ? "暂无" : `<span class="copyable" data-copy="${esc(v)}" title="点击复制">${esc(v)}</span>`;
const channelTag = (v) => `<span class="tag channel-${({FBP:"fbp",realFBS:"fbs",WHD:"whd"}[v] || "")}">${esc(v)}</span>`;
const renderAnalysisCards = cards => cards.map(card => {
  const rawTone = card.tone || card.rateTone || "blue";
  const tone = { safe: "mint", danger: "peach", warning: "lavender", neutral: "blue", butter: "lavender" }[rawTone] || rawTone;
  const badge = card.badge || card.rate;
  return `<article class="metric ${tone}"><div class="metric-head"><span class="metric-title">${card.label}${badge ? `<span class="analysis-rate-badge">${badge}</span>` : ""}</span><div class="metric-icon-badge"><morph-icon icon="${card.icon}" size="18" stroke-width="1.8"></morph-icon></div></div><strong>${card.count}</strong><small>${card.note || ""}</small></article>`;
}).join("");
const returnSelects = {};
function createReturnSelect(id){
  const select=$(`#${id}`),root=select.closest("[data-return-select],[data-import-select]"),button=root.querySelector("[data-select-button]"),label=root.querySelector("[data-select-label]"),options=root.querySelector("[data-select-options]"),morph=button.querySelector("morph-icon");
  options.id=`${id}Options`;button.setAttribute("aria-controls",options.id);
  const close=()=>{options.classList.add("hidden");button.setAttribute("aria-expanded","false");morph?.morphTo("chevronDown")};
  const render=()=>{const selected=select.options[select.selectedIndex];label.textContent=selected?.textContent||"请选择";options.innerHTML=[...select.options].map(option=>`<button type="button" role="option" tabindex="-1" data-select-value="${esc(option.value)}" aria-selected="${option.selected}"><span class="option-label">${esc(option.textContent)}</span><morph-icon icon="check" size="12" stroke-width="2.2" class="option-check"></morph-icon></button>`).join("")};
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
const gmvText = (gmv) => {
  if (!gmv) return "GMV：—";
  if (gmv.missing_rate_orders) return `可折算GMV：¥${num(gmv.amount)}｜缺少汇率：${num(gmv.missing_rate_orders,0)}单`;
  const sym = gmv.currency === "CNY" ? "¥" : gmv.currency === "USD" ? "$" : "";
  return `GMV：${sym ? `${sym}${num(gmv.amount)}` : `${num(gmv.amount)} ${gmv.currency}`}`;
};
function trendTip(bucket){
  const isOngoing = bucket.orders === 0 && bucket.from === isoDate(new Date());
  const dateBase = bucket.from === bucket.to ? bucket.from : `${bucket.from} 至 ${bucket.to}`;
  const dateStr = esc(dateBase) + (isOngoing ? ` <span class="ozon-tip-badge">进行中</span>` : ``);
  const channels=[
    {key:"FBP",name:"FBP",color:"#0066CC"},
    {key:"realFBS",name:"realFBS",color:"#1B8255"},
    {key:"WHD",name:"WHD",color:"#B86614"}
  ];
  return `
    <div class="ozon-tip-head">${dateStr}</div>
    <div class="ozon-tip-main">
      <div class="ozon-tip-main-row">
        <span class="ozon-tip-dot" style="background:var(--primary,#0066CC)"></span>
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
    const tipWidth=252;

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
  const totalPieces=data.totals.pieces||0;
  const channels=data.channels||[];

  $("#channelGrid").innerHTML=channels.map(r=>{
    const percent=Math.min(100,Math.round((r.orders/totalOrders)*100));
    const channelClass=r.channel==="FBP"?"channel-fbp":r.channel==="realFBS"?"channel-fbs":"channel-whd";
    const channelCancelRate=r.pieces>0?(r.cancelled_pieces||0)/r.pieces:0;
    return `
      <div class="channel-card">
        <div class="channel-card-top">
          <div class="channel-card-brand">
            ${channelTag(r.channel)}
            <span class="channel-share-pct">订单占比 <b>${percent}</b>%</span>
          </div>
          <div class="channel-track-bar">
            <div class="channel-track-fill ${channelClass}" style="width:${percent}%"></div>
          </div>
        </div>
        <div class="channel-card-metrics">
          <div class="channel-metric-cell">
            <span class="cell-label">有效订单</span>
            <strong class="cell-val">${num(r.orders,0)}<small>单</small></strong>
          </div>
          <div class="channel-metric-cell">
            <span class="cell-label">有效货件</span>
            <strong class="cell-val">${num(r.pieces,0)}<small>件</small></strong>
          </div>
          <div class="channel-metric-cell risk">
            <span class="cell-label">发货后取消</span>
            <strong class="cell-val ${r.cancelled_pieces>0?'has-risk':''}">${num(r.cancelled_pieces||0,0)}<small>件</small></strong>
          </div>
          <div class="channel-metric-cell risk">
            <span class="cell-label">发货取消率</span>
            <strong class="cell-val ${channelCancelRate>0.05?'has-risk':''}">${pct(channelCancelRate)}</strong>
          </div>
        </div>
      </div>
    `;
  }).join("")||'<div class="overview-empty"><morph-icon icon="box" size="20" stroke-width="1.8"></morph-icon><span>暂无渠道数据</span></div>';

  const channelInsightsEl=$("#channelInsights");
  if(channelInsightsEl){
    const topChannel=[...channels].sort((a,b)=>(b.orders||0)-(a.orders||0))[0]||{channel:"—",orders:0,pieces:0};
    const topPercent=Math.min(100,Math.round(((topChannel.orders||0)/totalOrders)*100));
    const itemRatio=data.totals.orders>0?(totalPieces/data.totals.orders).toFixed(2):"1.00";
    const activeChannels=channels.filter(c=>(c.orders||0)>0);
    const bestChannel=activeChannels.length>0
      ?[...activeChannels].sort((a,b)=>((a.cancelled_pieces||0)/(a.pieces||1))-((b.cancelled_pieces||0)/(b.pieces||1)))[0]
      :null;
    const bestCancelRate=bestChannel&&bestChannel.pieces>0?(bestChannel.cancelled_pieces||0)/bestChannel.pieces:0;

    channelInsightsEl.innerHTML=`
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="award" size="14" stroke-width="1.8"></morph-icon>
          <span>主力履约渠道</span>
        </div>
        <strong>${esc(topChannel.channel)}<small>占比 ${topPercent}%</small></strong>
        <span class="trend-insight-foot">${num(topChannel.orders,0)}单 · ${num(topChannel.pieces,0)}件</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="package" size="14" stroke-width="1.8"></morph-icon>
          <span>综合货单比</span>
        </div>
        <strong>${itemRatio}<small>件/单</small></strong>
        <span class="trend-insight-foot">共 ${num(totalPieces,0)}件 · ${num(data.totals.orders,0)}单</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="shieldCheck" size="14" stroke-width="1.8"></morph-icon>
          <span>最优履约质量</span>
        </div>
        <strong>${bestChannel?esc(bestChannel.channel):"—"}<small>取消 ${pct(bestCancelRate)}</small></strong>
        <span class="trend-insight-foot ${bestCancelRate===0?'trend-up':''}">发货后取消 ${num(bestChannel?bestChannel.cancelled_pieces:0,0)}件</span>
      </div>
    `;
  }

  $("#overviewTimeliness").innerHTML=data.timeliness.map(row=>{
    const ship=row.ship_sample_insufficient
      ? '<span class="cell-insufficient">数据不足</span>'
      : `${num(row.p50_ship_hours,1)}<small>小时 / ${(row.p50_ship_hours/24).toFixed(1)}天</small>`;
    const delivery=row.delivery_sample_insufficient
      ? '<span class="cell-insufficient">数据不足</span>'
      : `${num(row.p50_delivery_hours,1)}<small>小时 / ${(row.p50_delivery_hours/24).toFixed(1)}天</small>`;
    const p90=row.delivery_sample_insufficient
      ? '<span class="cell-insufficient">数据不足</span>'
      : `${num(row.p90_delivery_hours,1)}<small>小时 / ${(row.p90_delivery_hours/24).toFixed(1)}天</small>`;

    return `
      <div class="overview-timing-card">
        <div class="timing-card-top">
          <div class="timing-card-brand">
            ${channelTag(row.channel)}
            <span class="timing-sample-note">出库样本 <b>${num(row.ship_samples,0)}</b> 单 · 交付 <b>${num(row.delivery_samples,0)}</b> 单</span>
          </div>
        </div>
        <div class="timing-card-metrics">
          <div class="channel-metric-cell">
            <span class="cell-label">发货 P50</span>
            <strong class="cell-val">${ship}</strong>
          </div>
          <div class="channel-metric-cell">
            <span class="cell-label">配送 P50</span>
            <strong class="cell-val">${delivery}</strong>
          </div>
          <div class="channel-metric-cell">
            <span class="cell-label">配送 P90</span>
            <strong class="cell-val">${p90}</strong>
          </div>
        </div>
      </div>
    `;
  }).join("")||'<div class="overview-empty"><morph-icon icon="clock" size="20" stroke-width="1.8"></morph-icon><span>暂无时效数据</span></div>';

  const timelinessInsightsEl=$("#timelinessInsights");
  if(timelinessInsightsEl){
    const validShip=(data.timeliness||[]).filter(r=>!r.ship_sample_insufficient&&r.p50_ship_hours!==null);
    const fastestShip=[...validShip].sort((a,b)=>a.p50_ship_hours-b.p50_ship_hours)[0];
    const totalShipSamples=(data.timeliness||[]).reduce((sum,r)=>sum+(r.ship_samples||0),0);
    const totalDeliverySamples=(data.timeliness||[]).reduce((sum,r)=>sum+(r.delivery_samples||0),0);

    timelinessInsightsEl.innerHTML=`
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="bolt" size="14" stroke-width="1.8"></morph-icon>
          <span>发货最快渠道</span>
        </div>
        <strong>${fastestShip?esc(fastestShip.channel):"—"}<small>${fastestShip?hours(fastestShip.p50_ship_hours):"样本积累中"}</small></strong>
        <span class="trend-insight-foot">${fastestShip?`约 ${(fastestShip.p50_ship_hours/24).toFixed(1)} 天内完成出库`:"各渠道正在积累发货数据"}</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="clock" size="14" stroke-width="1.8"></morph-icon>
          <span>配送时效追踪</span>
        </div>
        <strong>${totalDeliverySamples>0?`${num(totalDeliverySamples,0)}单`:"P50 / P90"}<small>${totalDeliverySamples>0?"已交付样本":"时效监控"}</small></strong>
        <span class="trend-insight-foot">${totalDeliverySamples>0?"持续监控末端签收周期":"监控全链路最后一公里交付"}</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="checkCircle" size="14" stroke-width="1.8"></morph-icon>
          <span>履约时效样本</span>
        </div>
        <strong>${num(totalShipSamples,0)}<small>单有效样本</small></strong>
        <span class="trend-insight-foot">已纳入 P50 / P90 建模</span>
      </div>
    `;
  }

  const topProducts=data.top_products||[];
  const maxPieces=Math.max(1,...topProducts.map(p=>p.pieces||0));
  $("#overviewTopProducts").innerHTML=topProducts.map((row,index)=>{
    const rankClass=index===0?"rank-gold":index===1?"rank-silver":index===2?"rank-bronze":"rank-normal";
    const barWidth=Math.max(4,Math.round((row.pieces/maxPieces)*100));
    return `<div class="overview-product-item"><div class="product-item-left"><span class="overview-rank ${rankClass}">${index+1}</span><div class="product-info"><strong class="product-name" title="${esc(row.name)}">${esc(row.name)}</strong><div class="product-progress-track"><div class="product-progress-fill" style="width:${barWidth}%"></div></div></div></div><div class="product-stats"><span class="stat-badge pieces"><b>${num(row.pieces,0)}</b>件</span><span class="stat-badge orders">${num(row.orders,0)}单</span><span class="stat-badge cancel ${row.cancel_rate>0.05?'is-warning':''}">取消 ${pct(row.cancel_rate)}</span></div></div>`;
  }).join("")||'<div class="overview-empty"><morph-icon icon="tag" size="20" stroke-width="1.8"></morph-icon><span>所选范围暂无商品数据</span></div>';

  const topProductsInsightsEl=$("#topProductsInsights");
  if(topProductsInsightsEl){
    const top5Pieces=topProducts.reduce((sum,p)=>sum+(p.pieces||0),0);
    const top1=topProducts[0]||{name:"—",pieces:0,orders:0};
    const top5Share=totalPieces>0?Math.min(100,Math.round((top5Pieces/totalPieces)*100)):0;
    const top5CancelPieces=topProducts.reduce((sum,p)=>sum+Math.round((p.pieces||0)*(p.cancel_rate||0)),0);
    const top5CancelRate=top5Pieces>0?top5CancelPieces/top5Pieces:0;

    topProductsInsightsEl.innerHTML=`
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="flame" size="14" stroke-width="1.8"></morph-icon>
          <span>Top 5 销量集中度</span>
        </div>
        <strong>${num(top5Pieces,0)}件<small>占比 ${top5Share}%</small></strong>
        <span class="trend-insight-foot">前 5 款核心爆品合计销量</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="award" size="14" stroke-width="1.8"></morph-icon>
          <span>榜首爆品销量</span>
        </div>
        <strong>${num(top1.pieces,0)}件<small>${num(top1.orders,0)}单</small></strong>
        <span class="trend-insight-foot">领跑全店单品销售表现</span>
      </div>
      <div class="trend-insight-card">
        <div class="trend-insight-head">
          <morph-icon icon="shieldCheck" size="14" stroke-width="1.8"></morph-icon>
          <span>Top 5 综合取消率</span>
        </div>
        <strong>${pct(top5CancelRate)}<small>${top5CancelRate<=0.05?"履约健康":"需关注"}</small></strong>
        <span class="trend-insight-foot ${top5CancelRate<=0.05?'trend-up':'trend-down'}">${top5CancelRate<=0.05?'爆品退订率处于健康水平':'部分爆品取消率偏高'}</span>
      </div>
    `;
  }
}

function renderDataThrough(raw){const el=$("#dataThrough");if(!el)return;const timeStr=raw?(raw.length===10?raw:bj(raw)):"暂无";el.innerHTML=`<span class="pulse-dot" aria-hidden="true"></span><span class="data-through-label">数据截止</span><span class="data-through-time">${esc(timeStr)}</span>`}
function pager(name, data, loader) {
  const pages=Math.max(1,Math.ceil(data.total/data.size));
  $(`#${name}Info`).textContent=`第 ${data.page} / ${pages} 页，共 ${data.total} 条`;
  $(`#${name}Prev`).disabled=data.page<=1; $(`#${name}Next`).disabled=data.page>=pages;
  $(`#${name}Prev`).onclick=()=>{state.pages[name]--;loader().catch(err=>toast(err.message,true))};
  $(`#${name}Next`).onclick=()=>{state.pages[name]++;loader().catch(err=>toast(err.message,true))};
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
function showConfirm(options) {
  const {
    title = "确认操作",
    message = typeof options === "string" ? options : "",
    confirmText = "确认开始",
    cancelText = "取消",
    icon = "alertTriangle"
  } = typeof options === "string" ? { message: options } : (options || {});
  const modal = $("#confirmModal");
  if (!modal) return Promise.resolve(window.confirm(message));
  $("#confirmTitle").textContent = title;
  $("#confirmMessage").textContent = message;
  $("#confirmOkButton").textContent = confirmText;
  $("#confirmCancelButton").textContent = cancelText;
  const iconEl = $("#confirmModalIcon");
  if (iconEl?.morphTo) iconEl.morphTo(icon, "snappy");
  return new Promise(resolve => {
    let done = false;
    const finish = res => {
      if (done) return;
      done = true;
      modal.close();
      resolve(res);
    };
    $("#confirmOkButton").onclick = () => finish(true);
    $("#confirmCancelButton").onclick = () => finish(false);
    modal.oncancel = e => { e.preventDefault(); finish(false); };
    modal.onclick = e => { if (e.target === modal) finish(false); };
    if (!modal.open) modal.showModal();
    $("#confirmOkButton").focus();
  });
}
function showLogin(){ $("#shell").classList.add("hidden"); $("#login").classList.remove("hidden"); }
function showShell(){ $("#login").classList.add("hidden"); $("#shell").classList.remove("hidden"); }

function applyShopSelection(shopId, animate = true) {
  state.shop = Number(shopId);
  state.page = 1;
  Object.keys(state.pages).forEach(k => state.pages[k] = 1);
  const shopObj = state.shops.find(s => s.id === state.shop);
  const name = shopObj ? shopObj.name : "两店铺合并";
  const valEl = $("#shopPickerValue");
  const iconEl = $("#shopPickerIcon");
  if (valEl) {
    valEl.textContent = name;
    if (animate) {
      valEl.classList.remove("shop-picker-swap");
      void valEl.offsetWidth;
      valEl.classList.add("shop-picker-swap");
    }
  }
  if (iconEl) {
    if (animate) {
      iconEl.classList.remove("shop-picker-icon-pop");
      void iconEl.offsetWidth;
      iconEl.classList.add("shop-picker-icon-pop");
    }
    iconEl.morphTo(state.shop === 0 ? "gitMerge" : "store", "snappy");
  }
}

async function loadShops() {
  state.shops = await api("/api/shops");
  const options = state.shops.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
  const importShop = $("#importShop").value;
  const shops = [{ id: 0, name: "两店铺合并" }, ...state.shops];
  $("#shopOptions").innerHTML = shops.map(s => `<button type="button" role="option" data-shop="${s.id}" data-name="${esc(s.name)}" aria-selected="${s.id === state.shop}"><span class="option-main"><morph-icon icon="${s.id === 0 ? 'gitMerge' : 'store'}" size="14" stroke-width="1.8"></morph-icon><span class="option-label">${esc(s.name)}</span></span><morph-icon icon="check" size="13" stroke-width="2.2" class="option-check"></morph-icon></button>`).join("");
  applyShopSelection(state.shop, false);
  $("#importShop").innerHTML = `<option value="">请选择</option>${options}`;
  $("#importShop").value = importShop;
  returnSelects.importShop?.render();
  $("#shop1").value = state.shops[0].name; $("#shop2").value = state.shops[1].name;
  renderProfitShopOptions();
}
function profitMoney(value, currency = "CNY") {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const symbol = currency === "USD" ? "$" : "¥";
  return `${symbol}${Number(value).toLocaleString("zh-CN", {minimumFractionDigits:2, maximumFractionDigits:2})}`;
}
function profitPercent(value) {
  return value == null || !Number.isFinite(Number(value)) ? "—" : `${(Number(value) * 100).toFixed(2)}%`;
}
function profitShopCurrency(shopId) {
  return Number(shopId) === 2 ? "CNY" : "USD";
}
function renderProfitShopOptions() {
  const select = $("#profitShop");
  if (!select || !state.shops.length) return;
  const current = Number(select.value || 1);
  const shops = state.shops.filter(shop => [1, 2].includes(Number(shop.id)));
  if (!shops.length) return;
  select.innerHTML = shops.map(shop => `<option value="${shop.id}">${esc(shop.name)} · ${profitShopCurrency(shop.id)}</option>`).join("");
  select.value = String(shops.find(shop => Number(shop.id) === current)?.id || shops[0].id);
}
function renderProfitCalculator() {
  if (!profitCalculator || !$("#profitForm")) return;
  const fulfillmentMode = $("#profitFulfillment").value;
  const realFbs = fulfillmentMode === "realFBS";
  const channelField = $("#profitChannelField");
  const channel = $("#profitChannel");
  channelField.classList.toggle("hidden", !realFbs);
  channel.disabled = !realFbs;

  const result = profitCalculator.calculateProfit({
    shopId: Number($("#profitShop").value),
    priceOriginal: $("#profitPrice").value,
    purchasePriceUsd: $("#profitPurchasePrice").value,
    weightGrams: $("#profitWeight").value,
    usdCnyRate: $("#profitRate").value,
    fulfillmentMode,
    realFbsChannel: channel.value
  });
  const currency = result.price_currency;
  const isCny = currency === "CNY";
  $("#profitPriceCurrency").textContent = currency || "—";
  $("#profitPricePrefix").textContent = isCny ? "¥" : "$";
  $("#profitPriceUsdLabel").textContent = isCny ? "美元等值" : "美元售价";
  $("#profitPriceCnyLabel").textContent = isCny ? "人民币售价" : "人民币等值";
  $("#profitPriceUsd").textContent = profitMoney(result.price_usd, "USD");
  $("#profitPriceCny").textContent = profitMoney(result.price_cny);
  $("#profitPathBadge").textContent = profitPathLabels[result.fulfillment_path] || result.fulfillment_path;
  $("#profitCostRows").innerHTML = profitCalculator.COST_KEYS.map(key => {
    const cost = result.costs[key];
    const implemented = cost.status === "implemented";
    return `<div class="profit-cost-row"><div class="profit-cost-label"><strong>${profitCostLabels[key]}</strong><small>${profitStatusLabels[cost.status]}</small></div><strong class="profit-cost-value ${implemented ? "" : "is-pending"}">${implemented ? profitMoney(cost.value) : "—"}</strong></div>`;
  }).join("");
  $("#profitRevenue").textContent = profitMoney(result.revenue_cny);
  $("#profitTotalCost").textContent = profitMoney(result.total_cost_cny);
  $("#profitAmount").textContent = profitMoney(result.profit_cny);
  $("#profitMargin").textContent = profitPercent(result.net_margin);
  $("#profitSummaryNote").textContent = result.profit_cny === null
    ? "请输入有效的平台售价、采购价格和测算汇率；部分费用规则尚未接入。"
    : "当前仅包含已接入费用：采购成本；部分费用规则尚未接入。";
}
function loadProfitPage() {
  renderProfitShopOptions();
  renderProfitCalculator();
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
  const gmv = data.gmv;
  const gmvEl = $("#totalGmv");
  if (gmvEl && gmv) {
    const symbol = gmv.currency === "CNY" ? "¥" : gmv.currency === "USD" ? "$" : "";
    gmvEl.textContent = symbol ? `${symbol}${num(gmv.amount)}` : `${num(gmv.amount)} ${gmv.currency}`;
    const gmvSub = $("#gmvSub");
    if (gmvSub) {
      gmvSub.textContent = gmv.missing_rate_orders
        ? `可折算GMV · 缺汇率 ${num(gmv.missing_rate_orders, 0)} 单`
        : "有效订单总成交额";
    }
  }
  $("#totalOrders").textContent=num(t.orders,0);
  $("#totalPieces").textContent=num(t.pieces,0);
  $("#cancelOrders").textContent=num(t.cancelled_orders,0);
  const cancelRateEl = $("#cancelRate");
  if (cancelRateEl) {
    cancelRateEl.textContent=pct(t.cancel_rate);
    cancelRateEl.classList.toggle("is-warning", t.cancel_rate > 0.05);
  }
  renderDataThrough(data.data_through);
  renderOverviewPanels(data);
}
let analyticsTab="traffic", analyticsDetail=null, productQueryItems=[];
const analyticsRate=(value,denominator)=>denominator?`${(Number(value)/Number(denominator)*100).toFixed(2)}%`:"—";
const analyticsApiRate=value=>value==null?"—":`${num(value)}%`;
const analyticsMessage=(target,colspan,message,loading=false)=>{$(target).innerHTML=`<tr><td colspan="${colspan}" class="analytics-message">${loading?'<morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon>':'<morph-icon icon="alertCircle" size="18" stroke-width="1.8"></morph-icon>'}<span>${esc(message)}</span></td></tr>`};
function analyticsError(error){const root=$("#analyticsError");root.textContent=error?.message||String(error);root.classList.remove("hidden")}
function clearAnalyticsError(){$("#analyticsError").classList.add("hidden")}
function analyticsQuery(page){return new URLSearchParams({shop_id:state.shop,sku:$("#analyticsSku").value.trim(),page,from:analyticsRange.start,to:analyticsRange.end})}
function loadAnalyticsPage(){return analyticsTab==="traffic"?loadAnalyticsData():loadProductQueries()}
async function loadAnalyticsData(){
  clearAnalyticsError();analyticsMessage("#analyticsRows",11,"流量转化数据加载中…",true);
  try{
    const data=await api(`/api/analytics/data?${analyticsQuery(state.pages.analyticsData)}`),shops=data.shops||[];
    const total=key=>shops.reduce((sum,row)=>sum+Number(row[key]||0),0);
    const revenue=shops.length?shops.map(row=>`<span>${esc(row.shop_name)}：${num(row.revenue)} ${esc(row.currency)}</span>`).join(""):"—";
    $("#analyticsSummary").innerHTML=renderAnalysisCards([
      {icon:"search",label:"曝光量",count:num(total("impressions"),0),tone:"azure"},
      {icon:"package",label:"商品详情浏览量",count:num(total("product_views"),0),tone:"lavender"},
      {icon:"activity",label:"独立访客",count:num(total("unique_visitors"),0),tone:"mint"},
      {icon:"shoppingBag",label:"加购量",count:num(total("cart_adds"),0),tone:"peach"},
      {icon:"orders",label:"下单件数",count:num(total("ordered_units"),0),tone:"blue"},
      {icon:"wallet",label:"成交金额",count:`<span class="analytics-money-lines">${revenue}</span>`,note:"按店铺／币种分开展示",tone:"azure"},
      {icon:"trendingUp",label:"曝光→浏览",count:analyticsRate(total("product_views"),total("impressions")),tone:"lavender"},
      {icon:"percent",label:"浏览→加购 ／ 加购→下单",count:`${analyticsRate(total("cart_adds"),total("product_views"))} ／ ${analyticsRate(total("ordered_units"),total("cart_adds"))}`,tone:"mint"}
    ]);
    $("#analyticsRows").innerHTML=data.items.length?data.items.map(row=>`<tr><td><span class="shop-tag">${esc(row.shop_name)}</span><strong class="analytics-sku">${esc(row.sku)}</strong></td><td title="${esc(row.name)}">${esc(row.name||"—")}</td><td class="text-right">${num(row.impressions,0)}</td><td class="text-right">${num(row.product_views,0)}</td><td class="text-right">${num(row.unique_visitors,0)}</td><td class="text-right">${num(row.cart_adds,0)}</td><td class="text-right">${num(row.ordered_units,0)}</td><td class="text-right">${num(row.revenue)} ${esc(row.currency)}</td><td class="text-right">${analyticsRate(row.product_views,row.impressions)}</td><td class="text-right">${analyticsRate(row.cart_adds,row.product_views)}</td><td class="text-right">${analyticsRate(row.ordered_units,row.cart_adds)}</td></tr>`).join(""):`<tr><td colspan="11" class="analytics-message">该条件下暂无流量数据</td></tr>`;
    pager("analyticsData",data,loadAnalyticsData);
  }catch(error){$("#analyticsSummary").innerHTML="";analyticsMessage("#analyticsRows",11,error.message);analyticsError(error)}
}
async function loadProductQueries(){
  clearAnalyticsError();analyticsDetail=null;$("#queryDetailPanel").classList.add("hidden");analyticsMessage("#productQueryRows",8,"商品搜索表现加载中…",true);
  try{
    const data=await api(`/api/analytics/product-queries?${analyticsQuery(state.pages.productQueries)}`);productQueryItems=data.items;
    $("#productQueryRows").innerHTML=data.items.length?data.items.map((row,index)=>`<tr><td><span class="shop-tag">${esc(row.shop_name)}</span><strong class="analytics-sku">${esc(row.sku)}</strong></td><td><strong>${esc(row.name||"—")}</strong><small class="analytics-offer">${esc(row.offer_id||"—")}</small></td><td class="text-right">${row.position==null?"—":num(row.position)}</td><td class="text-right">${num(row.unique_search_users,0)}</td><td class="text-right">${num(row.unique_view_users,0)}</td><td class="text-right">${analyticsApiRate(row.view_conversion)}</td><td class="text-right">${row.gmv==null?"—":`${num(row.gmv)} ${esc(row.currency)}`}</td><td><button type="button" class="analytics-detail-button" data-query-detail="${index}">查看关键词</button></td></tr>`).join(""):`<tr><td colspan="8" class="analytics-message">该条件下暂无搜索表现数据</td></tr>`;
    pager("productQueries",data,loadProductQueries);
  }catch(error){analyticsMessage("#productQueryRows",8,error.message);analyticsError(error)}
}
async function loadProductQueryDetails(){
  if(!analyticsDetail)return;
  clearAnalyticsError();$("#queryDetailPanel").classList.remove("hidden");analyticsMessage("#queryDetailRows",7,"搜索关键词加载中…",true);
  $("#queryDetailTitle").innerHTML=`<morph-icon icon="fileText" size="18" stroke-width="1.8"></morph-icon> ${esc(analyticsDetail.shop_name)} · ${esc(analyticsDetail.sku)} 搜索关键词`;
  const query=new URLSearchParams({shop_id:analyticsDetail.shop_id,sku:analyticsDetail.sku,page:state.pages.productQueryDetails,from:analyticsRange.start,to:analyticsRange.end});
  try{
    const data=await api(`/api/analytics/product-queries/details?${query}`);
    $("#queryDetailRows").innerHTML=data.items.length?data.items.map(row=>`<tr><td>${esc(row.query||"—")}</td><td class="text-right">${row.position==null?"—":num(row.position)}</td><td class="text-right">${num(row.unique_search_users,0)}</td><td class="text-right">${num(row.unique_view_users,0)}</td><td class="text-right">${analyticsApiRate(row.view_conversion)}</td><td class="text-right">${num(row.order_count,0)}</td><td class="text-right">${row.gmv==null?"—":`${num(row.gmv)} ${esc(row.currency)}`}</td></tr>`).join(""):`<tr><td colspan="7" class="analytics-message">该 SKU 暂无关键词明细</td></tr>`;
    pager("productQueryDetails",data,loadProductQueryDetails);
  }catch(error){analyticsMessage("#queryDetailRows",7,error.message);analyticsError(error)}
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
                <small class="milestone-note">${deliveryDur ? `配送耗时 ${hours(deliveryDur)}` : (o.delivered_at ? "已签收" : o.status_raw === "已取消" ? "订单已取消" : o.shipped_at ? "配送中" : "待发货")}</small>
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
  currentExpandedReason = null;
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
    `).join("") || '<tr><td colspan="5" class="risk-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前范围内暂无发货后取消原因</span></td></tr>';
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
    q: $("#timelinessSearch").value.trim(),
    from: timelinessRange.start,
    to: timelinessRange.end
  });
  $("#timelinessGroupRows").innerHTML = '<tr><td colspan="4" class="timeliness-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>时效统计加载中…</span></td></tr>';
  $("#timelinessRows").innerHTML = '<tr><td colspan="5" class="timeliness-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>订单明细加载中…</span></td></tr>';
  try {
    const data = await api(`/api/timeliness?${query}`), s = data.summary;
    $("#timelinessSummary").innerHTML = renderAnalysisCards([
      {
        icon: "orders",
        label: "有效订单数",
        count: `${num(s.orders, 0)} 单`,
        badge: "全量统计",
        tone: "neutral",
        note: "当前店铺与筛选时间范围内有效订单"
      },
      {
        icon: "box",
        label: "实际发货有效样本",
        count: `${num(s.ship_samples, 0)} 单`,
        badge: s.orders ? `${pct(s.ship_samples / s.orders)} 样本率` : null,
        tone: "safe",
        note: "含真实且有效的实际出库时间"
      },
      {
        icon: "clock",
        label: "发货出库时效 P50",
        count: s.ship_samples ? hours(s.p50_ship_hours) : "数据不足",
        badge: s.ship_samples ? "中位数" : null,
        tone: s.ship_samples && s.p50_ship_hours <= 24 ? "safe" : s.ship_samples && s.p50_ship_hours <= 48 ? "warning" : "danger",
        note: "50% 的订单在此时间内完成出库发货"
      },
      {
        icon: "truck",
        label: "在途配送时效 P50",
        count: s.delivery_samples ? hours(s.p50_delivery_hours) : "数据不足",
        badge: s.delivery_samples ? "中位数" : null,
        tone: "lavender",
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
            <span class="complete-total">有效订单 <b>${num(r.orders, 0)}</b> 单</span>
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
        ${timelinessStatCell("发货出库时效", r.ship_samples, r.ship_sample_insufficient, r.p50_ship_hours, r.avg_ship_hours, r.p90_ship_hours, "ship")}
        ${timelinessStatCell("在途配送时效", r.delivery_samples, r.delivery_sample_insufficient, r.p50_delivery_hours, r.avg_delivery_hours, r.p90_delivery_hours, "delivery")}
      </tr>
    `).join("") || '<tr><td colspan="4" class="timeliness-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前范围内暂无有效订单</span></td></tr>';

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
        <td data-label="订购时间" class="timeliness-cell-time">${bj(r.created_at)}</td>
        ${timelinessDetailCell("实际发货／出库耗时", r.shipped_at, r.ship_hours, r.ship_anomaly, "ship")}
        ${timelinessDetailCell("实际签收／在途耗时", r.delivered_at, r.delivery_hours, r.delivery_anomaly, "delivery")}
      </tr>
    `).join("") || '<tr><td colspan="5" class="timeliness-empty"><morph-icon icon="truck" size="20" stroke-width="1.5"></morph-icon><span>没有匹配的订单时效明细</span></td></tr>';

    pager("timeliness", data, loadTimeliness);
  } catch (error) {
    $("#timelinessSummary").innerHTML = "";
    $("#timelinessGroupRows").innerHTML = `<tr><td colspan="4" class="timeliness-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    $("#timelinessRows").innerHTML = `<tr><td colspan="5" class="timeliness-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
}
function timelinessStatCell(label, samples, insufficient, p50, average, p90, type) {
  if (!samples) {
    return `
      <td class="timeliness-stat" data-label="${label}">
        <div class="timeliness-stat-empty">
          <morph-icon icon="clock" size="13" stroke-width="1.8"></morph-icon>
          <span>暂无有效样本</span>
        </div>
      </td>
    `;
  }
  const tone = type === "ship"
    ? (p50 != null && p50 <= 24 ? "tone-safe" : p50 != null && p50 <= 48 ? "tone-warning" : "tone-danger")
    : "tone-lavender";
  return `
    <td class="timeliness-stat" data-label="${label}">
      <div class="timeliness-stat-wrap">
        <div class="timeliness-p50-row">
          <span class="p50-badge ${tone}">
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
          <span class="time-chip chip-empty">${type === "ship" ? "待发货 / 暂无出库记录" : "运输中 / 暂无签收记录"}</span>
        </div>
      </td>
    `;
  }
  let tone = "normal";
  if (type === "ship") {
    tone = duration != null && duration <= 24 ? "fast" : duration != null && duration <= 48 ? "normal" : "slow";
  } else {
    tone = duration != null && duration <= 120 ? "lavender" : "normal";
  }
  return `
    <td class="timeliness-detail-time" data-label="${label}">
      <div class="time-cell-wrap">
        <strong class="time-cell-dt">${bj(value)}</strong>
        <span class="time-chip chip-${tone}">
          <morph-icon icon="${tone === 'fast' || tone === 'lavender' ? 'zap' : 'clock'}" size="11" stroke-width="2"></morph-icon>
          ${duration == null ? "数据异常" : `耗时 ${hours(duration)}`}
        </span>
      </div>
    </td>
  `;
}
function rfbsStatusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("approved") || s.includes("accepted") || s.includes("delivered") || s.includes("同意") || s.includes("已接收") || s.includes("已批准") || s.includes("完成") || s.includes("已签收")) return "mint";
  if (s.includes("rejected") || s.includes("declined") || s.includes("dispute") || s.includes("cancelled") || s.includes("拒绝") || s.includes("争议") || s.includes("取消")) return "peach";
  if (s.includes("pending") || s.includes("progress") || s.includes("审核") || s.includes("审批") || s.includes("处理中") || s.includes("在途") || s.includes("退回中")) return "butter";
  return "lavender";
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
        <td data-label="店铺与取消时间">
          <div class="return-shop-time">
            <span class="return-shop-badge">${esc(r.shop_name)}</span>
            <span class="return-time-text">${bj(r.cancelled_at||r.occurred_at)}</span>
            ${deadlineLine(r)}
          </div>
        </td>
        <td data-label="订单号">
          <strong class="copyable return-order-num" data-copy="${esc(r.posting_number)}" title="点击复制订单号">
            <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
            <span>${esc(r.posting_number)}</span>
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
        <td class="text-right" data-label="取消件数">
          <span class="return-qty-badge peach"><b>${num(r.quantity, 0)}</b> 件</span>
        </td>
        <td data-label="取消原因与状态">
          <div class="return-reason-cell">
            <span class="return-reason-chip" title="${esc(r.reason_raw)}">${esc(r.reason || r.reason_raw || '—')}</span>
            <span class="return-status-sub">${esc(r.status || r.type || '已取消')}</span>
          </div>
        </td>
      </tr>
    `).join("") || '<tr><td colspan="5" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有取消记录</span></td></tr>';

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
        tone: "lavender",
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
        <td data-label="店铺与申请时间">
          <div class="return-shop-time">
            <span class="return-shop-badge">${esc(r.shop_name)}</span>
            <span class="return-time-text">${bj(r.created_at)}</span>
            ${deadlineLine(r)}
          </div>
        </td>
        <td data-label="申请编号与订单号">
          <div class="return-ident-cell">
            <strong class="copyable return-ret-num" data-copy="${esc(r.return_number)}" title="点击复制申请编号">
              <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
              <span>${esc(r.return_number)}</span>
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
        <td data-label="状态与赔偿">
          <div class="return-state-cell">
            <span class="return-status-pill tone-${rfbsStatusTone(r.status_raw || r.status_name)}">
              ${esc(r.status_name || r.status_raw || '待处理')}
            </span>
            <small class="return-comp-text">退款：<b>${r.refund_amount==null?'—':money(r.refund_amount,r.refund_currency)}</b></small>
            <small class="return-comp-text">${compensationLine(r,'platform_compensation','平台赔偿','RUB')}</small>
            <small class="return-comp-text">${compensationLine(r,'logistics_compensation','物流商赔偿','CNY')}</small>
          </div>
        </td>
        <td class="text-right" data-label="件数与金额">
          <div class="return-qty-money">
            <span class="return-qty-badge neutral"><b>${num(r.quantity, 0)}</b> 件</span>
            <strong class="return-money-text">${money(r.product_amount, r.product_currency)}</strong>
          </div>
        </td>
        <td data-label="原因与退件跟踪">
          <div class="return-reason-logistics">
            <span class="return-reason-chip" title="${esc(r.reason_raw)}">${esc(r.reason_name || r.reason_raw || '平台未提供原因')}</span>
            <span class="return-logistics-sub">退货方式：<b>${esc(r.return_method || '—')}</b></span>
            <span class="return-logistics-sub">退件结果：<b>${esc(r.return_result || '—')}</b></span>
            ${r.buyer_comment_raw ? `
              <details class="return-buyer-bubble">
                <summary><morph-icon icon="messageSquare" size="11" stroke-width="2"></morph-icon> 买家留言原文</summary>
                <p lang="ru">${esc(r.buyer_comment_raw)}</p>
              </details>
            ` : ""}
          </div>
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有退货申请</span></td></tr>';

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
const deadlineIcons={overdue:"alertCircle",due_today:"clock",due_soon:"clock"};
const deadlineLine=row=>{if(!row.complaint_deadline&&!row.complaint_deadline_status)return "";const status=row.complaint_deadline_status||"missing",icon=deadlineIcons[status]||"clock";return `<span class="complaint-deadline ${esc(status)}"><morph-icon icon="${icon}" size="10.5" stroke-width="2"></morph-icon><span>投诉截止：${esc(row.complaint_deadline||'—')}</span>${deadlineLabels[status]?` <b>${deadlineLabels[status]}</b>`:""}</span>`};
const deadlineText=row=>`投诉截止：${row.complaint_deadline||'—'}${deadlineLabels[row.complaint_deadline_status]?` · ${deadlineLabels[row.complaint_deadline_status]}`:""}`;
function activateExceptionTab(name,focus=false){
  document.querySelectorAll("[data-exception-tab]").forEach(button=>{const active=button.dataset.exceptionTab===name;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus()});
  document.querySelectorAll(".exception-tab").forEach(panel=>{const active=panel.id===`exception-${name}`;panel.classList.toggle("active",active);panel.hidden=!active});
}
async function loadShippingComplaints(){
  $("#shippingComplaintRows").innerHTML='<tr><td colspan="5" class="return-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>发货未收货投诉加载中…</span></td></tr>';
  const query=new URLSearchParams({shop_id:state.shop,page:state.pages.shippingComplaints,q:$("#shippingComplaintQuery").value,status:$("#shippingComplaintStatus").value,from:complaintRange.start,to:complaintRange.end});
  const data=await api(`/api/exception-complaints/shipping?${query}`);
  shippingComplaintItems=data.items;
  $("#shippingComplaintCount").textContent=num(data.total,0);
  $("#shippingComplaintRows").innerHTML=data.items.map((row,index)=>{
    const first=row.items[0]||{},quantity=row.items.reduce((sum,item)=>sum+Number(item.quantity||0),0),complaints=row.complaints||[];
    return `<tr>
      <td data-label="店铺与订单">
        <div class="return-shop-time">
          <span class="return-shop-badge">${esc(row.shop_name)}</span>
          <strong class="copyable return-order-num" data-copy="${esc(row.posting_number)}" title="点击复制订单号">
            <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
            <span>${esc(row.posting_number)}</span>
          </strong>
          ${row.data_anomaly?'<span class="return-status-pill tone-butter"><morph-icon icon="alertTriangle" size="11" stroke-width="2"></morph-icon>数据异常</span>':""}
        </div>
      </td>
      <td data-label="物流与时效">
        <div class="return-ident-cell">
          <strong class="return-ret-num copyable" data-copy="${esc(row.tracking_number||'')}" title="点击复制物流单号">
            <morph-icon icon="truck" size="12" stroke-width="2"></morph-icon>
            <span>${esc(row.tracking_number||'—')}</span>
          </strong>
          <span class="return-time-text">下单：${bj(row.created_at)}</span>
          <span class="return-time-text">发货：${row.shipped_at?bj(row.shipped_at):'—'}</span>
          <span class="return-time-text">取消：${row.cancelled_at?bj(row.cancelled_at):'—'}</span>
          ${deadlineLine(row)}
        </div>
      </td>
      <td data-label="商品信息">
        <div class="return-product-cell">
          <span class="return-product-title" title="${esc(first.product_name)}">${esc(first.product_name||'产品名称暂无')}</span>
          <div class="return-sku-chips">
            <span class="return-sku-chip"><span class="sub-label">SKU</span> <b>${esc(first.sku||'—')}</b></span>
            <span class="return-sku-chip"><span class="sub-label">货号</span> <b>${esc(first.offer_id||'—')}</b></span>
            <span class="return-qty-badge neutral"><b>${num(quantity,0)}</b> 件${row.items.length>1?` · 另有 ${row.items.length-1} 种`:""}</span>
          </div>
        </div>
      </td>
      <td class="text-right" data-label="金额与取消原因">
        <div class="return-qty-money">
          <strong class="return-money-text">${row.amount_original==null?'—':money(row.amount_original,row.amount_currency)}</strong>
          <span class="return-reason-chip" title="${esc(row.cancel_reason_raw)}">${esc(row.cancel_reason||row.cancel_reason_raw||'原因暂缺')}</span>
        </div>
      </td>
      <td class="text-right" data-label="投诉记录与操作">
        <div class="exception-action-cell">
          <div class="exception-record-list">
            ${complaints.map((c,i)=>`<button type="button" data-edit-shipping="${index}:${i}" title="点击查看/编辑投诉明细">
              <strong><morph-icon icon="fileText" size="11" stroke-width="2"></morph-icon>${esc(c.complaint_number)}</strong>
              <small>${c.resolved===1?'<span class="return-status-pill tone-mint" style="font-size:10px;padding:1px 5px;">已完结</span>':'<span class="return-status-pill tone-butter" style="font-size:10px;padding:1px 5px;">处理中</span>'} · ${bj(c.complaint_at)}</small>
            </button>`).join("")||'<span class="muted" style="font-size:11.5px;">未创建投诉</span>'}
          </div>
          <button type="button" class="rule-act-btn" data-new-shipping="${index}"><morph-icon icon="plus" size="12" stroke-width="2"></morph-icon>新建投诉</button>
        </div>
      </td>
    </tr>`}).join("")||'<tr><td colspan="5" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有候选订单</span></td></tr>';
  pager("shippingComplaints",data,loadShippingComplaints);
}
async function loadReceivedDisputes(){
  $("#receivedDisputeRows").innerHTML='<tr><td colspan="5" class="return-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>已收货纠纷加载中…</span></td></tr>';
  const query=new URLSearchParams({shop_id:state.shop,page:state.pages.receivedDisputes,q:$("#receivedDisputeQuery").value,status:$("#receivedDisputeStatus").value,from:complaintRange.start,to:complaintRange.end});
  const data=await api(`/api/exception-complaints/received?${query}`);
  receivedDisputeItems=data.items;
  $("#receivedDisputeCount").textContent=num(data.total,0);
  $("#receivedDisputeRows").innerHTML=data.items.map((row,index)=>`<tr>
    <td data-label="店铺与退货申请">
      <div class="return-shop-time">
        <span class="return-shop-badge">${esc(row.shop_name)}</span>
        <strong class="copyable return-ret-num" data-copy="${esc(row.return_number)}" title="点击复制申请编号">
          <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
          <span>${esc(row.return_number)}</span>
        </strong>
        <span class="return-time-text">申请：${bj(row.created_at)}</span>
        ${deadlineLine(row)}
      </div>
    </td>
    <td data-label="订单与商品">
      <div class="return-product-cell">
        <strong class="copyable return-order-num" data-copy="${esc(row.posting_number)}" title="点击复制订单号">
          <morph-icon icon="package" size="12" stroke-width="2"></morph-icon>
          <span>${esc(row.posting_number)}</span>
        </strong>
        <span class="return-product-title" title="${esc(row.product_name)}">${esc(row.product_name||'产品名称暂无')}</span>
        <div class="return-sku-chips">
          <span class="return-sku-chip"><span class="sub-label">SKU</span> <b>${esc(row.sku||'—')}</b></span>
          <span class="return-sku-chip"><span class="sub-label">货号</span> <b>${esc(row.offer_id||'—')}</b></span>
        </div>
      </div>
    </td>
    <td data-label="金额与纠纷原因">
      <div class="return-reason-logistics">
        <strong class="return-money-text">${row.product_amount==null?'—':money(row.product_amount,row.product_currency)}</strong>
        <span class="return-reason-chip" title="${esc(row.reason_raw)}">${esc(row.reason_name||row.reason_raw||'平台未提供原因')}</span>
        ${row.buyer_comment_raw?`<details class="return-buyer-bubble"><summary><morph-icon icon="messageSquare" size="11" stroke-width="2"></morph-icon> 买家留言原文</summary><p lang="ru">${esc(row.buyer_comment_raw)}</p></details>`:""}
      </div>
    </td>
    <td data-label="退款与赔偿">
      <div class="return-state-cell">
        ${row.refund_type?`<span class="return-status-pill tone-lavender">${esc(row.refund_type)}</span>`:""}
        <small class="return-comp-text">退款：<b>${row.refund_amount==null?'—':money(row.refund_amount,row.refund_currency)}</b></small>
        <small class="return-comp-text">${compensationLine(row,'platform_compensation','平台赔偿','RUB')}</small>
        <small class="return-comp-text">${compensationLine(row,'logistics_compensation','物流商赔偿','CNY')}</small>
        <small class="return-comp-text">退货方式：<b>${esc(row.return_method||'—')}</b></small>
      </div>
    </td>
    <td class="text-right" data-label="处理状态与操作">
      <div class="exception-action-cell">
        <div class="return-state-cell">
          <span class="return-status-pill tone-${rfbsStatusTone(row.process_status||'待处理')}">${esc(row.process_status||'未记录')}</span>
          <span class="return-logistics-sub">方式：<b>${esc(row.handling_method||'—')}</b></span>
          <span class="return-logistics-sub">结果：<b>${esc(row.return_result||'—')}</b></span>
        </div>
        <button type="button" class="rule-act-btn" data-edit-received="${index}"><morph-icon icon="edit" size="12" stroke-width="2"></morph-icon>编辑</button>
      </div>
    </td>
  </tr>`).join("")||'<tr><td colspan="5" class="return-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选范围内没有退货申请</span></td></tr>';
  pager("receivedDisputes",data,loadReceivedDisputes);
}
const loadExceptionComplaints=()=>Promise.all([loadShippingComplaints(),loadReceivedDisputes()]);
async function loadStock() {
  $("#stockRows").innerHTML = '<tr><td colspan="7" class="stock-empty"><morph-icon icon="sync" size="18" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>库存数据加载中…</span></td></tr>';
  try {
    const query = new URLSearchParams({
      shop_id: state.shop,
      page: state.pages.stock,
      sku: $("#stockSku").value,
      offer_id: $("#stockOffer").value,
      product_name: $("#stockProduct").value,
      sort_by: state.stockSort.key,
      sort_order: state.stockSort.order
    });
    const data = await api(`/api/stock?${query}`);
    document.querySelectorAll("[data-stock-sort-column]").forEach(th => {
      const active = th.dataset.stockSortColumn === state.stockSort.key;
      th.setAttribute("aria-sort", active ? (state.stockSort.order === "asc" ? "ascending" : "descending") : "none");
      const morph = th.querySelector("morph-icon");
      if (morph) morph.morphTo(active ? (state.stockSort.order === "asc" ? "arrowUp" : "arrowDown") : "sortUpDown", "snappy");
    });
    const s = data.summary;
    $("#stockSummary").innerHTML = renderAnalysisCards([
      {
        icon: "package",
        label: "在售与备货 SKU",
        count: `${num(s.active_skus, 0)} 款`,
        rate: null,
        tone: "azure",
        note: "当前筛选条件下的全部商品"
      },
      {
        icon: "box",
        label: "FBP 可售现货",
        count: `${num(s.fbp_present, 0)} 件`,
        rate: null,
        tone: "safe",
        note: "FBP 仓库当前可售现货总数"
      },
      {
        icon: "clock",
        label: "FBP 锁定预留",
        count: `${num(s.fbp_reserved, 0)} 件`,
        rate: null,
        tone: "lavender",
        note: "买家下单已占用的预留库存"
      },
      {
        icon: "shoppingBag",
        label: "建议备货 SKU",
        count: `${num(s.replenishment_skus, 0)} 款`,
        rate: null,
        tone: (s.replenishment_skus || 0) > 0 ? "warning" : "safe",
        note: "可售天数 < 90 天，建议启动备货"
      },
      {
        icon: "alertTriangle",
        label: "预计缺货预警",
        count: `${num(s.shortage_skus, 0)} 款`,
        rate: null,
        tone: (s.shortage_skus || 0) > 0 ? "danger" : "safe",
        note: "可售天数 < 30 天或零库存严重缺货"
      }
    ]);
    $("#stockUpdated").textContent = `库存更新至 ${bj(data.data_through)}｜销量更新至 ${bj(data.sales_through)}`;
    const inventory = (c, cls) => `
      <div class="stock-channel-box ${cls}">
        <strong class="stock-qty-val ${c.present > 0 ? '' : 'zero'}">${num(c.present, 0)}</strong>
        <small class="stock-qty-sub">预留 <b>${num(c.reserved, 0)}</b></small>
      </div>`;
    $("#stockRows").innerHTML = data.items.map(r => {
      const riskTone = r.daily_sales <= 0 ? "neutral" : r.days_available < 30 ? "peach" : r.days_available < 90 ? "butter" : "mint";
      const riskIcon = r.daily_sales <= 0 ? "helpCircle" : r.days_available < 30 ? "alertTriangle" : r.days_available < 90 ? "clock" : "check";
      return `<tr>
        <td class="stock-product-cell" data-label="商品信息">
          <strong class="stock-product-name" title="${esc(r.display_name)}">${esc(r.display_name)}</strong>
          ${r.short_name && r.product_name_raw ? `<small class="stock-raw-name" title="${esc(r.product_name_raw)}">原名 ${esc(r.product_name_raw)}</small>` : ""}
          <div class="stock-meta-chips">
            <span class="stock-shop-badge">${esc(r.shop_name)}</span>
            <span class="stock-meta-chip"><span class="sub-label">SKU</span> <span class="copyable" data-copy="${esc(r.sku)}" title="点击复制 SKU"><b>${esc(r.sku)}</b></span></span>
            <span class="stock-meta-chip"><span class="sub-label">货号</span> <span class="copyable" data-copy="${esc(r.offer_id)}" title="点击复制货号"><b>${esc(r.offer_id || "暂无")}</b></span></span>
          </div>
        </td>
        <td class="text-right" data-label="FBP 现货">${inventory(r.channels[0], "fbp")}</td>
        <td class="text-right" data-label="realFBS 现货">${inventory(r.channels[1], "fbs")}</td>
        <td class="text-right" data-label="WHD 现货">${inventory(r.channels[2], "whd")}</td>
        <td class="text-right" data-label="近期有效销量">
          <div class="stock-sales-list">
            <span>7天 <b>${num(r.sales_7, 0)}</b> 件</span>
            <span>15天 <b>${num(r.sales_15, 0)}</b> 件</span>
            <span>30天 <b>${num(r.sales_30, 0)}</b> 件</span>
          </div>
        </td>
        <td class="text-right" data-label="综合预测">
          <div class="stock-forecast-box">
            <strong class="stock-daily-val">${r.daily_sales ? `${num(r.daily_sales, 2)} <small>件/天</small>` : "无法估算"}</strong>
            <small class="stock-days-sub ${r.days_available != null && r.days_available < 30 ? 'is-danger' : r.days_available != null && r.days_available < 90 ? 'is-warning' : ''}">FBP可售 ${r.days_available == null ? "—" : `<b>${num(r.days_available, 1)}</b> 天`}</small>
          </div>
        </td>
        <td class="text-center" data-label="FBP备货决策">
          <div class="stock-decision-cell">
            <span class="stock-decision-pill tone-${riskTone}"><morph-icon icon="${riskIcon}" size="12" stroke-width="2.2"></morph-icon><span>${esc(r.risk_status)}</span></span>
            <div class="stock-replenish-val">${r.replenishment == null ? '<span class="muted">—</span>' : `建议备货 <b>${num(r.replenishment, 0)}</b> 件`}</div>
            <small class="stock-time-sub">更新：${bj(r.observed_at)}</small>
          </div>
        </td>
      </tr>`;
    }).join("") || '<tr><td colspan="7" class="stock-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>当前筛选条件下没有库存或近期有效销量记录</span></td></tr>';
    pager("stock", data, loadStock);
  } catch (error) {
    $("#stockRows").innerHTML = `<tr><td colspan="7" class="stock-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>${esc(error.message)}</span></td></tr>`;
    throw error;
  }
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
    tbody.innerHTML = rows.map(r => `<tr><td class="import-filename" data-label="文件名称"><div class="import-file-cell"><span class="import-file-icon-badge"><morph-icon icon="fileText" size="14" stroke-width="1.8"></morph-icon></span><strong class="import-file-text" title="${esc(r.filename)}">${esc(r.filename)}</strong></div></td><td data-label="所属店铺／渠道"><div class="import-shop-cell"><strong class="import-shop-name">${esc(r.shop_name)}</strong>${channelTag(r.kind)}</div></td><td class="num text-right" data-label="导入行数"><div class="import-count-val"><strong>${num(r.row_count, 0)}</strong> <small>行</small></div></td><td class="text-right num import-time-cell" data-label="导入时间">${bj(r.imported_at)}</td></tr>`).join("") || '<tr><td colspan="4" class="transfer-empty"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>暂无历史 CSV 导入记录</span></td></tr>';
  } catch (error) {
    if (!isPolling) {
      tbody.innerHTML = `<tr><td colspan="4" class="transfer-empty error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>导入记录加载失败：${esc(error.message)}</span></td></tr>`;
    }
    throw error;
  }
}
const syncState = { rows: [], exchange: null, auto: [] };
function renderSyncSummary() {
  const root = $("#syncSummary");
  if (!root) return;
  const enabledCount = syncState.auto.filter(r => r.enabled).length;
  const lastSuccess = syncState.rows.find(r => r.status === "success");
  const failedCount = syncState.rows.filter(r => r.status === "failed").length;
  const rate = currency => syncState.exchange?.rates?.[currency]?.base_rate || "暂无";
  const usdRate = rate("USD"), cnyRate = rate("CNY");

  const cards = [
    {
      tone: "blue",
      label: "自动拉取配置",
      badge: `${enabledCount} / 6 开启`,
      icon: "clock",
      count: `${enabledCount}<small style="font-size:14px;font-weight:600;margin-left:4px;">/ 6 项启用</small>`,
      note: "两店铺三大模块独立定时调度"
    },
    {
      tone: "mint",
      label: "最近成功拉取",
      badge: lastSuccess ? "已同步" : "无记录",
      icon: "checkCircle",
      count: lastSuccess ? `${num(lastSuccess.records, 0)}<small style="font-size:14px;font-weight:600;margin-left:4px;">条记录</small>` : "暂无",
      note: lastSuccess ? `${esc(lastSuccess.shop_name)} · ${syncNames[lastSuccess.module] || lastSuccess.module} (${bj(lastSuccess.started_at)})` : "等待执行或暂无历史记录"
    },
    {
      tone: "lavender",
      label: "Ozon 官方基础汇率",
      badge: "USD & CNY",
      icon: "trendingUp",
      count: usdRate !== "暂无" ? `${esc(usdRate)}<small style="font-size:14px;font-weight:600;margin-left:4px;">USD/RUB</small>` : "暂无",
      note: `CNY/RUB 汇率：${esc(cnyRate)} · 全局生效`
    },
    {
      tone: failedCount > 0 ? "peach" : "mint",
      label: "同步异常与告警",
      badge: failedCount > 0 ? "需关注" : "健康",
      icon: failedCount > 0 ? "alertTriangle" : "check",
      count: `${failedCount}<small style="font-size:14px;font-weight:600;margin-left:4px;">次失败</small>`,
      note: failedCount > 0 ? "发生同步异常时自动推送钉钉告警" : "最近 10 次拉取任务运行正常"
    }
  ];
  root.innerHTML = renderAnalysisCards(cards);
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
    syncState.rows = rows;
    renderSyncSummary();
    const newHtml = rows.map(r => {
      const total = Math.max(1, Number(r.progress_total || 1)),
            done = Number(r.progress_done || 0),
            percent = Math.round(done / total * 100),
            status = r.status === 'failed' ? '失败' : r.status === 'success' ? '成功' : '进行中',
            statusIcon = r.status === 'failed' ? 'alertCircle' : r.status === 'success' ? 'check' : 'sync',
            source = r.run_source === 'auto' ? '自动' : '手动',
            module = syncNames[r.module] || r.module;
      return `<tr data-run-id="${r.id}"><td data-label="所属店铺"><div class="sync-shop-cell"><morph-icon icon="store" size="13" stroke-width="2"></morph-icon><strong>${esc(r.shop_name)}</strong></div></td><td data-label="同步模块与来源"><div class="sync-module-cell"><strong>${esc(module)}</strong><span class="sync-source ${r.run_source === 'auto' ? 'auto' : 'manual'}">${source}</span></div></td><td data-label="状态与分段进度"><span class="sync-state ${esc(r.status)}"><morph-icon icon="${statusIcon}" size="12" stroke-width="2.2" class="${r.status==='running'?'ozon-pulse':''}"></morph-icon><span>${status}</span></span>${r.status === 'running' ? `<div class="sync-progress-meta"><span>${done}/${total} 段 · ${percent}%</span><span>${num(r.records, 0)} 条记录</span></div><div class="sync-progress" role="progressbar" aria-label="${esc(module)}拉取进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>${r.current_from ? `<small class="sync-current">当前：${esc(r.current_from.slice(0, 10))} — ${esc(r.current_to.slice(0, 10))}</small>` : ''}` : r.status === 'success' ? `<div class="sync-success-meta">共拉取 ${num(r.records, 0)} 条记录</div>` : ''}</td><td data-label="开始时间" class="text-right"><span class="sync-time-cell">${bj(r.started_at)}</span></td><td data-label="执行详情 / 错误" class="${r.error ? 'error' : 'muted'}"><span class="sync-error-cell" title="${esc(r.error || '正常完成')}">${esc(r.error || '—')}</span></td></tr>`;
    }).join("") || '<tr><td colspan="5" class="sync-message"><morph-icon icon="checkCircle" size="20" stroke-width="1.8"></morph-icon><span>暂无拉取记录</span></td></tr>';
    tbody.innerHTML = newHtml;
    return rows;
  } catch (error) {
    if (!isPolling) {
      tbody.innerHTML = `<tr><td colspan="5" class="sync-message error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8"></morph-icon><span>拉取记录加载失败：${esc(error.message)}</span></td></tr>`;
    }
    throw error;
  }
}
async function loadExchangeRates(){const root=$("#exchangeRateStatus");if(!root)return;try{const data=await api("/api/exchange-rates");syncState.exchange=data;renderSyncSummary();const rateVal=curr=>data.rates?.[curr]?.base_rate;const formatRate=curr=>{const val=rateVal(curr);if(val==null||val===""||val==="暂无")return '<span class="muted">暂无</span>';const n=Number(val);return isNaN(n)?esc(String(val)):num(n,4)};root.innerHTML=`<div class="exchange-rate-card tone-mint"><div class="exchange-card-head"><div class="exchange-card-meta"><strong class="exchange-card-title">最后成功同步</strong><span class="exchange-card-tag">同步状态</span></div><div class="exchange-icon-badge"><morph-icon icon="checkCircle" size="14" stroke-width="2"></morph-icon></div></div><strong class="exchange-card-value">${data.last_success_at?bj(data.last_success_at):'<span class="muted">暂无记录</span>'}</strong><small class="exchange-card-desc">最近一次官方汇率同步完成时间</small></div><div class="exchange-rate-card tone-lavender"><div class="exchange-card-head"><div class="exchange-card-meta"><strong class="exchange-card-title">数据截止</strong><span class="exchange-card-tag">生效范围</span></div><div class="exchange-icon-badge"><morph-icon icon="calendar" size="14" stroke-width="2"></morph-icon></div></div><strong class="exchange-card-value">${data.data_through?bj(data.data_through):'<span class="muted">暂无数据</span>'}</strong><small class="exchange-card-desc">当前汇率有效覆盖截止期</small></div><div class="exchange-rate-card tone-azure"><div class="exchange-card-head"><div class="exchange-card-meta"><strong class="exchange-card-title">USD / RUB</strong><span class="exchange-card-tag">美元基准</span></div><div class="exchange-icon-badge"><morph-icon icon="trendingUp" size="14" stroke-width="2"></morph-icon></div></div><strong class="exchange-card-value">${formatRate('USD')}</strong><small class="exchange-card-desc">美元对俄罗斯卢布官方基准汇率</small></div><div class="exchange-rate-card tone-peach"><div class="exchange-card-head"><div class="exchange-card-meta"><strong class="exchange-card-title">CNY / RUB</strong><span class="exchange-card-tag">人民币基准</span></div><div class="exchange-icon-badge"><morph-icon icon="percent" size="14" stroke-width="2"></morph-icon></div></div><strong class="exchange-card-value">${formatRate('CNY')}</strong><small class="exchange-card-desc">人民币对俄罗斯卢布官方基准汇率</small></div>`}catch(error){root.innerHTML=`<div class="exchange-rate-card tone-peach error" style="grid-column:1/-1;"><div class="exchange-card-head"><strong class="exchange-card-title">汇率状态</strong></div><strong class="exchange-card-value">${esc(error.message)}</strong></div>`;throw error}}
function initMacaronSegmentedTime(input){if(!input||input.dataset.macaronSegBound)return;input.dataset.macaronSegBound="true";const wrap=input.closest(".auto-time-wrap");if(!wrap)return;input.style.display="none";const segWrap=document.createElement("div");segWrap.className="macaron-segmented-time";if(input.disabled)segWrap.classList.add("is-disabled");const[initialH,initialM]=(input.value||"02:00").split(":"),hourInp=document.createElement("input"),colon=document.createElement("span"),minInp=document.createElement("input");hourInp.type="text";hourInp.inputMode="numeric";hourInp.maxLength=2;hourInp.className="m-time-seg m-time-hour";hourInp.value=initialH||"02";hourInp.setAttribute("aria-label","小时");hourInp.disabled=input.disabled;colon.className="m-time-colon";colon.textContent=":";minInp.type="text";minInp.inputMode="numeric";minInp.maxLength=2;minInp.className="m-time-seg m-time-min";minInp.value=initialM||"00";minInp.setAttribute("aria-label","分钟");minInp.disabled=input.disabled;segWrap.appendChild(hourInp);segWrap.appendChild(colon);segWrap.appendChild(minInp);wrap.appendChild(segWrap);function syncValue(){let h=parseInt(hourInp.value,10),m=parseInt(minInp.value,10);if(isNaN(h))h=0;if(isNaN(m))m=0;h=Math.max(0,Math.min(23,h));m=Math.max(0,Math.min(59,m));const hStr=String(h).padStart(2,"0"),mStr=String(m).padStart(2,"0");hourInp.value=hStr;minInp.value=mStr;input.value=`${hStr}:${mStr}`;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))}hourInp.onfocus=()=>setTimeout(()=>hourInp.select(),10);minInp.onfocus=()=>setTimeout(()=>minInp.select(),10);hourInp.onclick=()=>hourInp.select();minInp.onclick=()=>minInp.select();hourInp.oninput=()=>{let val=hourInp.value.replace(/\D/g,"");if(val.length===1&&Number(val)>2){hourInp.value="0"+val;syncValue();minInp.focus();return}if(val.length>=2){hourInp.value=val.slice(0,2);syncValue();minInp.focus();return}hourInp.value=val};minInp.oninput=()=>{let val=minInp.value.replace(/\D/g,"");if(val.length===1&&Number(val)>5){minInp.value="0"+val;syncValue();return}if(val.length>=2){minInp.value=val.slice(0,2);syncValue();return}minInp.value=val};hourInp.onblur=syncValue;minInp.onblur=syncValue;hourInp.onkeydown=e=>{if(e.key==="ArrowUp"){e.preventDefault();hourInp.value=String((parseInt(hourInp.value||"0",10)+1)%24).padStart(2,"0");syncValue();hourInp.select()}else if(e.key==="ArrowDown"){e.preventDefault();hourInp.value=String((parseInt(hourInp.value||"0",10)+23)%24).padStart(2,"0");syncValue();hourInp.select()}else if(e.key==="ArrowRight"||e.key===":"||e.key==="Enter"){e.preventDefault();minInp.focus()}};minInp.onkeydown=e=>{if(e.key==="ArrowUp"){e.preventDefault();minInp.value=String((parseInt(minInp.value||"0",10)+5)%60).padStart(2,"0");syncValue();minInp.select()}else if(e.key==="ArrowDown"){e.preventDefault();minInp.value=String((parseInt(minInp.value||"0",10)+55)%60).padStart(2,"0");syncValue();minInp.select()}else if(e.key==="ArrowLeft"||(e.key==="Backspace"&&minInp.value==="")){e.preventDefault();hourInp.focus()}};hourInp.onwheel=e=>{e.preventDefault();let delta=e.deltaY<0?1:-1;hourInp.value=String((parseInt(hourInp.value||"0",10)+delta+24)%24).padStart(2,"0");syncValue();hourInp.select()};minInp.onwheel=e=>{e.preventDefault();let delta=e.deltaY<0?5:-5;minInp.value=String((parseInt(minInp.value||"0",10)+delta+60)%60).padStart(2,"0");syncValue();minInp.select()}}
function updateAutoSyncRow(toggle){const row=toggle.closest("[data-auto-row]"),enabled=toggle.checked;row.classList.toggle("is-disabled",!enabled);row.querySelectorAll("[data-auto-setting],[data-select-button]").forEach(input=>input.disabled=!enabled)}
async function saveAutoSync(){const values=Object.fromEntries([1,2].map(shop=>[String(shop),Object.fromEntries(Object.keys(syncNames).map(module=>[module,{enabled:$("#autoEnabled-"+shop+"-"+module)?.checked||false,interval_hours:Number($("#autoInterval-"+shop+"-"+module)?.value||24),range_days:module==="stock"?1:Number($("#autoRange-"+shop+"-"+module)?.value||1)}]))]));try{await api("/api/auto-sync-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(values)});toast("自动拉取设置已自动保存")}catch(err){toast(err.message,true)}}
async function loadAutoSync(){const rows=await api("/api/auto-sync-settings");syncState.auto=rows;renderSyncSummary();const byKey=new Map(rows.map(row=>[`${row.shop_id}:${row.module}`,row])),intervals=[1,2,3,4,6,8,12,24];$("#autoSyncCards").innerHTML=[1,2].map(shop=>{const shopName=state.shops.find(item=>item.id===shop)?.name||`店铺${shop}`;return `<section class="auto-sync-shop"><div class="auto-sync-shop-head"><div class="auto-sync-shop-badge"><morph-icon icon="store" size="14" stroke-width="2"></morph-icon><h3>${esc(shopName)}</h3></div><span class="auto-sync-shop-tag">店铺 ${shop}</span></div><div class="auto-sync-rows">${Object.keys(syncNames).map(module=>{const row=byKey.get(`${shop}:${module}`)||{enabled:false,interval_hours:24,range_days:1},selectId=`autoInterval-${shop}-${module}`;return `<article class="auto-sync-row" data-auto-row><div class="auto-sync-module"><strong>${syncNames[module]}</strong><small>${module==='stock'?'实时库存快照':'按日期范围拉取'}</small></div><label class="auto-sync-toggle"><span class="settings-switch"><input id="autoEnabled-${shop}-${module}" data-auto-enabled type="checkbox" ${row.enabled?'checked':''} aria-label="${esc(shopName)}${syncNames[module]}自动拉取"><span aria-hidden="true"></span></span></label><div class="auto-sync-field"><span>拉取频率</span><div class="return-select" data-return-select><select id="${selectId}" data-auto-setting aria-label="${esc(shopName)}${syncNames[module]}拉取频率">${intervals.map(value=>`<option value="${value}" ${Number(row.interval_hours)===value?'selected':''}>每隔 ${value} 小时</option>`).join("")}</select><button type="button" data-select-button aria-haspopup="listbox" aria-expanded="false" aria-label="${esc(shopName)}${syncNames[module]}拉取频率"><span data-select-label>每隔 ${Number(row.interval_hours||24)} 小时</span><morph-icon icon="chevronDown" size="18" spring="snappy" stroke-width="1.5"></morph-icon></button><div class="return-select-options hidden" data-select-options role="listbox" aria-label="拉取频率"></div></div></div>${module==='stock'?'<div class="auto-sync-field"><span class="auto-sync-field-label">拉取范围</span><strong class="snapshot-tag">实时快照</strong></div>':`<label class="auto-sync-field"><span class="auto-sync-field-label">最近 N 天</span><input id="autoRange-${shop}-${module}" data-auto-setting type="number" min="1" max="365" value="${Number(row.range_days)}" required aria-label="${esc(shopName)}${syncNames[module]}拉取范围"></label>`}</article>`}).join("")}</div></section>`}).join("");document.querySelectorAll("#autoSyncCards select[data-auto-setting]").forEach(select=>{returnSelects[select.id]=createReturnSelect(select.id);select.onchange=()=>saveAutoSync()});document.querySelectorAll("[data-auto-enabled]").forEach(toggle=>{updateAutoSyncRow(toggle);toggle.onchange=()=>{updateAutoSyncRow(toggle);saveAutoSync()}});document.querySelectorAll("#autoSyncCards input[type=number]").forEach(input=>{input.onchange=()=>saveAutoSync()})}
async function loadDingtalk() {
  const data = await api("/api/dingtalk/settings");
  const last = data.last_run;
  const status = last ? (last.status === 'success' ? '发送成功' : last.status === 'failed' ? '发送失败' : '发送中') : "暂无记录";
  const statusTone = status === '发送成功' ? 'mint' : status === '发送失败' ? 'peach' : 'lavender';
  const statusIcon = status === '发送成功' ? 'checkCircle' : status === '发送失败' ? 'alertCircle' : 'rotateCcw';

  const cards = [
    {
      label: "机器人连接",
      count: data.configured ? "已配置" : "未配置",
      icon: "dingtalk",
      tone: data.configured ? "mint" : "peach",
      note: data.configured ? "Webhook 凭据就绪" : "需在服务器 .env 配置",
      badge: data.configured ? "就绪" : "未就绪"
    },
    {
      label: "每日汇总计划",
      count: data.daily_enabled ? "已启用" : "已停用",
      icon: "clock",
      tone: data.daily_enabled ? "azure" : "lavender",
      note: data.daily_enabled ? "定时推送昨日业务明细" : "定时任务已暂停",
      badge: data.daily_enabled ? "运行中" : "已暂停"
    },
    {
      label: "下次预计推送",
      count: data.next_push_at ? bj(data.next_push_at) : "—",
      icon: "calendar",
      tone: "azure",
      note: data.next_push_at ? "按北京时间准时触发" : "未开启或未设排期"
    },
    {
      label: "最近一次推送",
      count: status,
      icon: statusIcon,
      tone: statusTone,
      note: last?.sent_at ? `已于 ${bj(last.sent_at)} 投递` : (last?.error ? "投递异常" : "等待下一次触发"),
      badge: last?.stats_date ? `统计 ${last.stats_date}` : ""
    }
  ];
  const summaryEl = $("#dingtalkSummary");
  if (summaryEl) summaryEl.innerHTML = renderAnalysisCards(cards);

  $("#dingEnabled").checked = data.daily_enabled;
  $("#dingTime").value = data.push_time;
  document.querySelectorAll("#dingWeekdays input").forEach(input => {
    input.checked = data.weekdays.includes(Number(input.value));
  });
  initMacaronSegmentedTime($("#dingTime"));

  const lastEl = $("#dingtalkLast");
  if (lastEl) {
    const statusPillClass = status === '发送成功' ? 'tone-mint' : status === '发送失败' ? 'tone-peach' : 'tone-lavender';
    lastEl.innerHTML = `
      <div class="ding-fact-item">
        <dt>统计业务日期</dt>
        <dd><strong>${esc(last?.stats_date || '—')}</strong></dd>
      </div>
      <div class="ding-fact-item">
        <dt>投递执行状态</dt>
        <dd><span class="return-status-pill ${statusPillClass}">${esc(status)}</span></dd>
      </div>
      <div class="ding-fact-item">
        <dt>实际发送时间</dt>
        <dd><strong>${last?.sent_at ? bj(last.sent_at) : '—'}</strong></dd>
      </div>
      <div class="ding-fact-item">
        <dt>失败原因 / 详情</dt>
        <dd class="${last?.error ? 'error-text' : ''}"><strong>${esc(last?.error || '无异常')}</strong></dd>
      </div>
    `;
  }
}
function pushTypesFromResponse(response){
  const values=Array.isArray(response)?response:(response?.types||response?.result?.types||[]);
  return values.map(value=>typeof value==="string"?value:value?.type).filter(Boolean).map(String);
}
function pushSubscriptionsFromResponse(response){
  const values=Array.isArray(response)?response:(response?.urls||response?.result?.urls||response?.notifications||response?.result?.notifications||[]);
  if(!Array.isArray(values))return [];
  return values.filter(row=>row&&typeof row==="object"&&(row.id!=null||row.notification_id!=null||row.url)).map(row=>{
    const enabled=row.enabled??row.is_enabled??false;
    return {
      id:row.id??row.notification_id,
      url:String(row.url||""),
      enabled:enabled===true||enabled===1||enabled==="1"||enabled==="true",
      types:pushTypesFromResponse({types:row.types}),
      createdAt:row.created_at,
      updatedAt:row.updated_at,
      error:row.error||row.last_error||""
    };
  });
}
function maskPushUrl(value){
  const raw=String(value||"").trim();
  if(!raw)return "暂无";
  try{
    const url=new URL(raw),parts=url.pathname.split("/"),marker=parts.findIndex((part,index)=>part==="ozon"&&parts[index+1]);
    if(marker>=0)parts[marker+1]="***";
    url.pathname=parts.join("/");
    if(url.search)url.search="?***";
    if(url.hash)url.hash="#***";
    return url.toString();
  }catch(_error){return "已配置（地址格式未解析）"}
}
function pushShopName(shopId){return state.shops.find(shop=>shop.id===shopId)?.name||`店铺 ${shopId}`}
function pushNotice(data){
  if(!data.notice?.message)return "";
  const error=data.notice.kind==="error";
  return `<div class="push-operation-message ${error?"is-error":"is-success"}" role="status"><morph-icon icon="${error?"alertCircle":"checkCircle"}" size="14" stroke-width="2"></morph-icon><span>${esc(data.notice.message)}</span></div>`;
}
function pushCheckNotice(data){
  const check=data.check||{};
  if(check.status==="loading")return `<div class="push-operation-message is-running" role="status"><morph-icon icon="sync" size="14" class="ozon-pulse" stroke-width="2"></morph-icon><span>正在请求 Ozon 检测 Webhook…</span></div>`;
  if(check.status==="success")return `<div class="push-operation-message is-success" role="status"><morph-icon icon="checkCircle" size="14" stroke-width="2"></morph-icon><span>${esc(check.message)}</span></div>`;
  if(check.status==="error")return `<div class="push-operation-message is-error" role="alert"><morph-icon icon="alertCircle" size="14" stroke-width="2"></morph-icon><span>${esc(check.message)}</span></div>`;
  return "";
}
function renderPushCard(shopId){
  const data=pushSubscriptionState[shopId]||{shopId,loading:true,types:[],subscriptions:[],listReady:false};
  const shopName=data.name||pushShopName(shopId);
  if(data.loading)return `<section class="panel push-shop-card" data-push-shop-card="${shopId}"><div class="panel-title"><div><h2><morph-icon icon="store" size="18" stroke-width="1.8"></morph-icon> ${esc(shopName)}</h2><span class="muted">店铺 ${shopId} · Push 订阅配置</span></div><span class="push-shop-tag">店铺 ${shopId}</span></div><div class="push-loading-state"><morph-icon icon="sync" size="20" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>正在读取 Ozon Push 配置…</span></div></section>`;
  const subscriptions=data.subscriptions||[],types=data.types||[],selected=new Set(data.selectedTypes||types);
  const apiText=data.apiAvailable?"可用":"不可用",apiClass=data.apiAvailable?"is-ok":"is-error";
  const count=data.listReady?String(subscriptions.length):"—",enabledCount=data.listReady?String(subscriptions.filter(row=>row.enabled).length):"—";
  const currentUrls=subscriptions.map(row=>row.url).filter(Boolean),currentUrl=currentUrls.length?maskPushUrl(currentUrls[0]):data.listReady?"暂无":"无法读取";
  const currentUrlNote=currentUrls.length>1?`另有 ${currentUrls.length-1} 个订阅`:"";
  const eventOptions=types.length?types.map(type=>`<label class="push-type-option"><input type="checkbox" data-push-type value="${esc(type)}" ${selected.has(type)?"checked":""}><span><strong>${esc(PUSH_EVENT_LABELS[type]||"Ozon Push 事件")}</strong><small>${esc(type)}</small></span></label>`).join(""):"<div class=\"push-empty-state\">Ozon 未返回可订阅类型</div>";
  const typeNotice=data.typesFresh?"":`<div class="push-inline-banner is-warning" role="status"><morph-icon icon="alertTriangle" size="14" stroke-width="1.8"></morph-icon><span>无法从 Ozon 获取最新类型，已使用内置已知类型作为降级展示。${data.typeError?` ${esc(data.typeError)}`:""}</span></div>`;
  const listError=!data.listReady?`<div class="push-empty-state is-error"><morph-icon icon="alertCircle" size="18" stroke-width="1.8"></morph-icon><strong>订阅读取失败</strong><span>${esc(data.listError||"Ozon 未返回订阅列表")}</span></div>`:"";
  const subscriptionRows=data.listReady?(subscriptions.length?subscriptions.map(row=>{
    const rowTypes=row.types.length?row.types.map(type=>`<span class="push-type-chip">${esc(PUSH_EVENT_LABELS[type]||type)}</span>`).join(""):"<span class=\"muted\">未返回事件类型</span>";
    const details=[row.createdAt?`创建于 ${bj(row.createdAt)}`:"",row.updatedAt?`更新于 ${bj(row.updatedAt)}`:"",row.error?`Ozon：${row.error}`:""].filter(Boolean).join(" · ");
    const deleting=data.action===`deleting:${row.id}`,busy=data.enableBusyId===String(row.id);
    return `<article class="push-subscription"><div class="push-subscription-main"><div class="push-subscription-id"><span>ID</span><code>${esc(row.id??"—")}</code></div><code class="push-subscription-url" title="Webhook 地址已隐藏密钥">${esc(maskPushUrl(row.url))}</code><div class="push-subscription-types">${rowTypes}</div>${details?`<small class="push-subscription-details">${esc(details)}</small>`:""}</div><div class="push-subscription-actions"><label class="push-enable-label"><span>启用</span><span class="settings-switch"><input type="checkbox" data-push-enabled data-shop="${shopId}" data-id="${esc(row.id)}" aria-label="启用订阅 ${esc(row.id)}" ${row.enabled?"checked":""} ${busy?"disabled":""}><span aria-hidden="true"></span></span></label><button type="button" class="rule-act-btn is-danger" data-push-action="delete" data-shop="${shopId}" data-id="${esc(row.id)}" ${deleting?"disabled":""}><morph-icon icon="trash" size="12" stroke-width="2"></morph-icon><span>${deleting?"删除中…":"删除"}</span></button></div></article>`;
  }).join(""):'<div class="push-empty-state"><morph-icon icon="zap" size="18" stroke-width="1.8"></morph-icon><strong>暂无 Push 订阅</strong><span>填写 Webhook 地址并选择事件后即可注册。</span></div>'):listError;
  const draft=String(data.urlDraft||""),sameUrl=subscriptions.some(row=>row.url===draft.trim()),setting=data.action==="setting";
  return `<section class="panel push-shop-card" data-push-shop-card="${shopId}"><div class="panel-title"><div><h2><morph-icon icon="store" size="18" stroke-width="1.8"></morph-icon> ${esc(shopName)}</h2><span class="muted">店铺 ${shopId} · 单独管理 Seller API Push 订阅</span></div><span class="push-shop-tag">店铺 ${shopId}</span></div><div class="push-status-grid"><div class="push-status-item"><span>Ozon API</span><strong class="push-status-value ${apiClass}">${apiText}</strong></div><div class="push-status-item"><span>Push 订阅</span><strong class="push-status-value ${subscriptions.length?"is-ok":"is-muted"}">${data.listReady?(subscriptions.length?"已配置":"未配置"):"无法读取"}</strong></div><div class="push-status-item"><span>当前订阅数量</span><strong class="push-status-value">${count}</strong></div><div class="push-status-item"><span>已启用数量</span><strong class="push-status-value">${enabledCount}</strong></div><div class="push-status-item push-status-url"><span>当前订阅 URL</span><code title="Webhook 地址已隐藏密钥">${esc(currentUrl)}</code>${currentUrlNote?`<small>${esc(currentUrlNote)}</small>`:""}</div></div>${!data.apiAvailable?`<div class="push-inline-banner is-error" role="alert"><morph-icon icon="alertCircle" size="14" stroke-width="1.8"></morph-icon><span>Ozon Push 管理 API 不可用：${esc(data.typeError||data.listError||"请检查服务器中的 Ozon API 凭据")}</span></div>`:""}<form id="pushForm${shopId}" class="push-form" data-push-form data-shop="${shopId}" novalidate><div class="push-section-title"><div><h3>Webhook 地址</h3><span>向 Ozon 注册订阅时使用的公网 HTTPS 地址</span></div></div><label class="push-field" for="pushUrl${shopId}"><span>Webhook URL</span><input id="pushUrl${shopId}" data-push-url type="text" value="${esc(draft)}" placeholder="https://example.com/api/webhooks/ozon/…" autocomplete="off"><small>Webhook 地址必须能够被 Ozon 通过公网 HTTPS 访问；密钥由服务器 .env 管理，请勿在页面中展示或保存 Secret。</small></label><div class="push-section-title"><div><h3>订阅事件</h3><span>提交给 Ozon API 的是原始 <code>TYPE_*</code> 值</span></div></div>${typeNotice}<div class="push-type-list">${eventOptions}</div><div class="push-form-actions"><button type="button" class="push-check-btn" data-push-action="check" data-shop="${shopId}" ${data.check?.status==="loading"?"disabled":""}><morph-icon icon="sync" size="14" stroke-width="2" spring="snappy"></morph-icon><span>检测连接</span></button><button type="submit" class="primary" data-push-set-label data-shop="${shopId}" ${setting?"disabled":""}><morph-icon icon="${sameUrl?"edit":"plus"}" size="14" stroke-width="2"></morph-icon><span>${setting?"保存中…":sameUrl?"更新订阅":"注册订阅"}</span></button></div>${pushCheckNotice(data)}${pushNotice(data)}</form><section class="push-subscription-section"><div class="push-section-title"><div><h3>当前订阅</h3><span>Ozon API 返回的订阅列表</span></div><span class="push-count-badge">${data.listReady?`${subscriptions.length} 条`:"读取中"}</span></div><div class="push-subscription-list">${subscriptionRows}</div></section></section>`;
}
function renderPushGrid(){
  const host=$("#pushShopGrid");
  if(host)host.innerHTML=[1,2].map(shopId=>renderPushCard(shopId)).join("");
}
async function loadPushShop(shopId,loadToken=pushSubscriptionLoadToken){
  const previous=pushSubscriptionState[shopId]||{};
  pushSubscriptionState[shopId]={...previous,shopId,name:pushShopName(shopId),loading:true,apiAvailable:false,listReady:false,types:[],subscriptions:[],typeError:"",listError:"",notice:null,action:"",enableBusyId:"",check:{status:"idle"}};
  renderPushGrid();
  const resultOf=promise=>promise.then(response=>({ok:true,response})).catch(error=>({ok:false,error}));
  const [typesResult,listResult]=await Promise.all([
    resultOf(api(`/api/ozon/notifications/push-types?shop_id=${shopId}`,{method:"POST"})),
    resultOf(api("/api/ozon/notifications/list",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:shopId})}))
  ]);
  if(loadToken!==pushSubscriptionLoadToken)return;
  const ozonTypes=typesResult.ok?pushTypesFromResponse(typesResult.response):[],subscriptions=listResult.ok?pushSubscriptionsFromResponse(listResult.response):[];
  const subscriptionTypes=subscriptions.find(row=>row.types.length)?.types||[],baseTypes=ozonTypes.length?ozonTypes:PUSH_EVENT_FALLBACK_TYPES,types=[...new Set([...baseTypes,...subscriptionTypes])];
  pushSubscriptionState[shopId]={...previous,shopId,name:pushShopName(shopId),loading:false,apiAvailable:typesResult.ok||listResult.ok,listReady:listResult.ok,types,typesFresh:ozonTypes.length>0,subscriptions,typeError:typesResult.ok?(ozonTypes.length?"":"Ozon 未返回可订阅类型"):typesResult.error.message,listError:listResult.ok?"":listResult.error.message,selectedTypes:subscriptionTypes.length?subscriptionTypes:(previous.selectedTypes?.filter(type=>types.includes(type)).length?previous.selectedTypes.filter(type=>types.includes(type)):types),notice:null,action:"",enableBusyId:"",check:{status:"idle"}};
  renderPushGrid();
}
async function loadPushSubscriptions(){
  if(!$("#pushShopGrid"))return;
  const loadToken=++pushSubscriptionLoadToken;
  pushSubscriptionState=Object.fromEntries([1,2].map(shopId=>[shopId,{shopId,name:pushShopName(shopId),loading:true,types:[],subscriptions:[]} ]));
  renderPushGrid();
  await Promise.all([loadPushShop(1,loadToken),loadPushShop(2,loadToken)]);
}
function pushActionError(shopId,message){
  const data=pushSubscriptionState[shopId];
  if(!data)return;
  data.notice={kind:"error",message};data.action="";renderPushGrid();toast(message,true);
}
async function checkPushWebhook(shopId){
  const form=$("#pushForm"+shopId),url=form?.querySelector("[data-push-url]")?.value.trim()||"",data=pushSubscriptionState[shopId];
  if(!url)return pushActionError(shopId,"请输入 Webhook 地址");
  if(!url.startsWith("https://"))return pushActionError(shopId,"Webhook 地址必须以 https:// 开头");
  data.urlDraft=url;data.check={status:"loading"};data.notice=null;renderPushGrid();
  try{await api("/api/ozon/notifications/check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:shopId,url})});data.check={status:"success",message:"检测成功：Ozon 已接受 Webhook 地址"};}
  catch(error){data.check={status:"error",message:error.message};}
  renderPushGrid();
}
async function setPushSubscription(form){
  const shopId=Number(form.dataset.shop),data=pushSubscriptionState[shopId],url=form.querySelector("[data-push-url]")?.value.trim()||"",types=[...form.querySelectorAll("[data-push-type]:checked")].map(input=>input.value);
  data.urlDraft=url;data.selectedTypes=types;
  if(!url)return pushActionError(shopId,"请输入 Webhook 地址");
  if(!url.startsWith("https://"))return pushActionError(shopId,"Webhook 地址必须以 https:// 开头");
  if(!types.length)return pushActionError(shopId,"至少选择一个 Push 类型");
  data.action="setting";data.notice=null;renderPushGrid();
  try{await api("/api/ozon/notifications/set",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:shopId,url,types})});toast(data.subscriptions.some(row=>row.url===url)?"Push 订阅已更新":"Push 订阅已注册");data.urlDraft="";await loadPushShop(shopId);}
  catch(error){data.action="";data.notice={kind:"error",message:error.message};renderPushGrid();toast(error.message,true);}
}
async function togglePushSubscription(shopId,id,input){
  const data=pushSubscriptionState[shopId],row=data?.subscriptions.find(item=>String(item.id)===String(id)),notificationId=Number(id);
  if(!data||!row||!Number.isInteger(notificationId))return pushActionError(shopId,"通知ID无效");
  const previous=row.enabled;row.enabled=input.checked;data.enableBusyId=String(id);data.notice=null;renderPushGrid();
  try{await api("/api/ozon/notifications/enable",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:shopId,id:notificationId,enabled:input.checked})});toast(input.checked?"Push 订阅已启用":"Push 订阅已停用");await loadPushShop(shopId);}
  catch(error){row.enabled=previous;data.enableBusyId="";data.notice={kind:"error",message:error.message};renderPushGrid();toast(error.message,true);}
}
async function deletePushSubscription(shopId,id){
  const notificationId=Number(id);
  if(!Number.isInteger(notificationId))return pushActionError(shopId,"通知ID无效");
  const ok=await showConfirm({title:"删除 Push 订阅？",message:`将从 Ozon 删除订阅 ID ${id}，此操作不可撤销。`,confirmText:"确认删除",cancelText:"取消",icon:"trash"});
  if(!ok)return;
  const data=pushSubscriptionState[shopId];data.action=`deleting:${id}`;data.notice=null;renderPushGrid();
  try{await api("/api/ozon/notifications/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({shop_id:shopId,id:notificationId})});toast("Push 订阅已删除");await loadPushShop(shopId);}
  catch(error){data.action="";data.notice={kind:"error",message:error.message};renderPushGrid();toast(error.message,true);}
}
function addMergeMember(member={key_type:"sku",key_value:""}){
  const id=`mergeMemberType${++mergeMemberIndex}`,row=document.createElement("div");
  row.className="merge-member";
  row.innerHTML=`<div class="return-select merge-type-select" data-return-select><select id="${id}" aria-label="成员类型"><option value="sku">SKU</option><option value="offer_id">货号</option></select><button type="button" data-select-button aria-haspopup="listbox" aria-expanded="false"><span data-select-label>SKU</span><morph-icon icon="chevronDown" size="16" spring="snappy" stroke-width="1.5"></morph-icon></button><div class="return-select-options hidden" data-select-options role="listbox" aria-label="成员类型"></div></div><input class="merge-member-value" value="${esc(member.key_value)}" placeholder="输入关联 SKU 或货号" aria-label="成员值" autocomplete="off" required><button type="button" class="member-remove-btn" data-remove-member aria-label="删除成员" title="删除成员"><morph-icon icon="x" size="14" stroke-width="2"></morph-icon></button>`;
  $("#mergeMembers").append(row);
  returnSelects[id]=createReturnSelect(id);
  setReturnSelect(id,member.key_type);
  return row;
}
function resetMergeForm(){$("#mergeForm").reset();$("#mergeId").value="";$("#mergeMembers").replaceChildren();addMergeMember()}
async function loadRules(){
  const query=new URLSearchParams({q:$("#shortSearch").value.trim()}),
        data=await api(`/api/product-rules?${query}`);
  ruleData=data;
  const conflictCount=data.conflicts?.length||0;
  const cards=[
    {
      tone:"mint",
      label:"中文短名称规则",
      badge:"SKU 映射",
      icon:"tag",
      count:`${num(data.summary.short_names,0)}<small style="font-size:14px;font-weight:600;margin-left:4px;">条规则</small>`,
      note:"用于全系统报表统一商品简称"
    },
    {
      tone:"blue",
      label:"全局合并关系",
      badge:"主货号聚合",
      icon:"gitMerge",
      count:`${num(data.summary.merges,0)}<small style="font-size:14px;font-weight:600;margin-left:4px;">个主货号</small>`,
      note:"多规格/多店铺货号归一聚合分析"
    },
    {
      tone:conflictCount>0?"peach":"mint",
      label:"待处理旧冲突",
      badge:conflictCount>0?"需处理":"正常",
      icon:conflictCount>0?"alertTriangle":"check",
      count:`${conflictCount}<small style="font-size:14px;font-weight:600;margin-left:4px;">项冲突</small>`,
      note:conflictCount>0?"存在旧规则或未确认合并冲突":"所有商品合并关系正常生效"
    },
    {
      tone:"lavender",
      label:"内置清洗规则",
      badge:"系统清洗",
      icon:"layers",
      count:`1<small style="font-size:14px;font-weight:600;margin-left:4px;">项规则</small>`,
      note:data.fixed_rule||"自动移除平台“Новый ”前缀"
    }
  ];
  $("#ruleSummary").innerHTML=renderAnalysisCards(cards);
  if($("#ruleFixedRuleText")){$("#ruleFixedRuleText").textContent=data.fixed_rule||"自动移除平台“Новый ”前缀"}else if($("#ruleFixedRule")){$("#ruleFixedRule").textContent=data.fixed_rule||""}
  $("#shortRuleRows").innerHTML=data.short_names.map(row=>`<tr><td class="copyable" data-copy="${esc(row.sku)}" title="点击复制 SKU"><div class="rule-sku-cell"><morph-icon icon="tag" size="13" stroke-width="2"></morph-icon><strong>${esc(row.sku)}</strong></div></td><td><span class="rule-short-name">${esc(row.short_name)}</span></td><td class="text-right"><span class="sync-time-cell">${bj(row.updated_at)}</span></td><td class="text-right"><div class="table-actions"><button type="button" class="rule-act-btn" data-edit-short="${esc(row.sku)}" title="编辑短名称"><morph-icon icon="edit" size="12" stroke-width="2"></morph-icon><span>编辑</span></button><button type="button" class="rule-act-btn is-danger" data-delete-short="${esc(row.sku)}" title="删除短名称"><morph-icon icon="trash" size="12" stroke-width="2"></morph-icon><span>删除</span></button></div></td></tr>`).join("")||'<tr><td colspan="4" class="rule-empty-cell"><div class="rule-empty-state"><morph-icon icon="tag" size="24" stroke-width="1.8"></morph-icon><strong>暂无短名称规则</strong><small>在上方输入 SKU 和中文短名称即可添加</small></div></td></tr>';
  $("#mergeRuleList").innerHTML=data.groups.map(group=>`<article class="merge-rule-card ${group.status!=="active"?"is-pending":""}"><div class="merge-rule-head"><div class="merge-primary-meta"><span class="merge-primary-chip"><morph-icon icon="box" size="12" stroke-width="2"></morph-icon><span>主货号 · ${esc(group.primary_offer_id||"待设置")}</span></span></div><small class="merge-product-title">${esc(group.product_name)}</small></div><div class="merge-tags">${group.members.map(member=>`<span class="merge-chip ${member.key_type==="sku"?"chip-sku":"chip-offer"}"><morph-icon icon="${member.key_type==="sku"?"tag":"box"}" size="11" stroke-width="2"></morph-icon><strong>${member.key_type==="sku"?"SKU":"货号"}</strong><span>${esc(member.key_value)}</span></span>`).join("")}</div><div class="merge-rule-foot"><small class="sync-time-cell">${group.note?esc(group.note):`更新于 ${bj(group.updated_at)}`}</small><div class="table-actions"><button type="button" class="rule-act-btn" data-edit-merge="${group.id}" title="编辑合并关系"><morph-icon icon="edit" size="12" stroke-width="2"></morph-icon><span>编辑</span></button><button type="button" class="rule-act-btn is-danger" data-dissolve="${group.id}" title="解散合并关系"><morph-icon icon="trash" size="12" stroke-width="2"></morph-icon><span>解散</span></button></div></div></article>`).join("")||'<div class="rule-empty-card"><div class="rule-empty-state"><morph-icon icon="gitMerge" size="24" stroke-width="1.8"></morph-icon><strong>暂无全局合并关系</strong><small>在上方添加主货号与关联成员即可建立全局合并分析身份</small></div></div>';
  $("#ruleConflicts").classList.toggle("hidden",!conflictCount);
  $("#ruleConflicts").innerHTML=conflictCount?`<div class="rule-conflicts-head"><morph-icon icon="alertTriangle" size="18" stroke-width="2"></morph-icon><h2>待处理的旧规则冲突 (${conflictCount})</h2></div><div class="rule-conflicts-list">${data.conflicts.map(row=>`<div class="rule-conflict-item"><strong>${esc(row.key_value)}</strong><span>${esc(row.note)}</span></div>`).join("")}</div>`:""
}
async function loadSettings(){
  $("#probeShops").innerHTML=state.shops.map(s=>`
    <article class="settings-shop-card" data-shop-card="${s.id}">
      <div class="settings-shop-head">
        <div class="settings-shop-identity">
          <div class="settings-shop-badge">
            <morph-icon icon="store" size="14" stroke-width="2"></morph-icon>
            <strong>${esc(s.name)}</strong>
          </div>
          <span class="settings-shop-tag">店铺 ${s.id}</span>
        </div>
        <button type="button" class="settings-shop-probe-btn" data-probe-single="${s.id}" title="单独检测店铺 ${s.id} API 连通性">
          <morph-icon icon="refreshCw" size="12" stroke-width="2" spring="snappy"></morph-icon>
          <span>检测</span>
        </button>
      </div>
      <div id="probeResult${s.id}" class="settings-probe-result">
        ${probeResult({status:"idle"})}
      </div>
    </article>
  `).join("");
}
function probeResult(result={}){
  const status=result.status||(result.valid===true?"success":result.valid===false?"error":"idle"),
        isIdle=status==="idle",isLoading=status==="loading",isOk=status==="success",isError=status==="error";
  let badge="";
  if(isIdle) badge=`<span class="probe-state is-idle"><morph-icon icon="clock" size="12" stroke-width="1.8"></morph-icon><span>待检测</span></span>`;
  else if(isLoading) badge=`<span class="probe-state is-running"><morph-icon icon="sync" size="12" stroke-width="2.2" class="ozon-pulse"></morph-icon><span>正在检测…</span></span>`;
  else if(isOk) badge=`<span class="probe-state is-ok"><morph-icon icon="check" size="12" stroke-width="2.2"></morph-icon><span>凭据有效</span></span>`;
  else badge=`<span class="probe-state is-error"><morph-icon icon="alertTriangle" size="12" stroke-width="2.2"></morph-icon><span>连接失败</span></span>`;

  const identity=result.identity||{},company=identity.company||{},
        name=isOk?(company.name||identity.name||"店铺身份已确认"):"—",
        seller=isOk?(identity.seller_id||identity.client_id||"未返回"):"—",
        inn=isOk?(company.inn||identity.inn||"未返回"):"—",
        roles=isOk?((result.roles||[]).join("、")||"未返回"):"—",
        errorNote=isError?`<div class="probe-error-note"><morph-icon icon="alertCircle" size="14" stroke-width="2"></morph-icon><span>${esc(result.error||"凭据或网络异常")}</span></div>`:"";

  const perms=["orders","returns","stock"].map(k=>{
    const title=syncNames[k]||k;
    if(isIdle||isLoading) return `<span class="probe-perm-chip is-idle"><strong>${esc(title)}</strong><small>待检测</small></span>`;
    const val=result.permissions?.[k]||(isOk?"可用":"未返回"),ok=val==="可用";
    return `<span class="probe-perm-chip ${ok?'is-ok':'is-missing'}"><strong><morph-icon icon="${ok?'check':'x'}" size="11" stroke-width="2.2"></morph-icon>${esc(title)}</strong><small>${esc(val)}</small></span>`;
  }).join("");

  return `
    <div class="probe-result-top">
      <span class="probe-top-label">诊断状态</span>
      ${badge}
    </div>
    ${errorNote}
    <dl class="probe-facts">
      <div class="probe-fact-item"><dt>店铺主体</dt><dd title="${esc(name)}">${esc(name)}</dd></div>
      <div class="probe-fact-item"><dt>Seller ID</dt><dd class="tabular-nums">${cell(seller)}</dd></div>
      <div class="probe-fact-item"><dt>税号 INN</dt><dd class="tabular-nums">${cell(inn)}</dd></div>
      <div class="probe-fact-item"><dt>授权角色</dt><dd title="${esc(roles)}">${esc(roles)}</dd></div>
    </dl>
    <div class="probe-permissions-section">
      <span class="probe-perm-label">模块调用权限</span>
      <div class="probe-permissions">${perms}</div>
    </div>
  `;
}
async function loadPage(page) {
  if(page==="overview") return Promise.all([loadOverview(),loadTrend()]); if(page==="orders") return loadOrders();
  if(page==="analytics") return loadAnalyticsPage();
  if(page==="risk") return loadRisk();
  const loaders={timeliness:loadTimeliness,returns:loadReturnPage,complaintPlaceholder:loadExceptionComplaints,stock:loadStock,profit:loadProfitPage};
  if(loaders[page]) return loaders[page](); if(page==="transfer") return loadImports(); if(page==="sync") return Promise.all([loadSync(),loadAutoSync(),loadExchangeRates()]); if(page==="rules") return loadRules(); if(page==="pushSubscriptions") return loadPushSubscriptions(); if(page==="dingtalk") return loadDingtalk(); if(page==="settings") return loadSettings();
}
function morphConfirm(morph,canonicalIcon,duration=300){if(!morph)return;clearTimeout(morph._confirmTimer);morph.morphTo("check","snappy");morph._confirmTimer=setTimeout(()=>{morph.morphTo(canonicalIcon,"snappy")},duration)}
const navIconMap={overview:"dashboard",orders:"orders",analytics:"search",risk:"risk",timeliness:"delivery",returns:"returns",complaintPlaceholder:"messageSquareAlert",stock:"stock",profit:"trendingUp",transfer:"transfer",sync:"sync",rules:"rules",pushSubscriptions:"zap",dingtalk:"dingtalk"};
const pageDateRangeMap={overview:"#overviewDateRange",orders:"#orderDateRange",analytics:"#analyticsDateRange",risk:"#riskDateRange",timeliness:"#timelinessDateRange",returns:"#returnsDateRange",complaintPlaceholder:"#complaintDateRange",transfer:"#exportDateRange",sync:"#syncDateRange"};
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
  $("#settingsButton")?.classList.toggle("active", page === "settings");
  $("#shopPickerButton")?.closest(".shop-picker-wrap")?.classList.toggle("hidden", page === "profit");
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
$("#profitForm")?.addEventListener("submit",e=>e.preventDefault());
$("#profitForm")?.addEventListener("input",renderProfitCalculator);
$("#profitForm")?.addEventListener("change",renderProfitCalculator);
$("#nav").addEventListener("click",e=>{const button=e.target.closest("[data-page]");if(button)openPage(button.dataset.page)});
$("#analyticsTabs").onclick=e=>{const button=e.target.closest("[data-analytics-tab]");if(!button||button.dataset.analyticsTab===analyticsTab)return;analyticsTab=button.dataset.analyticsTab;$("#analyticsTabs").querySelectorAll("button").forEach(item=>{const active=item===button;item.classList.toggle("active",active);item.setAttribute("aria-selected",String(active));item.tabIndex=active?0:-1});$("#analytics-traffic").classList.toggle("hidden",analyticsTab!=="traffic");$("#analytics-queries").classList.toggle("hidden",analyticsTab!=="queries");loadAnalyticsPage()};
$("#analyticsFilterForm").onsubmit=e=>{e.preventDefault();state.pages.analyticsData=state.pages.productQueries=state.pages.productQueryDetails=1;loadAnalyticsPage()};
$("#analyticsClear").onclick=()=>{$("#analyticsSku").value="";state.pages.analyticsData=state.pages.productQueries=state.pages.productQueryDetails=1;loadAnalyticsPage()};
$("#productQueryRows").onclick=e=>{const index=Number(e.target.closest("[data-query-detail]")?.dataset.queryDetail);if(!Number.isInteger(index)||!productQueryItems[index])return;analyticsDetail=productQueryItems[index];state.pages.productQueryDetails=1;loadProductQueryDetails()};
$("#shopPickerButton").onclick=()=>{const willOpen=$("#shopOptions").classList.contains("hidden");if(willOpen){document.querySelectorAll(".date-range-panel:not(.hidden)").forEach(panel=>panel.classList.add("hidden"));document.querySelectorAll(".date-range-pill[aria-expanded=true],.date-range-button[aria-expanded=true]").forEach(b=>{b.setAttribute("aria-expanded","false");b.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")});$("#channelOptions")?.classList.add("hidden");$("#channelPickerButton")?.setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy");Object.values(returnSelects).forEach(select=>select.close())}$("#shopOptions").classList.toggle("hidden",!willOpen);$("#shopPickerButton").setAttribute("aria-expanded",String(willOpen));$("#shopPickerMorph")?.morphTo(willOpen?"chevronUp":"chevronDown","snappy")};
$("#shopOptions").onclick=e=>{const option=e.target.closest("[data-shop]");if(!option)return;const newShop=Number(option.dataset.shop);const changed=state.shop!==newShop;applyShopSelection(newShop,true);document.querySelectorAll("#shopOptions [data-shop]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy");if(changed){const page=$(".page.active")?.id;if(page)loadPage(page).catch(err=>toast(err.message,true))}};
$("#channelPickerButton").onclick=()=>{const willOpen=$("#channelOptions").classList.contains("hidden");if(willOpen){document.querySelectorAll(".date-range-panel:not(.hidden)").forEach(panel=>panel.classList.add("hidden"));document.querySelectorAll(".date-range-pill[aria-expanded=true],.date-range-button[aria-expanded=true]").forEach(b=>{b.setAttribute("aria-expanded","false");b.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")});$("#shopOptions")?.classList.add("hidden");$("#shopPickerButton")?.setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy");Object.values(returnSelects).forEach(select=>select.close())}$("#channelOptions").classList.toggle("hidden",!willOpen);$("#channelPickerButton").setAttribute("aria-expanded",String(willOpen));$("#channelPickerMorph")?.morphTo(willOpen?"chevronUp":"chevronDown","snappy")};
$("#channelOptions").onclick=e=>{const option=e.target.closest("[data-channel]");if(!option)return;const newChan=option.dataset.channel;const changed=$("#channelFilter").value!==newChan;$("#channelFilter").value=newChan;const valEl=$("#channelPickerValue");if(valEl){valEl.textContent=option.querySelector(".option-label")?.textContent||option.textContent;valEl.classList.remove("shop-picker-swap");void valEl.offsetWidth;valEl.classList.add("shop-picker-swap")}document.querySelectorAll("#channelOptions [data-channel]").forEach(button=>button.setAttribute("aria-selected",String(button===option)));$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy");if(changed)$("#channelFilter").dispatchEvent(new Event("change"))};
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
let currentExpandedReason = null;
$("#reasonRows").onclick = async e => {
  const reasonBtn = e.target.closest("[data-reason]");
  if (!reasonBtn) return;
  const reason = reasonBtn.dataset.reason;
  const target = $("#reasonDetails");
  if (currentExpandedReason === reason && !target.classList.contains("hidden")) {
    target.classList.add("hidden");
    currentExpandedReason = null;
    document.querySelectorAll("#reasonRows .reason-link-btn").forEach(btn => btn.classList.remove("is-active"));
    return;
  }
  currentExpandedReason = reason;
  document.querySelectorAll("#reasonRows .reason-link-btn").forEach(btn => {
    btn.classList.toggle("is-active", btn.dataset.reason === reason);
  });
  const query = new URLSearchParams({shop_id: state.shop, reason, from: riskRange.start, to: riskRange.end});
  target.classList.remove("hidden");
  target.innerHTML = '<div class="reason-detail-loading"><morph-icon icon="sync" size="16" class="ozon-pulse" stroke-width="1.8"></morph-icon><span>原因对应订单加载中…</span></div>';
  try {
    const data = await api(`/api/risk/reasons?${query}`);
    target.innerHTML = `
      <div class="reason-detail-header">
        <div class="reason-detail-title">
          <morph-icon icon="alertTriangle" size="15" stroke-width="2"></morph-icon>
          <h3>${esc(reasonBtn.querySelector("span")?.textContent || reasonBtn.textContent.trim())} · 关联订单明细</h3>
        </div>
        <div class="reason-detail-actions">
          <span class="reason-detail-total">共 <b>${num(data.details.length, 0)}</b> 个异常订单</span>
          <button type="button" class="icon-button close-reason-details" aria-label="关闭明细" title="关闭明细"><morph-icon icon="x" size="14" stroke-width="2"></morph-icon></button>
        </div>
      </div>
      <div class="reason-detail-grid">
        ${data.details.map(r => `
          <div class="reason-detail-card">
            <div class="reason-card-head">
              <strong class="copyable" data-copy="${esc(r.posting_number)}" title="点击复制订单号">
                <morph-icon icon="copy" size="12" stroke-width="2"></morph-icon>
                ${esc(r.posting_number)}
              </strong>
            </div>
            <div class="reason-card-foot">
              <span class="shop-tag">${esc(r.shop_name)}</span>
              ${channelTag(r.channel)}
              <span class="pieces-count">× <b>${num(r.pieces, 0)}</b> 件</span>
            </div>
          </div>
        `).join("") || '<span class="muted">当前时间范围内没有对应订单。</span>'}
      </div>
    `;
    target.querySelector(".close-reason-details")?.addEventListener("click", () => {
      target.classList.add("hidden");
      currentExpandedReason = null;
      document.querySelectorAll("#reasonRows .reason-link-btn").forEach(btn => btn.classList.remove("is-active"));
    });
    target.scrollIntoView({behavior: "smooth", block: "nearest"});
  } catch (error) {
    target.innerHTML = `<span class="error">${esc(error.message)}</span>`;
  }
};
$("#prevPage").onclick=()=>{state.page--;loadOrders().catch(err=>toast(err.message,true))}; $("#nextPage").onclick=()=>{state.page++;loadOrders().catch(err=>toast(err.message,true))};
async function saveShopNames(){const s1=$("#shop1")?.value?.trim()||"",s2=$("#shop2")?.value?.trim()||"";if(!s1||!s2)return;const curr1=state.shops.find(s=>s.id===1)?.name,curr2=state.shops.find(s=>s.id===2)?.name;if(s1===curr1&&s2===curr2)return;try{await api("/api/shops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({1:s1,2:s2})});await loadShops();toast("店铺名称已自动保存")}catch(err){toast(err.message,true)}}
$("#shopForm").addEventListener("submit",e=>{e.preventDefault();saveShopNames()});
$("#shop1").addEventListener("change",saveShopNames);
$("#shop2").addEventListener("change",saveShopNames);
$("#shop1").addEventListener("blur",saveShopNames);
$("#shop2").addEventListener("blur",saveShopNames);
$("#dingtalkForm")?.addEventListener("submit",async e=>{e.preventDefault();try{const weekdays=[...document.querySelectorAll("#dingWeekdays input:checked")].map(input=>Number(input.value));await api("/api/dingtalk/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({daily_enabled:$("#dingEnabled").checked,push_time:$("#dingTime").value,weekdays})});toast("推送计划已保存");await loadDingtalk()}catch(err){toast(err.message,true)}});
$("#pushShopGrid")?.addEventListener("submit",e=>{const form=e.target.closest("form[data-push-form]");if(form){e.preventDefault();setPushSubscription(form)}});
$("#pushShopGrid")?.addEventListener("input",e=>{if(!e.target.matches("[data-push-url]"))return;const form=e.target.closest("[data-push-form]"),data=pushSubscriptionState[Number(form?.dataset.shop)];if(!form||!data)return;data.urlDraft=e.target.value;const label=form.querySelector("[data-push-set-label] span"),same=data.subscriptions?.some(row=>row.url===e.target.value.trim());if(label)label.textContent=same?"更新订阅":"注册订阅"});
$("#pushShopGrid")?.addEventListener("change",e=>{if(e.target.matches("[data-push-type]")){const form=e.target.closest("[data-push-form]"),data=pushSubscriptionState[Number(form?.dataset.shop)];if(data)data.selectedTypes=[...form.querySelectorAll("[data-push-type]:checked")].map(input=>input.value);return}if(e.target.matches("[data-push-enabled]"))togglePushSubscription(Number(e.target.dataset.shop),e.target.dataset.id,e.target)});
$("#pushShopGrid")?.addEventListener("click",e=>{const button=e.target.closest("[data-push-action]");if(!button)return;const shopId=Number(button.dataset.shop);if(button.dataset.pushAction==="check")checkPushWebhook(shopId);if(button.dataset.pushAction==="delete")deletePushSubscription(shopId,button.dataset.id)});
async function probeSingleShop(shopId){
  const target=$("#probeResult"+shopId),btn=document.querySelector(`[data-probe-single="${shopId}"]`);
  if(btn) btn.disabled=true;
  if(target) target.innerHTML=probeResult({status:"loading"});
  try{
    const res=await api(`/api/ozon/probe/${shopId}`,{method:"POST"});
    if(target) target.innerHTML=probeResult({...res,status:res.valid?"success":"error"});
    toast(`店铺 ${shopId} API 检测完成`);
  }catch(error){
    if(target) target.innerHTML=probeResult({valid:false,error:error.message,status:"error"});
    toast(error.message,true);
  }finally{
    if(btn) btn.disabled=false;
  }
}
$("#probeAllButton").onclick=async()=>{
  const btn=$("#probeAllButton");
  btn.disabled=true;
  state.shops.forEach(s=>{
    const el=$("#probeResult"+s.id);
    if(el) el.innerHTML=probeResult({status:"loading"});
  });
  try{
    await Promise.all(state.shops.map(async s=>{
      const target=$("#probeResult"+s.id);
      if(!target) return;
      try{
        const res=await api(`/api/ozon/probe/${s.id}`,{method:"POST"});
        target.innerHTML=probeResult({...res,status:res.valid?"success":"error"});
      }catch(error){
        target.innerHTML=probeResult({valid:false,error:error.message,status:"error"});
      }
    }));
    toast("API 连接与权限检测已完成");
  }catch(err){
    toast(err.message,true);
  }finally{
    btn.disabled=false;
  }
};
$("#probeShops")?.addEventListener("click",e=>{
  const btn=e.target.closest("[data-probe-single]");
  if(btn){
    const shopId=Number(btn.dataset.probeSingle);
    if(shopId) probeSingleShop(shopId);
  }
});
let importing = false;
const importFileValid = file => Boolean(file && file.name.toLowerCase().endsWith(".csv"));
function updateImportReady(message = "") {
  const file = $("#importFile").files[0],
        ready = Boolean($("#importShop").value && $("#importKind").value && importFileValid(file));
  $("#importSubmit").disabled = importing || !ready;
  const statusEl = $("#importStatus");
  if (statusEl) {
    if (message) statusEl.textContent = message;
    else if (!importing) statusEl.textContent = ready ? "已就绪，点击“开始导入”解析并导入" : "请选择店铺、渠道和 CSV 文件";
  }
}
function showImportFile(file) {
  const valid = importFileValid(file),
        panel = $("#importFilePanel"),
        nameEl = $("#importFileName"),
        sizeEl = $("#importFileSize"),
        chooseSpan = $("#importChooseFile span"),
        iconMorph = $("#importFileIcon");
  if (file) {
    nameEl.textContent = file.name;
    nameEl.title = file.name;
    sizeEl.textContent = `${num(file.size / 1024, 1)} KB · ${valid ? "CSV 格式验证通过" : "格式不支持，仅允许 .csv 文件"}`;
    if (chooseSpan) chooseSpan.textContent = "更换文件";
    panel.classList.toggle("is-invalid", !valid);
    panel.classList.toggle("is-ready", valid);
    iconMorph?.morphTo(valid ? "fileText" : "alertTriangle", "snappy");
    updateImportReady(!valid ? "请选择 .csv 格式的文件" : "");
  } else {
    nameEl.textContent = "点击选择或将 CSV 文件拖拽至此处";
    nameEl.removeAttribute("title");
    sizeEl.textContent = "支持标准 UTF-8 .csv 文件，单文件上限 50MB";
    if (chooseSpan) chooseSpan.textContent = "选择文件";
    panel.classList.remove("is-invalid", "is-ready");
    iconMorph?.morphTo("uploadCloud", "snappy");
    updateImportReady("");
  }
}
$("#importChooseFile").onclick = () => $("#importFile").click();
$("#importFilePanel").onclick = e => { if (!e.target.closest("button")) $("#importFile").click(); };
$("#importFile").onchange = () => showImportFile($("#importFile").files[0]);
for (const id of ["importShop", "importKind"]) $("#"+id).addEventListener("change", () => updateImportReady());
$("#importFilePanel").ondragover = e => { e.preventDefault(); e.currentTarget.classList.add("is-dragging"); };
$("#importFilePanel").ondragleave = e => e.currentTarget.classList.remove("is-dragging");
$("#importFilePanel").ondrop = e => {
  e.preventDefault();
  e.currentTarget.classList.remove("is-dragging");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  $("#importFile").files = transfer.files;
  showImportFile(file);
};
$("#importForm").addEventListener("submit", async e => {
  e.preventDefault();
  if (importing) return;
  const file = $("#importFile").files[0],
        shop = $("#importShop").value,
        kind = $("#importKind").value;
  if (!file || !shop || !kind || !importFileValid(file)) {
    updateImportReady("请完整选择店铺、渠道和 CSV 文件");
    return;
  }
  importing = true;
  const submitBtn = $("#importSubmit"),
        submitSpan = submitBtn.querySelector("span");
  if (submitSpan) submitSpan.textContent = "正在导入…";
  submitBtn.disabled = true;
  updateImportReady("正在上传并解析 CSV 数据，请稍候…");
  try {
    const result = await api(`/api/import/${kind}?shop_id=${shop}`, {
      method: "POST",
      headers: { "X-Filename": encodeURIComponent(file.name) },
      body: file
    });
    $("#importFile").value = "";
    showImportFile();
    updateImportReady(`成功导入 ${num(result.rows, 0)} 行数据`);
    toast(`已成功导入 ${result.rows} 行`);
    await loadImports();
  } catch (err) {
    updateImportReady(`导入失败：${err.message}`);
    toast(err.message, true);
  } finally {
    importing = false;
    if (submitSpan) submitSpan.textContent = "开始导入";
    updateImportReady($("#importStatus").textContent);
  }
});
const exportModules = {
  orders: { title: "订单数据", desc: "包含订单号、履约渠道、创单时间、发货状态及交易金额", icon: "package", tone: "blue" },
  risk: { title: "取消与风险分析", desc: "包含 SKU、渠道、货件及固定取消原因结构化数据", icon: "alertTriangle", tone: "peach" },
  returns: { title: "退货与异常订单", desc: "包含取消记录、客户退货申请及处理流转数据", icon: "rotateCcw", tone: "lavender" },
  complaints: { title: "异常投诉与赔付", desc: "包含投诉编号、状态、赔付金额及处理备注", icon: "messageSquareAlert", tone: "mint" }
};
$("#exportButtons").innerHTML = Object.entries(exportModules).map(([key, item]) => `
  <article class="export-card tone-${item.tone}">
    <div class="export-card-head">
      <strong class="export-card-title">${item.title}</strong>
      <div class="export-icon-badge"><morph-icon icon="${item.icon}" size="15" stroke-width="2"></morph-icon></div>
    </div>
    <p class="export-card-desc">${item.desc}</p>
    <div class="export-card-foot">
      <span class="export-fmt-tag">JSONL · AI友好</span>
      <button type="button" class="export-btn" data-export="${key}">
        <morph-icon icon="download" size="13" stroke-width="2"></morph-icon>
        <span>导出数据</span>
      </button>
    </div>
  </article>
`).join("");
function updateExportScope() {
  const shopName = state.shop ? state.shops.find(item => item.id === state.shop)?.name : "两店铺合并";
  const el = $("#exportScope");
  if (el) {
    el.innerHTML = `当前店铺：<span class="export-scope-tag">${esc(shopName || "两店铺合并")}</span> ｜ 时间范围：<span class="export-scope-tag">${exportRange.start} 至 ${exportRange.end}</span>`;
  }
}
$("#exportButtons").onclick = e => {
  const button = e.target.closest("[data-export]"), module = button?.dataset.export;
  if (!module) return;
  const query = new URLSearchParams({ shop_id: state.shop, date_from: exportRange.start, date_to: exportRange.end });
  button.disabled = true;
  const originalHtml = button.innerHTML;
  button.innerHTML = `<morph-icon icon="sync" size="13" class="ozon-pulse" stroke-width="2"></morph-icon><span>正在准备…</span>`;
  location.href = `/api/export/${module}?${query}`;
  setTimeout(() => {
    button.disabled = false;
    button.innerHTML = originalHtml;
  }, 1000);
};
$("#shortNameForm").onsubmit=async e=>{e.preventDefault();const sku=$("#shortSku").value.trim(),short_name=$("#shortName").value.trim();if(!sku){$("#shortSku").focus();return toast("请输入 SKU",true)}if(!short_name){$("#shortName").focus();return toast("请输入中文短名称",true)}await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"short_name",sku,short_name})});toast("短名称已保存");$("#shortNameForm").reset();await loadRules()};
$("#shortReset").onclick=()=>$("#shortNameForm").reset();$("#shortSearchForm").onsubmit=e=>{e.preventDefault();loadRules().catch(error=>toast(error.message,true))};$("#shortSearchClear").onclick=()=>{$("#shortSearch").value="";loadRules().catch(error=>toast(error.message,true))};
$("#shortRuleRows").onclick=async e=>{const edit=e.target.closest("[data-edit-short]")?.dataset.editShort,remove=e.target.closest("[data-delete-short]")?.dataset.deleteShort;if(edit){const row=ruleData.short_names.find(value=>value.sku===edit);$("#shortSku").value=row.sku;$("#shortName").value=row.short_name;$("#shortName").focus()}if(remove){await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"delete_short_name",sku:remove})});toast("短名称已删除");await loadRules()}};
$("#addMergeMember").onclick=()=>addMergeMember();$("#mergeMembers").onclick=e=>{if(e.target.closest("[data-remove-member]"))e.target.closest(".merge-member").remove()};$("#mergeReset").onclick=resetMergeForm;
$("#mergeForm").onsubmit=async e=>{e.preventDefault();const primary_offer_id=$("#primaryOffer").value.trim();if(!primary_offer_id){$("#primaryOffer").focus();return toast("请输入主货号",true)}const members=[...$("#mergeMembers").querySelectorAll(".merge-member")].map(row=>({key_type:row.querySelector("select").value,key_value:row.querySelector(".merge-member-value").value.trim()})).filter(m=>m.key_value);await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"merge",id:Number($("#mergeId").value||0),primary_offer_id,primary_sku:$("#primarySku").value.trim(),members})});toast("全局合并已保存");resetMergeForm();await loadRules()};
$("#mergeRuleList").onclick=async e=>{const edit=Number(e.target.closest("[data-edit-merge]")?.dataset.editMerge||0),dissolve=Number(e.target.closest("[data-dissolve]")?.dataset.dissolve||0);if(edit){const group=ruleData.groups.find(value=>value.id===edit);$("#mergeId").value=group.id;$("#primaryOffer").value=group.primary_offer_id||"";$("#primarySku").value=group.primary_sku||"";$("#mergeMembers").replaceChildren();group.members.filter(member=>!(member.key_type==="offer_id"&&member.key_value===group.primary_offer_id)).forEach(addMergeMember);if(!$("#mergeMembers").children.length)addMergeMember();$("#primaryOffer").focus()}if(dissolve){await api("/api/product-rules",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"dissolve",id:dissolve})});toast("合并关系已解散");resetMergeForm();await loadRules()}};
resetMergeForm();
const manualSyncModules = {
  orders: { title: "订单数据", desc: "拉取订单、商品明细及订单状态数据", scope: "受顶部时间范围影响", icon: "package", tone: "blue" },
  returns: { title: "退货数据", desc: "拉取退货与客户售后申请记录", scope: "受顶部时间范围影响", icon: "rotateCcw", tone: "peach" },
  stock: { title: "实时库存", desc: "拉取当前全量现货与快照数据", scope: "全量快照 · 实时", icon: "stock", tone: "mint" }
};
$("#syncButtons").innerHTML = Object.entries(manualSyncModules).map(([key, item]) => `
  <article class="sync-manual-card tone-${item.tone}" data-sync-module="${key}">
    <div class="sync-manual-head">
      <div class="sync-manual-meta">
        <strong class="sync-manual-title">${item.title}</strong>
        <span class="sync-scope-tag">${item.scope}</span>
      </div>
      <div class="sync-icon-badge">
        <morph-icon icon="${item.icon}" size="15" stroke-width="2"></morph-icon>
      </div>
    </div>
    <p class="sync-manual-desc">${item.desc}</p>
    <div class="sync-manual-foot">
      <button class="sync-pull-btn" type="button" data-module="${key}">
        <morph-icon icon="sync" size="13" stroke-width="2"></morph-icon>
        <span>拉取${syncNames[key]}</span>
      </button>
    </div>
  </article>
`).join("");
const today=new Date(); today.setHours(0,0,0,0);
const isoDate=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const localDate=value=>{const [year,month,day]=value.split("-").map(Number);return new Date(year,month-1,day)};
const shiftDays=(date,amount)=>new Date(date.getFullYear(),date.getMonth(),date.getDate()+amount);
const shiftMonths=(date,amount)=>new Date(date.getFullYear(),date.getMonth()+amount,1);
const threeMonthsAgo=(()=>{const target=new Date(today.getFullYear(),today.getMonth()-3,1);target.setDate(Math.min(today.getDate(),new Date(target.getFullYear(),target.getMonth()+1,0).getDate()));return target})();
const analyticsEnd=shiftDays(today,-3),analyticsStart=shiftDays(analyticsEnd,-29);
const formatShortDate=dStr=>{const parts=dStr.split("-");return `${parts[1]}.${parts[2]}`};
const formatRangeDisplay=(start,end,presetText)=>{
  if(presetText)return presetText;
  if(start===end)return formatShortDate(start);
  const [sY]=start.split("-"),[eY]=end.split("-");
  if(sY===eY)return `${formatShortDate(start)} - ${formatShortDate(end)}`;
  return `${sY.slice(2)}.${formatShortDate(start)} - ${eY.slice(2)}.${formatShortDate(end)}`;
};
function createDateRange(rootId,onChange,defaultPreset="3months"){
  const root=$(rootId);if(!root)return null;
  const range={start:isoDate(threeMonthsAgo),end:isoDate(today),selecting:false,view:new Date(today.getFullYear(),today.getMonth(),1),preset:"3months"};
  root.innerHTML=`<div class="date-range-wrap"><button class="date-range-pill" data-range-role="button" type="button" aria-haspopup="dialog" aria-expanded="false" title="时间范围：${range.start} 至 ${range.end}"><morph-icon icon="calendar" size="14" spring="snappy" stroke-width="1.8"></morph-icon><span class="date-range-text" data-range-role="label">近三个月</span><morph-icon icon="chevronDown" size="14" spring="snappy" stroke-width="1.8"></morph-icon></button><div class="date-range-panel header-date-panel hidden" data-range-role="panel" role="dialog" aria-label="选择日期范围"><div class="range-calendars"><div class="range-calendar"><div class="range-month-head"><button data-range-role="prev" type="button" aria-label="上个月"><morph-icon icon="chevronLeft" size="14" spring="snappy" stroke-width="1.8"></morph-icon></button><strong data-range-role="month-a"></strong><span></span></div><div class="range-weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div class="range-days" data-range-role="days-a"></div></div><div class="range-calendar"><div class="range-month-head"><span></span><strong data-range-role="month-b"></strong><button data-range-role="next" type="button" aria-label="下个月"><morph-icon icon="chevronRight" size="14" spring="snappy" stroke-width="1.8"></morph-icon></button></div><div class="range-weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div class="range-days" data-range-role="days-b"></div></div></div><div class="range-presets"><button type="button" data-range="today">今天</button><button type="button" data-range="3days">3天内</button><button type="button" data-range="7days">7天内</button><button type="button" data-range="3months">近三个月</button><button type="button" data-range="all">全部时间</button></div></div></div>`;
  const find=role=>root.querySelector(`[data-range-role="${role}"]`),label=find("label"),panel=find("panel"),button=find("button"),caret=button.querySelector("morph-icon:last-of-type");
  const month=(value,title,days)=>{title.textContent=`${value.getFullYear()}年 ${value.getMonth()+1}月`;const first=new Date(value.getFullYear(),value.getMonth(),1),last=new Date(value.getFullYear(),value.getMonth()+1,0),items=[];for(let index=0;index<(first.getDay()+6)%7;index++)items.push('<span class="range-blank"></span>');for(let day=1;day<=last.getDate();day++){const current=new Date(value.getFullYear(),value.getMonth(),day),key=isoDate(current),weekend=current.getDay()===0||current.getDay()===6,inRange=key>=range.start&&key<=range.end,edge=key===range.start||key===range.end,edgeStart=key===range.start&&range.start!==range.end,edgeEnd=key===range.end&&range.start!==range.end;items.push(`<button type="button" data-date="${key}" class="${weekend?'weekend ':''}${inRange?'in-range ':''}${edge?'range-edge ':''}${edgeStart?'range-start ':''}${edgeEnd?'range-end ':''}${key===isoDate(today)?'today':''}" aria-label="${value.getFullYear()}年${value.getMonth()+1}月${day}日">${day}</button>`)}days.innerHTML=items.join("")};
  const render=(dir=null)=>{
    month(range.view,find("month-a"),find("days-a"));
    month(shiftMonths(range.view,1),find("month-b"),find("days-b"));
    root.querySelectorAll("[data-range]").forEach(item=>item.classList.toggle("active",item.dataset.range===range.preset));
    if(dir){
      const cls=dir==="next"?"range-slide-left":"range-slide-right",cals=root.querySelector(".range-calendars");
      if(cals){cals.classList.remove("range-slide-left","range-slide-right");void cals.offsetWidth;cals.classList.add(cls)}
    }
  };
  const set=(start,end,presetName="",notify=true)=>{
    range.start=isoDate(start);range.end=isoDate(end);range.selecting=false;range.preset=presetName;
    const choices={today:"今天","3days":"3天内","7days":"7天内","3months":"近三个月",analytics30:"近30天（截至3天前）",all:"全部时间"};
    const presetText=choices[presetName]||"";
    label.textContent=formatRangeDisplay(range.start,range.end,presetText);
    label.classList.remove("shop-picker-swap");
    void label.offsetWidth;
    label.classList.add("shop-picker-swap");
    button.title=`时间范围：${range.start} 至 ${range.end}`;
    render();if(notify)onChange(range);
  };
  const preset=(name,notify=true)=>{const choices={today:[today,today],"3days":[shiftDays(today,-2),today],"7days":[shiftDays(today,-6),today],"3months":[threeMonthsAgo,today],analytics30:[analyticsStart,analyticsEnd],all:[new Date(2020,0,1),today]};set(...choices[name],name,notify)};
  root.onclick=e=>{
    if(e.target.closest(".date-range-pill,.date-range-button")){
      const willOpen=panel.classList.contains("hidden");
      document.querySelectorAll(".date-range-panel:not(.hidden)").forEach(p=>{if(p!==panel)p.classList.add("hidden")});
      document.querySelectorAll(".date-range-pill[aria-expanded=true],.date-range-button[aria-expanded=true]").forEach(b=>{if(b!==button){b.setAttribute("aria-expanded","false");b.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")}});
      $("#shopOptions")?.classList.add("hidden");
      $("#shopPickerButton")?.setAttribute("aria-expanded","false");
      $("#shopPickerMorph")?.morphTo("chevronDown","snappy");
      $("#channelOptions")?.classList.add("hidden");
      $("#channelPickerButton")?.setAttribute("aria-expanded","false");
      $("#channelPickerMorph")?.morphTo("chevronDown","snappy");
      Object.values(returnSelects).forEach(select=>select.close());
      panel.classList.toggle("hidden",!willOpen);
      button.setAttribute("aria-expanded",String(willOpen));
      if(caret)caret.morphTo(willOpen?"chevronUp":"chevronDown","snappy");
      if(willOpen)render();
      return;
    }
    const role=e.target.closest("[data-range-role]")?.dataset.rangeRole;
    if(role==="prev"||role==="next"){range.view=shiftMonths(range.view,role==="prev"?-1:1);render(role);return}
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
  preset(defaultPreset,false);return range;
}
const overviewRange=createDateRange("#overviewDateRange",()=>loadOverview().catch(error=>toast(error.message,true)));
const analyticsRange=createDateRange("#analyticsDateRange",()=>{state.pages.analyticsData=state.pages.productQueries=state.pages.productQueryDetails=1;loadAnalyticsPage()},"analytics30");
const orderRange=createDateRange("#orderDateRange",()=>{state.page=1;loadOrders().catch(error=>toast(error.message,true))});
const riskRange=createDateRange("#riskDateRange",()=>loadRisk().catch(error=>toast(error.message,true)));
const timelinessRange=createDateRange("#timelinessDateRange",()=>{state.pages.timeliness=1;loadTimeliness().catch(error=>toast(error.message,true))});
const returnsRange=createDateRange("#returnsDateRange",()=>{state.pages.returns=state.pages.rfbsReturns=1;loadReturnPage().catch(error=>toast(error.message,true))});
const complaintRange=createDateRange("#complaintDateRange",()=>{state.pages.shippingComplaints=state.pages.receivedDisputes=1;loadExceptionComplaints().catch(error=>toast(error.message,true))});
const exportRange=createDateRange("#exportDateRange",()=>updateExportScope());
const syncRange=createDateRange("#syncDateRange",()=>{});
const exchangeRateRange=createDateRange("#exchangeRateDateRange",()=>{});
document.addEventListener("click",e=>{const copyEl=e.target.closest(".copyable,[data-copy]");if(copyEl){const val=copyEl.dataset.copy?.trim();if(val&&val!=="暂无"&&val!=="—"){const done=()=>toast(`已复制：${val}`);if(navigator.clipboard?.writeText){navigator.clipboard.writeText(val).then(done).catch(()=>{const ta=document.createElement("textarea");ta.value=val;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();done()})}else{const ta=document.createElement("textarea");ta.value=val;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();done()}if(e.target.closest("summary"))e.preventDefault();e.stopPropagation();return}}const clickedWrap=e.target.closest(".date-range-wrap");document.querySelectorAll(".date-range-panel:not(.hidden)").forEach(p=>{if(!clickedWrap||!clickedWrap.contains(p)){p.classList.add("hidden");const b=p.closest(".date-range-wrap")?.querySelector(".date-range-pill,.date-range-button");if(b){b.setAttribute("aria-expanded","false");b.querySelector("morph-icon:last-of-type")?.morphTo("chevronDown","snappy")}}});const path=e.composedPath();if(!path.some(el=>el.id==="shopPickerButton"||el.id==="shopOptions")){$("#shopOptions").classList.add("hidden");$("#shopPickerButton").setAttribute("aria-expanded","false");$("#shopPickerMorph")?.morphTo("chevronDown","snappy")}if(!path.some(el=>el.id==="channelPickerButton"||el.id==="channelOptions")){$("#channelOptions").classList.add("hidden");$("#channelPickerButton").setAttribute("aria-expanded","false");$("#channelPickerMorph")?.morphTo("chevronDown","snappy")}if(!path.some(el=>el.hasAttribute?.("data-select-button")||el.hasAttribute?.("data-select-options")))Object.values(returnSelects).forEach(select=>select.close());if(!e.target.closest("#orderTrend"))$("#orderTrend .ozon-tooltip")?.classList.add("hidden")});
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
  if (!state.shop) return toast("请先在右上角选择一个店铺", true);
  if (syncRange.preset === "all") {
    const ok = await showConfirm({
      title: "确认开始全量拉取？",
      message: "整个时段将按自然月逐段拉取，耗时可能较长。确认开始？",
      confirmText: "确认开始",
      cancelText: "取消",
      icon: "alertTriangle"
    });
    if (!ok) return;
  }
  const originalHtml = button.innerHTML;
  button.disabled = true;
  button.innerHTML = `<morph-icon icon="sync" size="13" class="ozon-pulse" stroke-width="2"></morph-icon><span>拉取中…</span>`;
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
    button.innerHTML = originalHtml;
  }
};
$("#exchangeRateButton").onclick=async()=>{const button=$("#exchangeRateButton"),originalHtml=button.innerHTML;button.disabled=true;button.innerHTML=`<morph-icon icon="sync" size="13" class="ozon-pulse" stroke-width="2"></morph-icon><span>拉取中…</span>`;try{const result=await api("/api/exchange-rates/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({from:exchangeRateRange.start,to:exchangeRateRange.end})});toast(`汇率拉取完成：${num(result.records,0)} 条`);await loadExchangeRates()}catch(error){toast(error.message,true)}finally{button.disabled=false;button.innerHTML=originalHtml}};
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
