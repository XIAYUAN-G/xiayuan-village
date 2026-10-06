// 12306 多段拼车票规划器 v4 —— 后端（零依赖，Node 22+，缓存用内置 node:sqlite）
// 新增：SQLite 缓存层 / 跨站换乘检测与惩罚 / 晚点风险提示 / 价格日历 / 住宿总成本 / 自动推荐途经点
const http = require('http');
const fs = require('fs');
const path = require('path');

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const PORT = process.env.PORT || 3721;
const MAX_DAYS = 15;

// ---------- 缓存层（node:sqlite，不可用则降级内存） ----------
let db = null;
try {
  const { DatabaseSync } = require('node:sqlite');
  db = new DatabaseSync(path.join(__dirname, 'cache.db'));
  db.exec('CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, v TEXT, e INTEGER)');
  db.exec('CREATE INDEX IF NOT EXISTS idx_cache_e ON cache(e)');
} catch (e) {
  console.warn('node:sqlite 不可用，降级为内存缓存:', e.message);
}
const memCache = new Map();
function cacheGet(k) {
  const now = Date.now();
  if (db) {
    const r = db.prepare('SELECT v, e FROM cache WHERE k = ?').get(k);
    if (r) { if (r.e > now) return JSON.parse(r.v); db.prepare('DELETE FROM cache WHERE k = ?').run(k); }
    return null;
  }
  const it = memCache.get(k);
  if (it) { if (it.e > now) return it.v; memCache.delete(k); }
  return null;
}
function cacheSet(k, v, ttlMs) {
  if (db) db.prepare('INSERT OR REPLACE INTO cache(k, v, e) VALUES(?, ?, ?)').run(k, JSON.stringify(v), Date.now() + ttlMs);
  else memCache.set(k, { v, e: Date.now() + ttlMs });
}
const TTL_TICKET = 10 * 60e3, TTL_PRICE = 30 * 60e3, TTL_ROUTE = 24 * 3600e3, TTL_STATION = 12 * 3600e3;

// ---------- cookie 会话 ----------
let cookieJar = {};
async function initSession(force = false) {
  if (!force && Object.keys(cookieJar).length) return;
  const res = await fetch('https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc', {
    headers: { 'User-Agent': UA, 'Referer': 'https://www.12306.cn/' },
  });
  const set = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
  for (const c of set) {
    const [kv] = c.split(';');
    const i = kv.indexOf('=');
    if (i > 0) cookieJar[kv.slice(0, i).trim()] = kv.slice(i + 1).trim();
  }
  await res.arrayBuffer().catch(() => {});
}
function cookieHeader() {
  return Object.entries(cookieJar).map(([k, v]) => `${k}=${v}`).join('; ');
}
function saveCookies(res) {
  const set = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
  for (const c of set) {
    const [kv] = c.split(';');
    const i = kv.indexOf('=');
    if (i > 0) cookieJar[kv.slice(0, i).trim()] = kv.slice(i + 1).trim();
  }
}

