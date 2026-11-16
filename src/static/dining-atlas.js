'use strict';
const $ = selector => document.querySelector(selector);
const districts={'Gangnam-gu':'江南区','Jongno-gu':'钟路区','Jung-gu':'中区','Yongsan-gu':'龙山区','Seocho-gu':'瑞草区','Mapo-gu':'麻浦区','Songpa-gu':'松坡区','Seongdong-gu':'城东区','Yeongdeungpo-gu':'永登浦区','Gwangjin-gu':'广津区','Dongdaemun-gu':'东大门区','Eunpyeong-gu':'恩平区','Seodaemun-gu':'西大门区','Gangdong-gu':'江东区','Gwanak-gu':'冠岳区','Dongjak-gu':'铜雀区','Seongbuk-gu':'城北区','Gangseo-gu':'江西区','Yangcheon-gu':'阳川区','Gangbuk-gu':'江北区','Nowon-gu':'芦原区','Geumcheon-gu':'衿川区','Guro-gu':'九老区','Jungnang-gu':'中浪区','Dobong-gu':'道峰区'};
const cuisines={'Thai':'泰餐','Udon':'乌冬面','Doganitang':'牛膝骨汤','Chueotang':'泥鳅汤','Korean Contemporary':'现代韩餐','Korean':'韩餐','Contemporary':'现代料理','Innovative':'创新料理','Modern Cuisine':'现代料理','French':'法餐','French Contemporary':'现代法餐','Japanese':'日料','Sushi':'寿司','Chinese':'中餐','Mediterranean Cuisine':'地中海料理','Mexican':'墨西哥菜','Vegan':'纯素','Vegetarian':'素食','Noodles':'面食','Naengmyeon':'冷面','Memil-guksu':'荞麦面','Soba':'日式荞麦面','Ramen':'拉面','Gomtang':'牛骨汤','Dwaeji-gukbap':'猪肉汤饭','Dubu':'豆腐','Mandu':'饺子','Gejang':'酱蟹','Barbecue':'烤肉','Bulgogi':'烤牛肉','Samgyetang':'参鸡汤','Sujebi':'面片汤','Seolleongtang':'雪浓汤','Kalguksu':'刀切面','Chueo-tang':'泥鳅汤'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const config = ATLAS_CONFIG;
const isKorea = config.city === 'seoul';
const isHongKong = config.city === 'hong-kong';
const isMichelin = config.kind === 'michelin';
const isBars = config.kind === 'bars';
const multiCategory = config.kind === 'eat' || config.kind === 'bichi';
const guide = GUIDE_METADATA[config.city] || {};
const currency = config.currency || (isKorea ? '₩' : '¥');
const storageKey = isKorea ? 'seoul-michelin-favorites' : 'dining-atlas-' + config.id;
const hashKey = config.city === 'shanghai' ? 'v' : 'r';
const categoryDefs = isMichelin ? [
  ['3','三星','✳✳✳ 三星','#a94454','✳3'], ['2','二星','✳✳ 二星','#996137','✳2'],
  ['1','一星','✳ 一星','#71618e','✳'], ['bib','必比登','必比登推介','#4d7768','必']
] : isBars ? [
  ['精酿','精酿','精酿','#a57c3e','啤'],['鸡尾酒','鸡尾酒','鸡尾酒','#a94454','调'],
  ['威士忌','威士忌','威士忌','#87643f','威'],['爵士现场','爵士','爵士现场','#71618e','爵'],
  ['Livehouse','Livehouse','Livehouse','#486f8a','演'],['音乐剧场','音乐剧场','音乐剧场','#4d7768','剧'],
  ['电音俱乐部','电音','电音俱乐部','#97638d','电'],['大型夜店','夜店','大型夜店','#72517e','夜']
] : [
  ['both','双榜','必吃 × 扫街双榜','#a94454','双'],['bichi','必吃榜','必吃榜','#996137','吃'],
  ['saojie','扫街榜','扫街榜','#4d7768','街'],
  ...(config.kind === 'eat' ? [['3','三星','✳✳✳ 三星','#a94454','✳3'],['2','二星','✳✳ 二星','#996137','✳2'],['1','一星','✳ 一星','#71618e','✳'],['bib','必比登','必比登推介','#4d7768','必']] : [])
];
const categoryById = Object.fromEntries(categoryDefs.map(([id, short, label, color, symbol], rank) => [id, {short, label, color, symbol, rank}]));
const districtName = value => districts[value] || value || '区域未标注';
const cuisineName = value => ({'Cantonese':'粤菜','Shanghai':'上海菜','Shanghainese':'上海菜','Jiangsu Cuisine':'苏菜','Huaiyang':'淮扬菜','Hang Zhou':'杭帮菜','Zhejiang':'浙菜','Sichuan':'川菜','Sichuan Cuisine':'川菜','Beijing Cuisine':'京菜','Chao Zhou':'潮州菜','Taizhou':'台州菜','Seafood':'海鲜','Dim Sum':'点心','Hotpot':'火锅','Ningbo':'宁波菜','European Contemporary':'现代欧陆菜', ...cuisines}[value] || value || '菜系未标注');
const normalizeCategory = value => String(value || '').replace(/^michelin/, '');
function shanghaiDistrict(address) {
  const names = ['浦东新区','黄浦区','徐汇区','长宁区','静安区','普陀区','虹口区','杨浦区','闵行区','宝山区','嘉定区','金山区','松江区','青浦区','奉贤区','崇明区'];
  return names.find(name => address.includes(name)) || '';
}
function normalizeRecord(record) {
  const r = {...record};
  r.id = String(record.id || record.key);
  r.lat = record.lat ?? record.coords?.[0];
  r.lng = record.lng ?? record.coords?.[1];
  r.hasCoordinates = Number.isFinite(r.lat) && Number.isFinite(r.lng);
  r.address = record.address || record.addr || '';
  r.localName = record.koreanName || '';
  r.localAddress = record.koreanAddress || r.address;
  r.district = record.district || (config.city === 'shanghai' ? shanghaiDistrict(r.address) : '');
  r.cuisine = isBars ? record.genre : record.cuisine;
  r.tags = record.tags?.map(normalizeCategory) || [];
  if (config.kind === 'bichi') {
    r.tags = [record.bichi && record.saojie ? 'both' : '', record.bichi ? 'bichi' : '', record.saojie ? 'saojie' : ''].filter(Boolean);
  }
  r.category = isBars ? record.type : config.kind === 'eat' ? normalizeCategory(record.primary) : config.kind === 'bichi' ? r.tags[0] : normalizeCategory(record.category);
  if (!r.tags.length) r.tags = [r.category];
  r.priceBand = String(record.price || '').match(/[¥₩$]{1,4}/)?.[0] || '';
  r.priceText = isMichelin ? (r.priceBand || '价位未标注') : record.avg ? `人均约 ¥${record.avg}` : '人均待核实';
  r.priceKey = isMichelin ? r.priceBand : !record.avg ? 'unknown' : record.avg < 100 ? 'under100' : record.avg < 300 ? '100to300' : record.avg < 1000 ? '300to1000' : 'over1000';
  return r;
}
const all = ATLAS_RECORDS.map(normalizeRecord).sort((a,b) =>
  ((categoryById[a.category]?.rank ?? 99) - (categoryById[b.category]?.rank ?? 99)) || a.name.localeCompare(b.name, isKorea ? 'en' : 'zh-CN'));
const initialDetail = $('#detail').innerHTML;
const smallScreen = matchMedia('(max-width: 900px)');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let filtered = [], selectedCategories = new Set(), onlyFavorites = false, selected = null;
let position = null, distanceSort = false, favorites = new Set();
const markers = new Map();
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
  if (Array.isArray(saved)) favorites = new Set(saved.filter(id => all.some(r => r.id === id)));
} catch { /* Private browsing may disable persistent storage. */ }

