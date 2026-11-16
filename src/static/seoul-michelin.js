'use strict';
const $=s=>document.querySelector(s),colors={'3':'#a94454','2':'#bb8050','1':'#71618e',bib:'#4d7768'},labels={'3':'✳✳✳ 三星','2':'✳✳ 二星','1':'✳ 一星',bib:'必比登推介'};
const districts={'Gangnam-gu':'江南区','Jongno-gu':'钟路区','Jung-gu':'中区','Yongsan-gu':'龙山区','Seocho-gu':'瑞草区','Mapo-gu':'麻浦区','Songpa-gu':'松坡区','Seongdong-gu':'城东区','Yeongdeungpo-gu':'永登浦区','Gwangjin-gu':'广津区','Dongdaemun-gu':'东大门区','Eunpyeong-gu':'恩平区','Seodaemun-gu':'西大门区','Gangdong-gu':'江东区','Gwanak-gu':'冠岳区','Dongjak-gu':'铜雀区','Seongbuk-gu':'城北区','Gangseo-gu':'江西区','Yangcheon-gu':'阳川区','Gangbuk-gu':'江北区','Nowon-gu':'芦原区','Geumcheon-gu':'衿川区','Guro-gu':'九老区','Jungnang-gu':'中浪区','Dobong-gu':'道峰区'};
const cuisines={'Thai':'泰餐','Udon':'乌冬面','Doganitang':'牛膝骨汤','Chueotang':'泥鳅汤','Korean Contemporary':'现代韩餐','Korean':'韩餐','Contemporary':'现代料理','Innovative':'创新料理','Modern Cuisine':'现代料理','French':'法餐','French Contemporary':'现代法餐','Japanese':'日料','Sushi':'寿司','Chinese':'中餐','Mediterranean Cuisine':'地中海料理','Mexican':'墨西哥菜','Vegan':'纯素','Vegetarian':'素食','Noodles':'面食','Naengmyeon':'冷面','Memil-guksu':'荞麦面','Soba':'日式荞麦面','Ramen':'拉面','Gomtang':'牛骨汤','Dwaeji-gukbap':'猪肉汤饭','Dubu':'豆腐','Mandu':'饺子','Gejang':'酱蟹','Barbecue':'烤肉','Bulgogi':'烤牛肉','Samgyetang':'参鸡汤','Sujebi':'面片汤','Seolleongtang':'雪浓汤','Kalguksu':'刀切面','Chueo-tang':'泥鳅汤'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const all = [...SEOUL_RESTAURANTS].sort((a, b) =>
  ({'3': 0, '2': 1, '1': 2, bib: 3}[a.category] - {'3': 0, '2': 1, '1': 2, bib: 3}[b.category]) || a.name.localeCompare(b.name));
const guide = GUIDE_METADATA.seoul;
const initialDetail = $('#detail').innerHTML;
const smallScreen = window.matchMedia('(max-width: 900px)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let filtered = [], category = 'all', onlyFavorites = false, selected = null;
let position = null, distanceSort = false, favorites = new Set();
const markers = new Map();
try {
  const stored = JSON.parse(localStorage.getItem('seoul-michelin-favorites') || '[]');
  if (Array.isArray(stored)) favorites = new Set(stored.filter(id => all.some(r => r.id === id)));
} catch { /* Storage can be unavailable in private browsing. */ }

let toastTimer;
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 3500);
}
function scrollToElement(element, block = 'nearest') {
  element.scrollIntoView({behavior: reducedMotion.matches ? 'instant' : 'smooth', block});
}
function setView(view) {
  $('#explorer').dataset.view = view;
  document.querySelectorAll('.view-switch button').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.view === view));
  });
  if (view === 'map') map.invalidateSize({pan: false});
}
document.querySelectorAll('.view-switch button').forEach(button => {
  button.onclick = () => {
    setView(button.dataset.view);
    if ($('#explorer').getBoundingClientRect().top < 70) scrollToElement($('#explorer'), 'start');
  };
});
$('.skip-link').onclick = event => {
  event.preventDefault();
  setView('directory');
  $('#search').focus();
};