// ---------- 车站表 ----------
let stations = [];
async function loadStations() {
  if (stations.length) return stations;
  const cached = cacheGet('stations');
  if (cached) { stations = cached; return stations; }
  const res = await fetch('https://kyfw.12306.cn/otn/resources/js/framework/station_name.js', { headers: { 'User-Agent': UA } });
  const text = await res.text();
  stations = [];
  for (const m of text.matchAll(/@([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\d+\|\d+\|([^|]*)/g)) {
    stations.push({ id: m[1], name: m[2], code: m[3], py: m[4], spy: m[5], city: m[6] });
  }
  cacheSet('stations', stations, TTL_STATION);
  return stations;
}
function matchStations(q) {
  q = q.trim();
  const byName = stations.filter(s => s.name === q);
  if (byName.length) return byName;
  const contains = stations.filter(s => s.name.includes(q));
  if (contains.length) return contains;
  const ql = q.toLowerCase();
  const byPy = stations.filter(s => s.py === ql || s.spy === ql || s.py.startsWith(ql));
  if (byPy.length) return byPy;
  return stations.filter(s => s.city.includes(q));
}
const stripDir = n => n.replace(/[东西南北]站?$/, '');

// ---------- 余票查询 ----------
async function queryTickets(fromCode, toCode, date) {
  const key = `tickets:${fromCode}:${toCode}:${date}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  const qs = `leftTicketDTO.train_date=${date}&leftTicketDTO.from_station=${fromCode}&leftTicketDTO.to_station=${toCode}&purpose_codes=ADULT`;
  let result = [];
  outer:
  for (const ep of ['queryG', 'queryZ', 'query']) {
    for (let attempt = 0; attempt < 2; attempt++) {
      await initSession();
      try {
        const res = await fetch(`https://kyfw.12306.cn/otn/leftTicket/${ep}?${qs}`, {
          headers: {
            'User-Agent': UA,
            'Referer': 'https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc',
            'X-Requested-With': 'XMLHttpRequest',
            'Cookie': cookieHeader(),
          },
        });
        saveCookies(res);
        const j = await res.json();
        if (j && j.data && Array.isArray(j.data.result)) {
          result = j.data.result;
          if (result.length) break outer; // 拿到票就收工
        } else {
          await initSession(true); // 可能没 cookie/被风控，换会话重试
        }
      } catch { await initSession(true); }
    }
  }
  cacheSet(key, result, result.length ? TTL_TICKET : 60e3);
  return result;
}

function parseTrain(row) {
  const f = row.split('|');
  if (f.length < 40) return null;
  const dep = f[8], arr = f[9], dur = f[10];
  if (!/^\d{2}:\d{2}$/.test(dep) || !/^\d{2}:\d{2}$/.test(arr) || !/^\d+:\d{2}$/.test(dur)) return null;
  return {
    secret: f[0], trainNo: f[2], code: f[3],
    fromCode: f[4], toCode: f[5], startCode: f[6], endCode: f[7],
    dep, arr, dur, canBuy: f[11] === 'Y',
    fromNo: f[16], toNo: f[17],
    seatTypes: f[35] || f[34] || '',
  };
}

// ---------- 票价查询 ----------
async function queryPrice(t, date) {
  const key = `price:${t.trainNo}:${t.fromNo}:${t.toNo}:${date}`;
  const cached = cacheGet(key);
  if (cached !== null) return cached; // 可能是缓存的 null（确认无价）
  let result = null;
  for (let attempt = 0; attempt < 2 && result === null; attempt++) {
    try {
      await initSession();
      const res = await fetch(
        `https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice?train_no=${t.trainNo}&from_station_no=${t.fromNo}&to_station_no=${t.toNo}&seat_types=${encodeURIComponent(t.seatTypes || 'OM9')}&train_date=${date}`,
        { headers: { 'User-Agent': UA, 'Referer': 'https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc', 'Cookie': cookieHeader() } });
      saveCookies(res);
      const j = await res.json();
      if (j && j.status && j.data) {
        const d = j.data;
        const pick = code => {
          let v = d[code];
          if (typeof v === 'object' && v) v = v[0] ?? v.price;
          return typeof v === 'string' ? parseFloat(v.replace(/[¥,]/g, '')) : (typeof v === 'number' ? v : null);
        };
        const prices = {};
        const map = { 'O': '二等座', 'M': '一等座', '9': '商务座', 'WZ': '无座', 'A1': '硬座', '3': '硬卧', '4': '软卧', 'F': '动卧', '6': '高级软卧', '2': '软座' };
        for (const [code, name] of Object.entries(map)) {
          const p = pick(code);
          if (p && p > 0) prices[name] = p;
        }
        if (Object.keys(prices).length) result = prices;
      } else if (j && j.status === false) break; // 明确无价
    } catch { /* 重试 */ }
  }
  cacheSet(key, result, result ? TTL_PRICE : 60e3);
  return result;
}