function fillPage() {
  $('#cityEyebrow').textContent = config.eyebrow;
  $('#pageTitle').innerHTML = `${esc(config.headline)}<span>${esc(config.edition)}</span>`;
  $('#cityIntro').textContent = config.subtitle;
  $('#mapCity').textContent = config.cityName + (isKorea ? ' · 汉江两岸' : ' · 城市寻味');
  $('#mapCaption').textContent = config.englishName.toUpperCase() + ' / 上北 ↑';
  $('#footerMotto').textContent = config.englishName.toUpperCase() + ', ONE STOP AT A TIME.';
  $('#search').placeholder = isKorea ? '店名、韩文名、地址或菜系' : isBars ? '店名、地址、音乐类型或地铁' : '店名、地址或菜系';
  $('#map').setAttribute('aria-label', config.title + '互动地图');
  if (isBars) { $('#mapLabel').textContent = '场馆分布'; $('#cuisine').setAttribute('aria-label','音乐类型'); $('#cuisine').options[0].textContent = '全部音乐类型'; }
  for (const country of [...new Set(ATLAS_PAGES.map(page => page.country))]) {
    const group = document.createElement('optgroup');
    const countryPage = ATLAS_PAGES.find(page => page.country === country);
    group.label = countryPage.countryName + ' · ' + countryPage.countryEnglish;
    ATLAS_PAGES.filter(page => page.country === country).forEach(page => {
      const option = document.createElement('option');
      option.value = page.file; option.textContent = page.title + (page.kind === 'michelin' ? ' · ' + page.edition : '');
      option.selected = page.id === config.id; group.append(option);
    });
    $('#mapPicker').append(group);
  }
  $('#mapPicker').onchange = () => { location.href = $('#mapPicker').value; };
  const next = ATLAS_PAGES.filter(page => page.kind === 'michelin');
  const nextPage = next[(next.findIndex(page => page.city === config.city) + 1) % next.length];
  $('#nextCity').href = nextPage.file; $('#nextCity').textContent = '下一站：' + nextPage.cityName + ' ↗';
  const counts = Object.fromEntries(categoryDefs.map(([cat]) => [cat, all.filter(r => r.tags.includes(cat)).length]));
  $('#categories').innerHTML = `<button data-cat="all" class="active" aria-pressed="true">全部 <b>${all.length}</b></button>` + categoryDefs.map(([cat, short]) =>
    `<button data-cat="${esc(cat)}" aria-pressed="false" ${counts[cat] ? '' : 'disabled'}>${esc(short)} <b>${counts[cat]}</b></button>`).join('');
  $('#categories').classList.toggle('many', categoryDefs.length > 4);
  $('#legend').innerHTML = categoryDefs.filter(([id]) => counts[id]).map(([id,short,,color,symbol]) => `<span style="--c:${color}">${esc(symbol)} ${esc(short)}</span>`).join('');
  if (isMichelin) {
    $('#starTotal').textContent = (counts['3'] || 0) + (counts['2'] || 0) + (counts['1'] || 0);
    $('#bibTotal').textContent = counts.bib || 0;
  } else if (isBars) {
    $('#starTotal').textContent = all.filter(r => r.status === 'active').length; $('#starLabel').textContent = '营业场馆';
    $('#bibTotal').textContent = all.filter(r => r.status !== 'active').length; $('#bibLabel').textContent = '暂停 / 停业';
    $('#summaryNote').innerHTML = '从一杯好酒<br>到一场好现场';
  } else {
    $('#starTotal').textContent = all.length; $('#starLabel').textContent = '收录餐厅';
    $('#bibTotal').textContent = config.kind === 'eat' ? 3 : counts.both; $('#bibLabel').textContent = config.kind === 'eat' ? '榜单来源' : '双榜门店';
    $('.totals > i').textContent = '·';
    $('#summaryNote').innerHTML = '一张地图<br>串起街巷好味';
  }
  $('#priceFootnote').textContent = isMichelin ? (isHongKong ? '官方港币价位档位' : '价位为官方档位') : '人均仅供参考';
  const sourceDate = isMichelin ? guide.verifiedAt : '2026-09-12';
  $('#verifiedAt').textContent = (isMichelin ? '名单核验 ' : '资料截至 ') + (sourceDate || '').replaceAll('-', '.');
  for (const [id,field,translate] of [['district','district',districtName],['cuisine','cuisine',cuisineName]]) {
    [...new Set(all.map(r => r[field]).filter(Boolean))].sort((a,b) => translate(a).localeCompare(translate(b),'zh-CN')).forEach(value => {
      const option = document.createElement('option'); option.value = value; option.textContent = translate(value); $('#' + id).append(option);
    });
  }
  const priceOptions = isMichelin ? [1,2,3,4].map(n => [currency.repeat(n),currency.repeat(n)]) : [['under100','人均 < ¥100'],['100to300','¥100–299'],['300to1000','¥300–999'],['over1000','人均 ≥ ¥1000'],['unknown','人均待核实']];
  priceOptions.forEach(([value,label]) => { const option=document.createElement('option'); option.value=value; option.textContent=label; $('#price').append(option); });
  const options = {
    newOption: all.some(r => r.distinctionChange === 'new' || r.distinctionChange === 'promoted' || r.isNew),
    greenOption: all.some(r => r.greenStar), michelinOption: !isMichelin && !isBars,
    liveOption: isBars, closedOption: isBars, bookingOption: isBars, lateOption: isBars, idOption: isBars
  };
  Object.entries(options).forEach(([id,visible]) => { $('#' + id).hidden = !visible; });
  $('#advancedFilters').hidden = !Object.values(options).some(Boolean);
  for (const [id,field] of [['booking','booking'],['idCheck','id_check']]) {
    [...new Set(all.map(r => r[field]).filter(Boolean))].forEach(value => {
      const option=document.createElement('option'); option.value=value; option.textContent=value === 'none' ? '通常无需实名' : value; $('#' + id).append(option);
    });
  }
  $('#aboutTitle').textContent = config.title + ' · 收录说明';
  if (isMichelin) {
    $('#scopeSummary').textContent = `《米其林指南》${config.edition} 版，共 ${all.length} 家：${$('#starTotal').textContent} 家星级餐厅（三星 ${counts['3']} · 二星 ${counts['2']} · 一星 ${counts['1']}），以及 ${counts.bib} 家必比登推介。`;
    $('#scopeDetails').innerHTML = `<p>${esc(guide.scope || '')}。绿星为独立奖项，不另行重复计数；“新获奖 / 晋级”指年度评级变化，不代表新开业。</p><p>价位 ${currency} 至 ${currency.repeat(4)} 是官方${isHongKong ? '港币' : ''}消费档位，不是具体人均或套餐报价。城市全景仅调整浏览范围，不改变收录名单。请在出发前核对门店位置、营业与预订情况。</p>`;
    $('#sourceLinks').innerHTML = (guide.sources || []).map(source => `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.label)} ↗</a>`).join('');
    $('#verificationNote').textContent = `名单核验：${guide.verifiedAt || '待核实'}。${guide.verificationNote || ''}`;
  } else {
    $('#scopeSummary').textContent = isBars ? `共 ${all.length} 条上海夜生活场馆记录，包含暂停与停业的历史条目，不能将全部记录视为正在营业。` : `共 ${all.length} 家餐厅。${config.kind === 'eat' ? '必吃榜、扫街榜与米其林按原始坐标完全一致合并，保留全部榜单标签。' : '收录公开可核实的部分必吃榜与扫街榜门店，不是完整榜单。'} 分类支持多选，命中任一已选标签即显示。`;
    $('#scopeDetails').innerHTML = `<p>资料截至 2026-09-12，未在本次样式升级中重新逐店核验。${isBars ? '营业时间、人均、预约和实名要求见各场馆详情，演出以当场票务须知为准。' : '人均取自原店铺资料；没有具体数值的如实标为待核实，不由米其林档位估算。'}</p><p>坐标以 WGS-84 参考点位展示，部分门店为街道近似点；请按详情中的街道地址确认实际位置。暂停、停业或待核实信息保留在门店说明中。</p>`;
    $('#sourceLinks').innerHTML = isBars ? '<a href="https://www.showstart.com/" target="_blank" rel="noopener">秀动 ↗</a><a href="https://www.smartshanghai.com/" target="_blank" rel="noopener">SmartShanghai ↗</a>' : '<a href="https://www.dianping.com/" target="_blank" rel="noopener">大众点评 ↗</a><a href="https://www.amap.com/" target="_blank" rel="noopener">高德地图 ↗</a>';
    $('#verificationNote').textContent = GUIDE_METADATA.otherCollections.verificationNote;
  }
}
fillPage();
let toastTimer;
function toast(message) { $('#toast').textContent=message; $('#toast').classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(() => $('#toast').classList.remove('show'),3500); }
function scrollToElement(element, block='nearest') { element.scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth',block}); }
function setView(view) {
  $('#explorer').dataset.view=view;
  document.querySelectorAll('.view-switch button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.view===view)));
  if(view==='map') map.invalidateSize({pan:false});
}
document.querySelectorAll('.view-switch button').forEach(button=>{button.onclick=()=>{setView(button.dataset.view);if($('#explorer').getBoundingClientRect().top<70)scrollToElement($('#explorer'),'start');};});
$('.skip-link').onclick=event=>{event.preventDefault();setView('directory');$('#search').focus();};
const map=L.map('map',{zoomControl:false}).setView(config.center,12);
L.control.zoom({position:'topright'}).addTo(map);
let dark=false,tileErrors=0;
const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
tiles.on('loading',()=>{tileErrors=0;});tiles.on('tileerror',()=>{if(++tileErrors>3)$('#tileError').hidden=false;});tiles.on('load',()=>{if(tileErrors===0)$('#tileError').hidden=true;});
$('#retryTiles').onclick=()=>{tileErrors=0;$('#tileError').hidden=true;tiles.redraw();};
const landmarkLayer=L.layerGroup().addTo(map);
config.landmarks.forEach(([name,lat,lng])=>L.circleMarker([lat,lng],{radius:3,weight:1,color:'#fff',fillColor:'#9d8e79',fillOpacity:1}).bindTooltip(name,{permanent:true,direction:'right',className:'landmark',offset:[5,0]}).addTo(landmarkLayer));
$('#landmarks').onclick=()=>{const on=map.hasLayer(landmarkLayer);if(on)map.removeLayer(landmarkLayer);else landmarkLayer.addTo(map);$('#landmarks').setAttribute('aria-pressed',String(!on));};
$('#theme').onclick=()=>{dark=!dark;$('#map').classList.toggle('dark-map',dark);$('#theme').textContent=dark?'浅色':'深色';$('#theme').setAttribute('aria-pressed',String(dark));};
$('#capital').onclick=()=>{map.setView(config.overview.slice(0,2),config.overview[2]);toast(config.cityName+'全景 · 点位仍按当前筛选显示');};
function fit(){const points=filtered.filter(r=>r.hasCoordinates);if(points.length)map.fitBounds(points.map(r=>[r.lat,r.lng]),{padding:[45,55],maxZoom:14});else toast(filtered.length?'这些记录暂未核实坐标，可在名录查看说明':'当前筛选没有门店');}
$('#fit').onclick=fit;
smallScreen.addEventListener('change',()=>{map.invalidateSize({pan:false});if(selected?.hasCoordinates)map.setView([selected.lat,selected.lng],15,{animate:false});else fit();});
function distance(r){if(!position||!r.hasCoordinates)return null;const rad=Math.PI/180,a=(r.lat-position.lat)*rad,b=(r.lng-position.lng)*rad,h=Math.sin(a/2)**2+Math.cos(position.lat*rad)*Math.cos(r.lat*rad)*Math.sin(b/2)**2;return 6371*2*Math.asin(Math.sqrt(Math.min(1,h)));}
function distText(r){const d=distance(r);return d===null?'':d<1?Math.round(d*1000)+' m':d.toFixed(1)+' km';}
let userMarker;
function locate(sort=false){
  if(!navigator.geolocation){toast('此浏览器不支持定位');return;}
  $('#locate').textContent='定位中…';$('#locate').disabled=true;
  navigator.geolocation.getCurrentPosition(p=>{
    position={lat:p.coords.latitude,lng:p.coords.longitude};if(userMarker)map.removeLayer(userMarker);
    userMarker=L.marker([position.lat,position.lng],{icon:L.divIcon({className:'',html:'<div class="user-dot"></div>',iconSize:[15,15],iconAnchor:[7,7]})}).addTo(map).bindTooltip('我的位置');
    $('#locate').textContent='◎ 更新位置';$('#locate').disabled=false;if(sort)distanceSort=true;render();if(!sort)map.setView([position.lat,position.lng],13);toast('已定位 · 名录距离为直线距离');
  },()=>{$('#locate').textContent='◎ 定位';$('#locate').disabled=false;toast('未能获取位置，请检查浏览器定位权限后重试');},{enableHighAccuracy:true,timeout:12000,maximumAge:60000});
}
$('#locate').onclick=()=>locate();$('#distance').onclick=()=>{if(!position){locate(true);return;}distanceSort=!distanceSort;render();};
function save(id){
  const focused=document.activeElement,fromDetail=focused?.id==='detailSave',fromRow=focused?.dataset.save===id;
  if(favorites.has(id))favorites.delete(id);else favorites.add(id);
  try{localStorage.setItem(storageKey,JSON.stringify([...favorites]));}catch{toast('浏览器未允许保存，收藏本次会话有效');}
  render();
  if(fromDetail&&selected)$('#detailSave').focus({preventScroll:true});
  else if(fromRow)([...$('#list').querySelectorAll('[data-save]')].find(button=>button.dataset.save===id)||$('#favoriteFilter')).focus({preventScroll:true});
}
function crossMichelin(r) {
  if (isMichelin || isBars || !r.michelin || ['3','2','1','bib'].includes(r.category)) return null;
  return { '-1': {label:'必比登推介',symbol:'必'}, '1': {label:'✳ 一星',symbol:'✳'}, '2': {label:'✳✳ 二星',symbol:'✳2'}, '3': {label:'✳✳✳ 三星',symbol:'✳3'} }[String(r.michelin)] || null;
}
function icon(r,active=false) {
  const def=categoryById[r.category], cross=crossMichelin(r);
  return L.divIcon({className:'pin'+(active?' active':''),html:`<div class="pin-body" style="--c:${def?.color||'#746573'}"><span>${esc(def?.symbol||'·')}</span></div>${cross?`<span class="pin-award" aria-label="米其林${esc(cross.label)}">${esc(cross.symbol)}</span>`:''}`,iconSize:[30,37],iconAnchor:[15,35],tooltipAnchor:[0,-29]});
}
function awardBadges(r){
  const cross=crossMichelin(r);
  const change=r.distinctionChange==='new'?'新获奖':r.distinctionChange==='promoted'?'晋级':r.isNew?'新上榜 / 晋级':'';
  return `${cross?`<span class="michelin-cross">米其林 ${esc(cross.label)}</span>`:''}${r.greenStar?'<span class="green-star">✧ 米其林绿星</span>':''}${change?`<span class="award-note">${esc(config.edition)} ${change}</span>`:''}${r.status==='closed'?'<span class="status-note">已停业</span>':r.status==='suspended'?'<span class="status-note">暂停营业</span>':''}${r.directoryStatus==='not-listed'?'<span class="status-note notice">实时目录未收录 · 请核实</span>':''}`;
}
function hasMichelin(r){return ['3','2','1','bib'].some(tag=>r.tags.includes(tag))||Boolean(r.michelin);}
function clearSelection(updateHash=true){selected=null;$('#detail').className='detail';$('#detail').innerHTML=initialDetail;if(updateHash&&/^#(?:r|v)=/.test(location.hash))history.replaceState(null,'',location.pathname+location.search);}
function render(){
  const query=$('#search').value.trim().toLocaleLowerCase(),district=$('#district').value,cuisine=$('#cuisine').value,price=$('#price').value,scrollTop=$('#list').scrollTop;
  filtered=all.filter(r=>(!selectedCategories.size||[...selectedCategories].some(cat=>r.tags.includes(cat)))&&(!onlyFavorites||favorites.has(r.id))&&(!district||r.district===district)&&(!cuisine||r.cuisine===cuisine)&&(!price||r.priceKey===price)&&
    (!$('#onlyNew').checked||r.distinctionChange==='new'||r.distinctionChange==='promoted'||r.isNew)&&(!$('#onlyGreen').checked||r.greenStar)&&(!$('#onlyMichelin').checked||hasMichelin(r))&&
    (!$('#onlyLive').checked||r.live)&&(!$('#hideClosed').checked||r.status==='active')&&(!$('#booking').value||r.booking===$('#booking').value)&&(!$('#idCheck').value||r.id_check===$('#idCheck').value)&&
    (!$('#onlyLate').checked||(r.close&&r.close>='02:00'&&r.close<'12:00'))&&
    (!query||[r.name,r.localName,r.englishName,r.address,r.localAddress,districtName(r.district),cuisineName(r.cuisine),r.cuisine,r.metro,r.type].join(' ').toLocaleLowerCase().includes(query)));
  if(distanceSort&&position)filtered.sort((a,b)=>(distance(a)??Infinity)-(distance(b)??Infinity));
  if(selected&&!filtered.some(r=>r.id===selected.id))clearSelection();
  $('#resultCount').textContent=filtered.length+' 家';$('#mobileCount').textContent=filtered.length;$('#favoriteCount').textContent=favorites.size;$('#mapCount').textContent=filtered.some(r=>!r.hasCoordinates)?`${filtered.filter(r=>r.hasCoordinates).length} 个点位 / ${filtered.length} 条记录`:`显示 ${filtered.length} / ${all.length} 家`;
  $('#filterHint').textContent=distanceSort?'按直线距离排列':multiCategory?'多选分类 · 命中任一':'按'+(isMichelin?'评级':'类型')+'排列';$('#distance').setAttribute('aria-pressed',String(distanceSort));
  $('#list').innerHTML=filtered.length?filtered.map((r,i)=>`
    <article class="row ${selected?.id===r.id?'active':''}" data-id="${esc(r.id)}"><button class="row-open" data-select="${esc(r.id)}" aria-label="查看 ${esc(r.name)}" ${selected?.id===r.id?'aria-current="true"':''}>
    <span class="rank" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><span class="row-main"><span class="row-title">${esc(r.name)}</span>${r.localName||r.englishName?`<span class="row-ko">${esc(r.localName||r.englishName)}</span>`:''}
    <span class="row-meta"><span class="rating" style="--c:${categoryById[r.category]?.color}">${esc(categoryById[r.category]?.label||r.category)}</span><span>${esc(cuisineName(r.cuisine))}</span><span>${esc(r.priceText)}</span></span>
    <span class="row-meta">${esc(districtName(r.district))}${position&&r.hasCoordinates?' · '+distText(r):''}${!r.hasCoordinates?'<span class="status-note notice">坐标待核实</span>':''}${awardBadges(r)}</span></span></button>
    <button class="save ${favorites.has(r.id)?'saved':''}" data-save="${esc(r.id)}" aria-label="${favorites.has(r.id)?'取消收藏':'收藏'} ${esc(r.name)}" aria-pressed="${favorites.has(r.id)}">${favorites.has(r.id)?'♥':'♡'}</button></article>`).join(''):
    `<div class="empty">${onlyFavorites&&!favorites.size?'还没有收藏的餐厅。<br>点击门店旁的 ♡，存下下一站。':'没有符合条件的门店。<br>试试其他店名或放宽筛选条件。'}<button data-reset>查看全部门店</button></div>`;
  $('#list').scrollTop=scrollTop;
  const visible=new Set(filtered.map(r=>r.id));
  for(const [id,marker]of markers){if(!visible.has(id)){map.removeLayer(marker);markers.delete(id);}}
  for(const r of filtered.filter(r=>r.hasCoordinates)){const active=selected?.id===r.id;let marker=markers.get(r.id);if(!marker){marker=L.marker([r.lat,r.lng],{icon:icon(r,active),title:r.name,alt:r.name,riseOnHover:true}).bindTooltip(esc(r.name)+' · '+esc(categoryById[r.category]?.label||r.category)).addTo(map);marker.on('click',()=>select(r.id,false));markers.set(r.id,marker);}else if(marker._atlasActive!==active)marker.setIcon(icon(r,active));marker._atlasActive=active;marker.setZIndexOffset(active?1000:0);}
  $('#categories').querySelectorAll('button').forEach(button=>{const active=button.dataset.cat==='all'?!selectedCategories.size:selectedCategories.has(button.dataset.cat);button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  $('#favoriteFilter').setAttribute('aria-pressed',String(onlyFavorites));if(selected)showDetail(selected);
}
function resetFilters(){selectedCategories.clear();onlyFavorites=false;distanceSort=false;['search','district','cuisine','price','booking','idCheck'].forEach(id=>{$('#'+id).value='';});document.querySelectorAll('.advanced input').forEach(input=>{input.checked=false;});}
function select(id,pan=true,fromHash=false){
  const r=all.find(item=>item.id===id||item.key===id);if(!r)return;if(fromHash&&!filtered.some(item=>item.id===r.id))resetFilters();selected=r;if(smallScreen.matches)setView('map');render();
  history.replaceState(null,'','#'+hashKey+'='+encodeURIComponent(r.id));if(pan&&r.hasCoordinates)map.flyTo([r.lat,r.lng],15,{animate:!reducedMotion.matches,duration:.5});
  const row=[...$('#list').children].find(node=>node.dataset.id===r.id);if(row&&!smallScreen.matches)$('#list').scrollTo({top:row.offsetTop-$('#list').offsetTop,behavior:reducedMotion.matches?'instant':'smooth'});if(smallScreen.matches)scrollToElement($('#detail'));
}
function detailsCopy(r){
  const facts=isBars?[['营业时间',r.open_days],['打烊',r.close],['预约',r.booking],['入场要求',r.id_check==='none'?'通常无需实名（以单场须知为准）':r.id_check],['票价',r.ticket],['容量',r.capacity?`${r.capacity} 人（参考）`:''],['地铁',r.metro],['氛围',r.vibe],['核实日期',r.updated]]:[['地址提示',r.mnemonic&&r.mnemonic!==r.address?r.mnemonic:''],['官方价位',!isMichelin?r.priceBand:''],['电话',r.phone]];
  return `<div class="detail-copy">${r.desc?`<p>${esc(r.desc)}</p>`:''}${r.note?`<p>${esc(r.note)}</p>`:''}${r.directoryNote?`<p>${esc(r.directoryNote)}</p>`:''}<dl>${facts.filter(([,value])=>value!==undefined&&value!==null&&value!=='').map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}</dd>`).join('')}</dl></div>`;
}
function showDetail(r){
  const query=encodeURIComponent((r.localName||r.name)+' '+r.localAddress);
  const koreanLinks=`<a href="https://map.naver.com/p/search/${query}" target="_blank" rel="noopener">Naver 地图 ↗</a><a href="https://map.kakao.com/link/search/${query}" target="_blank" rel="noopener">Kakao 地图 ↗</a><a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name+' '+r.address+' Seoul')}" target="_blank" rel="noopener">Google 地图 ↗</a>`;
  const chinaLinks=r.hasCoordinates?'<span id="detail-links"><a id="detail-nav">百度导航</a><a id="detail-poi">百度店铺</a></span>':`<a id="detail-poi" href="${esc(VenueLinks.poi(r).web)}">百度搜索店名 ↗</a>`;
  const hongKongLink=isHongKong?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name+' '+r.address+' 香港 Hong Kong')}" target="_blank" rel="noopener">Google 地图 ↗</a>`:'';
  const official=r.url&&r.directoryStatus!=='not-listed'?`<a href="${esc(r.url)}" target="_blank" rel="noopener">米其林详情 ↗</a>`:'';
  $('#detail').className='detail selected';$('#detail').innerHTML=`
    <div class="detail-top"><div><div class="detail-meta" style="color:${categoryById[r.category]?.color}">${esc(categoryById[r.category]?.label||r.category)} · ${esc(cuisineName(r.cuisine))} · ${esc(r.priceText)}</div><h2>${esc(r.name)}</h2>${r.localName||r.englishName?`<div class="ko">${esc(r.localName||r.englishName)}</div>`:''}<div class="row-meta">${awardBadges(r)}</div></div><button class="detail-save" id="detailSave" aria-label="${favorites.has(r.id)?'取消收藏':'收藏'} ${esc(r.name)}" aria-pressed="${favorites.has(r.id)}">${favorites.has(r.id)?'♥':'♡'}</button></div>
    <p class="address">⌖ ${esc(r.localAddress||'地址待核实，请向门店确认')}${isKorea?'<br>'+esc(r.address)+', Seoul':''}${position&&r.hasCoordinates?'<br>距你 '+distText(r)+'（直线距离）':''}</p>${detailsCopy(r)}
    <div class="actions">${isKorea?koreanLinks:hongKongLink+chinaLinks}${official}<button id="copyAddress">复制${isKorea?'韩文':''}地址</button><button id="share">分享门店</button></div>
    ${(r.src_url||[]).length?`<div class="record-sources">${r.src_url.map((url,i)=>`<a href="${esc(url)}" target="_blank" rel="noopener">来源 ${i+1} ↗</a>`).join('')}</div>`:''}`;
  if(!isKorea&&r.hasCoordinates){const links=VenueLinks.mount();links.update({...r,coords:[r.lat,r.lng]},position?[position.lat,position.lng]:null);$('#detail-links').style.display='contents';}
  $('#detailSave').onclick=()=>save(r.id);$('#copyAddress').disabled=!r.localAddress;$('#copyAddress').onclick=()=>copy(r.localAddress,'地址已复制');$('#share').onclick=async()=>{if(navigator.share){try{await navigator.share({title:r.name+' · '+config.title,url:location.href});return;}catch(error){if(error.name==='AbortError')return;}}await copy(location.href,'门店链接已复制');};
}
async function copy(text,message){try{await navigator.clipboard.writeText(text);toast(message);}catch{toast('复制未成功，请从详情中选择文字复制');}}
$('#list').onclick=event=>{const saveButton=event.target.closest('[data-save]');if(saveButton){save(saveButton.dataset.save);return;}const openButton=event.target.closest('[data-select]');if(openButton){select(openButton.dataset.select);return;}if(event.target.closest('[data-reset]')){resetFilters();render();fit();}};
$('#categories').onclick=event=>{const button=event.target.closest('[data-cat]');if(!button||button.disabled)return;const cat=button.dataset.cat;if(cat==='all')selectedCategories.clear();else if(multiCategory){if(selectedCategories.has(cat))selectedCategories.delete(cat);else selectedCategories.add(cat);}else selectedCategories=new Set([cat]);render();$('#list').scrollTop=0;};
['search','district','cuisine','price','booking','idCheck','onlyNew','onlyGreen','onlyMichelin','onlyLive','hideClosed','onlyLate'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',()=>{render();$('#list').scrollTop=0;}));
$('#favoriteFilter').onclick=()=>{onlyFavorites=!onlyFavorites;render();};$('#reset').onclick=()=>{resetFilters();render();fit();};
$('#aboutBtn').onclick=$('#aboutFooter').onclick=()=>$('#about').showModal();$('#closeAbout').onclick=()=>$('#about').close();$('#about').onclick=event=>{if(event.target===$('#about')){const rect=event.target.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)event.target.close();}};
document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key==='k'){event.preventDefault();setView('directory');$('#search').focus();}});
render();fit();
function restoreHash(){const params=new URLSearchParams(location.hash.slice(1)),id=params.get('r')||params.get('v');if(id&&all.some(r=>r.id===id||r.key===id))select(id,true,true);else{clearSelection(false);render();}}
restoreHash();window.addEventListener('hashchange',restoreHash);
// Shanghai's maintained metro overlay is optional and independent of the base map.
if(typeof ATLAS_METRO_LINES !== 'undefined'){
  const chosen=new Set(),layer=L.layerGroup().addTo(map);
  $('#metroControl').hidden=false;
  $('#metroOptions').innerHTML='<p>上海核心区 · 已收录 13 条线路<br>为局部参考图层，不含全部线路</p>'+ATLAS_METRO_LINES.map(line=>`<label><input type="checkbox" value="${esc(line.id)}"><span style="color:${line.color}">●</span> ${esc(line.name)}</label>`).join('');
  function drawMetro(){
    layer.clearLayers();const stationIds=new Set();
    ATLAS_METRO_LINES.filter(line=>chosen.has(line.id)).forEach(line=>{L.polyline(line.path,{color:line.color,weight:3,opacity:.65}).addTo(layer);line.stations.forEach(id=>stationIds.add(id));});
    ATLAS_METRO_STATIONS.filter(station=>stationIds.has(station.id)).forEach(station=>L.circleMarker(station.coords,{radius:3,color:'#6b6259',weight:1,fillColor:'#fff',fillOpacity:1}).bindTooltip(esc(station.name)).addTo(layer));
  }
  $('#metroOptions').onchange=event=>{const input=event.target;if(input.checked)chosen.add(input.value);else chosen.delete(input.value);drawMetro();};
  document.addEventListener('click',event=>{if(!event.target.closest('#metroControl'))$('#metroControl').open=false;});
}