const map = L.map('map', {zoomControl: false}).setView([37.543, 127.007], 12);
L.control.zoom({position: 'topright'}).addTo(map);
let dark = false, tileErrors = 0;
const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);
tiles.on('loading', () => { tileErrors = 0; });
tiles.on('tileerror', () => { if (++tileErrors > 3) $('#tileError').hidden = false; });
tiles.on('load', () => { if (tileErrors === 0) $('#tileError').hidden = true; });
$('#retryTiles').onclick = () => { tileErrors = 0; $('#tileError').hidden = true; tiles.redraw(); };
const landmarkLayer = L.layerGroup().addTo(map);
[
  ['景福宫 경복궁', 37.5796, 126.9770], ['首尔站 서울역', 37.5547, 126.9707],
  ['南山塔 N서울타워', 37.5512, 126.9882], ['汝矣岛 여의도', 37.5250, 126.9244],
  ['弘大入口 홍대입구', 37.5572, 126.9254], ['江南站 강남역', 37.4979, 127.0276],
  ['圣水 성수', 37.5446, 127.0559], ['蚕室 잠실', 37.5133, 127.1001], ['龙山站 용산역', 37.5298, 126.9647]
].forEach(([name, lat, lng]) => L.circleMarker([lat, lng], {
  radius: 3, weight: 1, color: '#fff', fillColor: '#9d8e79', fillOpacity: 1
}).bindTooltip(name, {permanent: true, direction: 'right', className: 'landmark', offset: [5, 0]}).addTo(landmarkLayer));
$('#landmarks').onclick = () => {
  const on = map.hasLayer(landmarkLayer);
  if (on) map.removeLayer(landmarkLayer); else landmarkLayer.addTo(map);
  $('#landmarks').setAttribute('aria-pressed', String(!on));
};
$('#theme').onclick = () => {
  dark = !dark;
  $('#map').classList.toggle('dark-map', dark);
  $('#theme').textContent = dark ? '浅色' : '深色';
  $('#theme').setAttribute('aria-pressed', String(dark));
};
$('#capital').onclick = () => {
  map.setView([37.48, 126.96], 10);
  toast(`首都圈视野：当前收录的 ${all.length} 家餐厅均在首尔市内`);
};
function fit() {
  if (filtered.length) map.fitBounds(filtered.map(r => [r.lat, r.lng]), {padding: [45, 55], maxZoom: 14});
  else toast('当前筛选没有餐厅');
}
$('#fit').onclick = fit;
smallScreen.addEventListener('change', () => {
  map.invalidateSize({pan: false});
  if (selected) map.setView([selected.lat, selected.lng], 15, {animate: false});
  else fit();
});
function distance(r) {
  if (!position) return null;
  const rad = Math.PI / 180, a = (r.lat - position.lat) * rad, b = (r.lng - position.lng) * rad;
  const h = Math.sin(a / 2) ** 2 + Math.cos(position.lat * rad) * Math.cos(r.lat * rad) * Math.sin(b / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}
function distText(r) {
  const d = distance(r);
  return d === null ? '' : d < 1 ? Math.round(d * 1000) + ' m' : d.toFixed(1) + ' km';
}
let userMarker;
function locate(sort = false) {
  if (!navigator.geolocation) { toast('此浏览器不支持定位'); return; }
  $('#locate').textContent = '定位中…';
  $('#locate').disabled = true;
  navigator.geolocation.getCurrentPosition(p => {
    position = {lat: p.coords.latitude, lng: p.coords.longitude};
    if (userMarker) map.removeLayer(userMarker);
    userMarker = L.marker([position.lat, position.lng], {
      icon: L.divIcon({className: '', html: '<div class="user-dot"></div>', iconSize: [15, 15], iconAnchor: [7, 7]})
    }).addTo(map).bindTooltip('我的位置');
    $('#locate').textContent = '◎ 更新位置';
    $('#locate').disabled = false;
    if (sort) distanceSort = true;
    render();
    if (!sort) map.setView([position.lat, position.lng], 13);
    toast('已定位 · 名录距离为直线距离');
  }, () => {
    $('#locate').textContent = '◎ 定位';
    $('#locate').disabled = false;
    toast('未能获取位置，请检查浏览器定位权限后重试');
  }, {enableHighAccuracy: true, timeout: 12000, maximumAge: 60000});
}
$('#locate').onclick = () => locate();
$('#distance').onclick = () => {
  if (!position) { locate(true); return; }
  distanceSort = !distanceSort;
  render();
};
function save(id) {
  const focused = document.activeElement;
  const fromDetail = focused?.id === 'detailSave';
  const fromRow = focused?.dataset.save === id;
  if (favorites.has(id)) favorites.delete(id); else favorites.add(id);
  try { localStorage.setItem('seoul-michelin-favorites', JSON.stringify([...favorites])); }
  catch { toast('浏览器未允许保存，收藏本次会话有效'); }
  render();
  if (fromDetail && selected) $('#detailSave').focus({preventScroll: true});
  else if (fromRow) {
    const button = [...$('#list').querySelectorAll('[data-save]')].find(b => b.dataset.save === id);
    (button || $('#favoriteFilter')).focus({preventScroll: true});
  }
}
function icon(r, active = false) {
  return L.divIcon({
    className: 'pin' + (active ? ' active' : ''),
    html: `<div class="pin-body" style="--c:${colors[r.category]}"><span>${r.category === 'bib' ? '必' : '✳' + (r.category === '1' ? '' : r.category)}</span></div>`,
    iconSize: [30, 37], iconAnchor: [15, 35], tooltipAnchor: [0, -29]
  });
}
function awardBadges(r) {
  const change = r.distinctionChange === 'new' ? '2026 新获奖' : r.distinctionChange === 'promoted' ? '2026 晋级' : '';
  return `${r.greenStar ? '<span class="green-star">✧ 米其林绿星</span>' : ''}${change ? `<span class="award-note">${change}</span>` : ''}`;
}
function clearSelection(updateHash = true) {
  selected = null;
  $('#detail').className = 'detail';
  $('#detail').innerHTML = initialDetail;
  if (updateHash && location.hash.startsWith('#r=')) history.replaceState(null, '', location.pathname + location.search);
}
function render() {
  const query = $('#search').value.trim().toLocaleLowerCase();
  const district = $('#district').value, cuisine = $('#cuisine').value, price = $('#price').value;
  const scrollTop = $('#list').scrollTop;
  filtered = all.filter(r =>
    (category === 'all' || r.category === category) && (!onlyFavorites || favorites.has(r.id)) &&
    (!district || r.district === district) && (!cuisine || r.cuisine === cuisine) && (!price || r.price === price) &&
    (!query || [r.name, r.koreanName, r.address, r.koreanAddress, districts[r.district], cuisines[r.cuisine], r.cuisine]
      .join(' ').toLocaleLowerCase().includes(query)));
  if (distanceSort && position) filtered.sort((a, b) => distance(a) - distance(b));
  if (selected && !filtered.some(r => r.id === selected.id)) clearSelection();
  $('#resultCount').textContent = filtered.length + ' 家';
  $('#mobileCount').textContent = filtered.length;
  $('#favoriteCount').textContent = favorites.size;
  $('#mapCount').textContent = `显示 ${filtered.length} / ${all.length} 家`;
  $('#filterHint').textContent = distanceSort ? '按直线距离排列' : '按星级排列';
  $('#distance').setAttribute('aria-pressed', String(distanceSort));
  $('#list').innerHTML = filtered.length ? filtered.map((r, i) => `
    <article class="row ${selected?.id === r.id ? 'active' : ''}" data-id="${esc(r.id)}">
      <button class="row-open" data-select="${esc(r.id)}" aria-label="查看 ${esc(r.name)}" ${selected?.id === r.id ? 'aria-current="true"' : ''}>
        <span class="rank" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span>
        <span class="row-main"><span class="row-title">${esc(r.name)}</span><span class="row-ko">${esc(r.koreanName)}</span>
          <span class="row-meta"><span class="rating" style="--c:${colors[r.category]}">${labels[r.category]}</span><span>${esc(cuisines[r.cuisine] || r.cuisine)}</span><span>${esc(r.price)}</span></span>
          <span class="row-meta">${esc(districts[r.district] || r.district)}${position ? ' · ' + distText(r) : ''}${awardBadges(r)}</span>
        </span>
      </button>
      <button class="save ${favorites.has(r.id) ? 'saved' : ''}" data-save="${esc(r.id)}" aria-label="${favorites.has(r.id) ? '取消收藏' : '收藏'} ${esc(r.name)}" aria-pressed="${favorites.has(r.id)}">${favorites.has(r.id) ? '♥' : '♡'}</button>
    </article>`).join('') : `<div class="empty">${onlyFavorites && !favorites.size ? '还没有收藏的餐厅。<br>点击餐厅旁的 ♡，存下下一餐。' : '没有符合条件的餐厅。<br>试试其他店名或放宽筛选条件。'}<button data-reset>查看全部餐厅</button></div>`;
  $('#list').scrollTop = scrollTop;
  const visible = new Set(filtered.map(r => r.id));
  for (const [id, marker] of markers) {
    if (!visible.has(id)) { map.removeLayer(marker); markers.delete(id); }
  }
  for (const r of filtered) {
    const active = selected?.id === r.id;
    let marker = markers.get(r.id);
    if (!marker) {
      marker = L.marker([r.lat, r.lng], {icon: icon(r, active), title: r.name, alt: r.name, riseOnHover: true})
        .bindTooltip(esc(r.name) + ' · ' + labels[r.category]).addTo(map);
      marker.on('click', () => select(r.id, false));
      markers.set(r.id, marker);
    } else if (marker._atlasActive !== active) marker.setIcon(icon(r, active));
    marker._atlasActive = active;
    marker.setZIndexOffset(active ? 1000 : 0);
  }
  $('#categories').querySelectorAll('button').forEach(button => {
    button.classList.toggle('active', button.dataset.cat === category);
    button.setAttribute('aria-pressed', String(button.dataset.cat === category));
  });
  $('#favoriteFilter').setAttribute('aria-pressed', String(onlyFavorites));
  if (selected) showDetail(selected);
}
function resetFilters() {
  category = 'all'; onlyFavorites = false; distanceSort = false;
  ['search', 'district', 'cuisine', 'price'].forEach(id => { $('#' + id).value = ''; });
}
function select(id, pan = true, fromHash = false) {
  const r = all.find(item => item.id === id);
  if (!r) return;
  // Shared links must also work while an incompatible filter is active.
  if (fromHash && !filtered.some(item => item.id === id)) resetFilters();
  selected = r;
  if (smallScreen.matches) setView('map');
  render();
  history.replaceState(null, '', '#r=' + encodeURIComponent(id));
  if (pan) map.flyTo([r.lat, r.lng], 15, {animate: !reducedMotion.matches, duration: .5});
  const row = [...$('#list').children].find(node => node.dataset.id === id);
  if (row && !smallScreen.matches) $('#list').scrollTo({top: row.offsetTop - $('#list').offsetTop, behavior: reducedMotion.matches ? 'instant' : 'smooth'});
  if (smallScreen.matches) scrollToElement($('#detail'));
}
function showDetail(r) {
  const query = encodeURIComponent((r.koreanName || r.name) + ' ' + (r.koreanAddress || r.address));
  $('#detail').className = 'detail selected';
  $('#detail').innerHTML = `
    <div class="detail-top"><div><div class="detail-meta" style="color:${colors[r.category]}">${labels[r.category]} · ${esc(cuisines[r.cuisine] || r.cuisine)} · ${esc(r.price)}</div>
      <h2>${esc(r.name)}</h2><div class="ko">${esc(r.koreanName)}</div><div class="row-meta">${awardBadges(r)}</div></div>
      <button class="detail-save" id="detailSave" aria-label="${favorites.has(r.id) ? '取消收藏' : '收藏'} ${esc(r.name)}" aria-pressed="${favorites.has(r.id)}">${favorites.has(r.id) ? '♥' : '♡'}</button></div>
    <p class="address">⌖ ${esc(r.koreanAddress || r.address)}<br>${esc(r.address)}, Seoul${position ? '<br>距你 ' + distText(r) + '（直线距离）' : ''}</p>
    <div class="actions"><a href="https://map.naver.com/p/search/${query}" target="_blank" rel="noopener">Naver 地图 ↗</a>
      <a href="https://map.kakao.com/link/search/${query}" target="_blank" rel="noopener">Kakao 地图 ↗</a>
      <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name + ' ' + r.address + ' Seoul')}" target="_blank" rel="noopener">Google 地图 ↗</a>
      <a href="${esc(r.url)}" target="_blank" rel="noopener">米其林详情 ↗</a><button id="copyAddress">复制韩文地址</button><button id="share">分享餐厅</button></div>`;
  $('#detailSave').onclick = () => save(r.id);
  $('#copyAddress').onclick = () => copy(r.koreanAddress || r.address, '地址已复制');
  $('#share').onclick = async () => {
    if (navigator.share) {
      try { await navigator.share({title: r.name + ' · 首尔米其林地图', url: location.href}); return; }
      catch (error) { if (error.name === 'AbortError') return; }
    }
    await copy(location.href, '餐厅链接已复制');
  };
}
async function copy(text, message) {
  try { await navigator.clipboard.writeText(text); toast(message); }
  catch { toast('复制未成功，请从详情中选择文字复制'); }
}
$('#list').onclick = event => {
  const saveButton = event.target.closest('[data-save]');
  if (saveButton) { save(saveButton.dataset.save); return; }
  const openButton = event.target.closest('[data-select]');
  if (openButton) { select(openButton.dataset.select); return; }
  if (event.target.closest('[data-reset]')) { resetFilters(); render(); fit(); }
};
$('#categories').onclick = event => {
  const button = event.target.closest('[data-cat]');
  if (button) { category = button.dataset.cat; render(); $('#list').scrollTop = 0; }
};
['search', 'district', 'cuisine', 'price'].forEach(id => $('#' + id).addEventListener(id === 'search' ? 'input' : 'change', () => { render(); $('#list').scrollTop = 0; }));
$('#favoriteFilter').onclick = () => { onlyFavorites = !onlyFavorites; render(); };
$('#reset').onclick = () => { resetFilters(); render(); fit(); };
$('#aboutBtn').onclick = $('#aboutFooter').onclick = () => $('#about').showModal();
$('#closeAbout').onclick = () => $('#about').close();
$('#about').onclick = event => {
  if (event.target === $('#about')) {
    const rect = event.target.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
  }
};
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
    event.preventDefault(); setView('directory'); $('#search').focus();
  }
});
for (const [id, field, translations] of [['district', 'district', districts], ['cuisine', 'cuisine', cuisines]]) {
  [...new Set(all.map(r => r[field]))].sort((a, b) => (translations[a] || a).localeCompare(translations[b] || b, 'zh-CN')).forEach(value => {
    const option = document.createElement('option');
    option.value = value; option.textContent = translations[value] || value; $('#' + id).append(option);
  });
}
const counts = all.reduce((result, r) => { result[r.category] = (result[r.category] || 0) + 1; return result; }, {});
const stars = (counts['3'] || 0) + (counts['2'] || 0) + (counts['1'] || 0);
$('#starTotal').textContent = stars;
$('#bibTotal').textContent = counts.bib || 0;
$('#categories').querySelectorAll('button').forEach(button => {
  button.querySelector('b').textContent = button.dataset.cat === 'all' ? all.length : counts[button.dataset.cat] || 0;
});
$('#verifiedAt').textContent = '名单核验 ' + guide.verifiedAt.replaceAll('-', '.');
$('#scopeSummary').textContent = `共 ${all.length} 家：${stars} 家星级餐厅（三星 ${counts['3']} · 二星 ${counts['2']} · 一星 ${counts['1']}），以及 ${counts.bib} 家必比登推介。`;
$('#sourceLinks').innerHTML = guide.sources.map(source => `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.label)} ↗</a>`).join('');
$('#verificationNote').textContent = `名单核验：${guide.verifiedAt}。${guide.verificationNote}`;
render();
fit();
function restoreHash() {
  const id = new URLSearchParams(location.hash.slice(1)).get('r');
  if (id && all.some(r => r.id === id)) select(id, true, true);
  else { clearSelection(false); render(); }
}
restoreHash();
window.addEventListener('hashchange', restoreHash);