// ---------- 列车经停站（自动推荐途经点用） ----------
async function queryTrainRoute(trainNo, fromCode, toCode, date) {
  const key = `route:${trainNo}:${date}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  let result = null;
  try {
    await initSession();
    const res = await fetch(
      `https://kyfw.12306.cn/otn/czxx/queryByTrainNo?train_no=${trainNo}&from_station_telecode=${fromCode}&to_station_telecode=${toCode}&depart_date=${date}`,
      { headers: { 'User-Agent': UA, 'Referer': 'https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc', 'Cookie': cookieHeader() } });
    saveCookies(res);
    const j = await res.json();
    if (j && j.data && j.data.data && j.data.data.length) result = j.data.data;
  } catch { /* 忽略 */ }
  if (result) cacheSet(key, result, TTL_ROUTE);
  return result;
}

// ---------- 工具 ----------
function hmsToMin(s) { const [h, m] = s.split(':').map(Number); return h * 60 + m; }
function fmtMin(min) {
  const d = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), m = min % 60;
  if (d > 0) return `${d}天${h ? h + '小时' : ''}${m ? m + '分' : ''}`;
  return `${h ? h + '小时' : ''}${m ? m + '分' : ''}` || '0分';
}
function fmtStay(min) {
  if (min < 180) return `换乘 ${Math.round(min)} 分钟`;
  if (min < 1440) return `停留 ${fmtMin(min)}（可玩）`;
  return `停留 ${fmtMin(min)}（${Math.floor(min / 1440)} 晚，可玩）`;
}
const SEAT_ORDER = ['二等座', '一等座', '商务座', '硬座', '硬卧', '软座', '软卧', '动卧', '无座'];

async function pool(items, n, fn) {
  const ret = []; let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const idx = i++; ret[idx] = await fn(items[idx], idx); }
  }));
  return ret;
}

// ---------- 一条腿在日期区间内的所有车次+票价 ----------
async function getLegOptions(fromName, toName, dates, seatPref, priceCap) {
  const froms = matchStations(fromName);
  const tos = matchStations(toName);
  if (!froms.length || !tos.length) {
    throw new Error(`车站无法识别: ${!froms.length ? fromName : toName}`);
  }
  const tasks = [];
  for (let di = 0; di < dates.length; di++) {
    for (const a of froms) for (const b of tos) tasks.push({ di, date: dates[di], a, b });
  }
  const raw = await pool(tasks, 4, async t => {
    const rows = await queryTickets(t.a.code, t.b.code, t.date);
    return { di: t.di, date: t.date, fromName: t.a.name, toName: t.b.name, trains: rows.map(parseTrain).filter(Boolean) };
  });

  const candidates = [];
  const seen = new Set();
  for (const r of raw) {
    let ts = r.trains.filter(t => t.fromCode !== t.toCode);
    if (ts.length > priceCap) {
      const cheap = ts.filter(t => !/^[GDC]/.test(t.code)).slice(0, 25);
      const fast = [...ts].sort((a, b) => hmsToMin(a.dur) - hmsToMin(b.dur)).filter(t => !cheap.includes(t)).slice(0, Math.max(10, priceCap - cheap.length));
      ts = [...cheap, ...fast];
    }
    for (const t of ts) {
      const k = t.code + t.dep + r.date;
      if (seen.has(k)) continue;
      seen.add(k);
      candidates.push({ t, di: r.di, date: r.date, fromName: r.fromName, toName: r.toName });
    }
  }

  const priced = await pool(candidates, 8, async c => {
    const prices = await queryPrice(c.t, c.date);
    if (!prices) return null;
    const seat = seatPref && prices[seatPref] ? seatPref : SEAT_ORDER.find(s => prices[s] != null);
    if (!seat) return null;
    const depMin = hmsToMin(c.t.dep), durMin = hmsToMin(c.t.dur);
    return {
      code: c.t.code, trainNo: c.t.trainNo, seat,
      price: prices[seat], allPrices: prices,
      fromName: c.fromName, toName: c.toName,
      dep: c.t.dep, arr: c.t.arr, dur: c.t.dur,
      depMin, arrMin: depMin + durMin, durMin,
      dateIndex: c.di, date: c.date, canBuy: c.t.canBuy,
    };
  });
  const opts = priced.filter(Boolean);
  for (const o of opts) { o.absDep = o.dateIndex * 1440 + o.depMin; o.absArr = o.dateIndex * 1440 + o.arrMin; }
  opts.sort((a, b) => a.absDep - b.absDep);
  return opts;
}

// ---------- 核心：多日 DP（含跨站惩罚 + 住宿总成本） ----------
const CROSS_STATION_PENALTY = 90; // 跨站换乘需多留的分钟数（打车）
const TIGHT_TRANSFER = 30;        // 晚点风险阈值

function solvePlan(legs, stayMin, mode, totalDays, hotelPerNight, K = 5) {
  const totalMin = totalDays * 1440;
  const hotel = hotelPerNight > 0 ? hotelPerNight : 0;
  const hotelNightsOf = p => Math.max(0, Math.floor(p.lastArr / 1440) - p.firstDateIdx - p.overnightCount);
  const total = p => p.cost + (hotel ? hotelNightsOf(p) * hotel : 0);
  const better = (a, b) => {
    if (mode === 'time') {
      const da = a.lastArr - a.firstDep, db = b.lastArr - b.firstDep;
      return da !== db ? da < db : total(a) < total(b);
    }
    if (mode === 'money') return total(a) !== total(b) ? total(a) < total(b) : (a.lastArr - a.firstDep) < (b.lastArr - b.firstDep);
    const sa = total(a) + (a.lastArr - a.firstDep) * 2, sb = total(b) + (b.lastArr - b.firstDep) * 2;
    return sa !== sb ? sa < sb : total(a) < total(b);
  };

  let prev = legs[0].map(t => (t.absArr >= totalMin ? [] : [{
    cost: t.price, firstDep: t.absDep, lastArr: t.absArr,
    firstDateIdx: t.dateIndex, overnightCount: t.arrMin >= 1440 ? 1 : 0, path: [t],
  }]));

  for (let li = 1; li < legs.length; li++) {
    const cur = [];
    for (const t of legs[li]) {
      if (t.absArr >= totalMin) { cur.push([]); continue; }
      const best = [];
      for (const states of prev) for (const p of states) {
        const cross = p.path[p.path.length - 1].toName !== t.fromName;
        const gap = t.absDep - p.lastArr;
        const need = stayMin + (cross && gap < 360 ? CROSS_STATION_PENALTY : 0);
        if (gap < need) continue;
        best.push({
          cost: p.cost + t.price,
          firstDep: p.firstDep, lastArr: t.absArr,
          firstDateIdx: p.firstDateIdx,
          overnightCount: p.overnightCount + (t.arrMin >= 1440 ? 1 : 0),
          path: [...p.path, t],
        });
      }
      best.sort((a, b) => (better(a, b) ? -1 : better(b, a) ? 1 : 0));
      cur.push(best.slice(0, K));
    }
    prev = cur;
  }

  const all = prev.flat().sort((a, b) => (better(a, b) ? -1 : better(b, a) ? 1 : 0));
  const out = []; const seen = new Set();
  for (const p of all) {
    const k = p.path.map(t => t.code + t.date + t.dep).join('>');
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(p);
    if (out.length >= K) break;
  }

  return out.map(p => {
    // 同车次同日期连跑段合并
    const groups = [];
    for (const t of p.path) {
      const last = groups[groups.length - 1];
      if (last && last[0].code === t.code && last[0].date === t.date) last.push(t);
      else groups.push([t]);
    }
    const segs = groups.map(g => ({
      code: g[0].code, seat: g[0].seat,
      price: g.reduce((s, t) => s + t.price, 0),
      from: g[0].fromName, to: g[g.length - 1].toName,
      date: g[0].date, dep: g[0].dep, arr: g[g.length - 1].arr,
      dur: fmtMin(g[g.length - 1].absArr - g[0].absDep),
      canBuy: g.every(t => t.canBuy),
      via: g.length > 1 ? g.slice(1, -1).map(t => t.fromName) : [],
    }));
    const stays = [], risks = [];
    for (let i = 0; i < segs.length - 1; i++) {
      const gap = groups[i + 1][0].absDep - groups[i][groups[i].length - 1].absArr;
      stays.push(gap);
      const fromSt = groups[i][groups[i].length - 1].toName, toSt = groups[i + 1][0].fromName;
      if (fromSt !== toSt) {
        risks.push(gap < 360
          ? { level: 'warn', text: `${fromSt} 下车后要去 ${toSt} 上车（跨站换乘，需打车，已强制多留 ${CROSS_STATION_PENALTY} 分钟）` }
          : { level: 'info', text: `${fromSt} 和 ${toSt} 不是同一个站（跨站，间隔 ${fmtStay(gap)}，时间充裕可打车）` });
      } else if (gap < TIGHT_TRANSFER) {
        risks.push({ level: 'warn', text: `${fromSt} 换乘仅 ${Math.round(gap)} 分钟，前车一晚点就赶不上` });
      } else {
        risks.push(null);
      }
    }
    const hn = hotelNightsOf(p);
    return {
      cost: p.cost,
      totalCost: total(p),
      hotelNights: hn,
      depart: `${p.path[0].date.slice(5)} ${p.path[0].dep}`,
      arrive: `${p.path[p.path.length - 1].date.slice(5)} ${p.path[p.path.length - 1].arr}`,
      durMin: p.lastArr - p.firstDep,
      daysSpan: Math.floor((p.lastArr - p.firstDep) / 1440) + 1,
      transfers: segs.length - 1,
      stays, risks, segments: segs,
    };
  });
}

// ---------- 价格日历：按「出发那天」算每天最低票价 ----------
function buildCalendar(legs, stayMin, totalDays, dates) {
  const out = [];
  for (let d = 0; d < dates.length; d++) {
    const first = legs[0].filter(t => t.dateIndex === d);
    if (!first.length) { out.push({ date: dates[d], cost: null }); continue; }
    const plans = solvePlan([first, ...legs.slice(1)], stayMin, 'money', totalDays, 0, 1);
    out.push({ date: dates[d], cost: plans.length ? plans[0].cost : null });
  }
  return out;
}

// ---------- 自动推荐途经点 ----------
async function cheapLeg(from, to, date, seatPref, cap) {
  return getLegOptions(from, to, [date], seatPref, cap);
}
async function suggestRoutes(fromName, toName, dates, seatPref) {
  const date0 = dates[0];
  // 1. 拿直达车（不查价），挑代表车次取经停站
  const froms = matchStations(fromName), tos = matchStations(toName);
  const rows = [];
  for (const a of froms) for (const b of tos) {
    for (const r of await queryTickets(a.code, b.code, date0)) {
      const t = parseTrain(r);
      if (t) rows.push(t);
    }
  }
  if (!rows.length) return null;
  const byDur = [...rows].sort((a, b) => hmsToMin(a.dur) - hmsToMin(b.dur));
  const reps = byDur.slice(0, 2);
  for (const s of rows.filter(t => !/^[GDC]/.test(t.code)).sort((a, b) => hmsToMin(a.dur) - hmsToMin(b.dur)).slice(0, 2)) {
    if (!reps.find(r => r.code === s.code)) reps.push(s);
  }
  // 2. 汇总经停站（按线路位置排序）
  const posMap = new Map();
  for (const t of reps) {
    const stops = await queryTrainRoute(t.trainNo, t.fromCode, t.toCode, date0);
    if (!stops || stops.length < 3) continue;
    const maxNo = Number(stops[stops.length - 1].station_no) || stops.length;
    const fromStrip = stripDir(fromName), toStrip = stripDir(toName);
    for (const s of stops) {
      const name = s.station_name;
      if (stripDir(name) === fromStrip || stripDir(name) === toStrip) continue;
      const rec = posMap.get(name) || { count: 0, pos: 0 };
      rec.count++; rec.pos += Number(s.station_no) / maxNo;
      posMap.set(name, rec);
    }
  }
  let cands = [...posMap.entries()].map(([name, r]) => ({ name, count: r.count, pos: r.pos / r.count }))
    .sort((a, b) => b.count - a.count || Math.abs(0.5 - a.pos) - Math.abs(0.5 - b.pos))
    .slice(0, 6);
  if (!cands.length) return null;
  // 3. 评分：一跳中转成本
  for (const c of cands) {
    const A = await cheapLeg(fromName, c.name, date0, seatPref, 8);
    const B = await cheapLeg(c.name, toName, date0, seatPref, 8);
    if (!A.length || !B.length) { c.cost = Infinity; c.durMin = Infinity; continue; }
    const aMin = A.reduce((m, t) => (t.price < m.price ? t : m), A[0]);
    const bMin = B.reduce((m, t) => (t.price < m.price ? t : m), B[0]);
    c.cost = aMin.price + bMin.price;
    c.durMin = aMin.durMin + bMin.durMin;
    c.legInfo = {
      first: { price: aMin.price, durMin: aMin.durMin },   // from → c
      second: { price: bMin.price, durMin: bMin.durMin },  // c → to
    };
  }
  const ok = cands.filter(c => c.cost < Infinity).sort((a, b) => a.cost - b.cost);
  const options = ok.slice(0, 3).map(c => ({ vias: [c.name], cost: c.cost, durMin: c.durMin }));
  // 4. 两跳：单跳最优的前 3 个候选按线路顺序组合
  const top = ok.slice(0, 3).sort((a, b) => a.pos - b.pos);
  for (let i = 0; i < top.length; i++) {
    for (let j = i + 1; j < top.length; j++) {
      const M = await cheapLeg(top[i].name, top[j].name, date0, seatPref, 8);
      if (!M.length) continue;
      const mMin = M.reduce((m, t) => (t.price < m.price ? t : m), M[0]);
      options.push({
        vias: [top[i].name, top[j].name],
        cost: top[i].legInfo.first.price + mMin.price + top[j].legInfo.second.price,
        durMin: top[i].legInfo.first.durMin + mMin.durMin + top[j].legInfo.second.durMin,
      });
    }
  }
  options.sort((a, b) => a.cost - b.cost);
  // 5. 直达基线
  const direct = await cheapLeg(fromName, toName, date0, seatPref, 12);
  const directCost = direct.length ? direct.reduce((m, t) => Math.min(m, t.price), Infinity) : null;
  return { directCost: directCost === Infinity ? null : directCost, options: options.slice(0, 4) };
}

// ---------- 日期工具 ----------
function dateRange(startStr, endStr) {
  const out = [];
  const local = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const start = new Date(startStr + 'T00:00:00'), end = new Date(endStr + 'T00:00:00');
  const today = new Date(); today.setHours(0, 0, 0, 0);
  for (let d = new Date(start); d <= end && out.length < MAX_DAYS; d.setDate(d.getDate() + 1)) {
    if (d < today) continue;
    out.push(local(d)); // 不能用 toISOString：会按 UTC 错移一天
  }
  return out;
}

// ---------- HTTP ----------
function json(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    if (url.pathname === '/api/stations') { await loadStations(); return json(res, 200, { ok: true, total: stations.length }); }
    if (url.pathname === '/api/search') {
      await loadStations();
      const q = url.searchParams.get('q') || '';
      return json(res, 200, { ok: true, list: matchStations(q).slice(0, 8).map(s => ({ name: s.name, city: s.city })) });
    }
    if (url.pathname === '/api/plan' && req.method === 'POST') {
      let body = '';
      for await (const c of req) body += c;
      const q = JSON.parse(body || '{}');
      const from = (q.from || q.stops?.[0] || '').trim();
      const to = (q.to || q.stops?.[q.stops.length - 1] || '').trim();
      const via = (q.via || '').split(/[,，、\s]+/).map(s => s.trim()).filter(Boolean);
      const dateStart = q.dateStart || q.date;
      const dateEnd = q.dateEnd || q.date || dateStart;
      const stayMin = Math.max(0, parseInt((q.stayHours ?? 0) * 60, 10) || 0);
      const seatPref = q.seat || '二等座';
      const hotelPerNight = parseFloat(q.hotelPerNight) || 0;
      const focusDate = (q.focusDate || '').trim(); // 点价格日历：只限定出发日，后续段仍可跨天
      if (!from || !to) return json(res, 400, { ok: false, error: '需要出发站和终点站' });
      const dates = dateRange(dateStart, dateEnd);
      if (!dates.length) return json(res, 400, { ok: false, error: '日期区间无效（不能全在过去，且最长 15 天）' });

      await loadStations();

      // 自动推荐途经点（用户没填途经时）
      let suggest = null, routeUsed = [from, ...via, to];
      if (!via.length) {
        suggest = await suggestRoutes(from, to, dates, seatPref);
        if (suggest && suggest.options.length) {
          routeUsed = [from, ...suggest.options[0].vias, to];
        }
      }

      const priceCap = Math.max(12, Math.min(50, Math.floor(1500 / ((routeUsed.length - 1) * dates.length))));
      const legs = [];
      const legNames = [];
      for (let i = 0; i < routeUsed.length - 1; i++) {
        const opts = await getLegOptions(routeUsed[i], routeUsed[i + 1], dates, seatPref, priceCap);
        if (!opts.length) throw new Error(`【${routeUsed[i]} → ${routeUsed[i + 1]}】区间内没查到可购的直达车次（或价格拿不到），调整日期或途经点试试`);
        legs.push(opts);
        const dc = new Set(opts.map(o => o.date)).size;
        legNames.push(`${opts[0].fromName} → ${opts[0].toName}（${opts.length} 车次 / ${dc} 天有票）`);
      }

      const calendar = buildCalendar(legs, stayMin, dates.length, dates);

      // 指定出发日：第一段只留该天的车，其余段照常在区间内任意天
      let focusIdx = null;
      if (focusDate) {
        focusIdx = dates.indexOf(focusDate);
        if (focusIdx >= 0) legs[0] = legs[0].filter(t => t.dateIndex === focusIdx);
      }
      const modes = {
        money: solvePlan(legs, stayMin, 'money', dates.length, hotelPerNight).map(p => ({
          ...p, durText: fmtMin(p.durMin), stayTexts: p.stays.map(fmtStay),
        })),
      };

      return json(res, 200, { ok: true, legs: legNames, dates, seatPref, stayMin, hotelPerNight, modes, calendar, suggest, routeUsed, focusDate: focusIdx >= 0 ? focusDate : null });
    }
    if (url.pathname === '/' || url.pathname === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(fs.readFileSync(path.join(__dirname, 'index.html')));
    }
    res.writeHead(404); res.end('not found');
  } catch (e) {
    console.error(e);
    json(res, 500, { ok: false, error: e.message || '服务器出错了' });
  }
});

const HOST = process.env.HOST || '0.0.0.0';
server.listen(PORT, HOST, () => console.log(`🚄 拼票规划器 v4 已启动: http://${HOST === '0.0.0.0' ? 'localhost' : HOST}:${PORT}`));
