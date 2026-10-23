const C='clubcount-20261024-v5';
const META='cc-meta';   // seen/notified events, written by the page; survives app updates
const CORE=['./','index.html','klubi.html','venues.js','events.js','manifest.webmanifest','icon-192.png','icon-512.png','apple-touch-icon.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!==META).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET')return;
  const u=new URL(r.url);
  if(u.origin===location.origin){
    e.respondWith(fetch(r).then(res=>{const cp=res.clone();caches.open(C).then(c=>c.put(r,cp));return res}).catch(()=>caches.match(r).then(m=>m||caches.match('index.html'))));
  }else if(/(fonts\.(googleapis|gstatic)\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|storage\.googleapis\.com|tfhub\.dev|kaggle\.com|upload\.wikimedia\.org)$/.test(u.hostname)){
    // fonts, Leaflet, TensorFlow.js and the AI model: cache after first load so they work offline
    e.respondWith(caches.match(r).then(m=>m||fetch(r).then(res=>{const cp=res.clone();caches.open(C).then(c=>c.put(r,cp));return res})));
  }
});

/* new D3 / Club Studio events while the app is closed (Android, installed app, periodic background sync) */
const TOP_NAMES={'club-studio':'Club Studio','d3':'D3'};
async function checkEvents(){
  const meta=await caches.open(META),r=await meta.match('cc-seen');if(!r)return;
  const seen=await r.json();if(!seen.notify)return;
  const txt=await fetch('events.js',{cache:'no-store'}).then(x=>x.text());
  const evs=[...txt.matchAll(/"id":"([^"]+)","date":"([^"]+)","time":"[^"]*","title":"((?:[^"\\]|\\.)*)","venue":"(club-studio|d3)"/g)].map(m=>({id:m[1],date:m[2],title:m[3],venue:m[4]}));
  const d=new Date(),today=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  const done=new Set((seen.ids||[]).concat(seen.notified||[]));
  const fresh=evs.filter(x=>x.date>=today&&!done.has(x.id));if(!fresh.length)return;
  const e=fresh[0];
  await self.registration.showNotification('Clubcount',{body:TOP_NAMES[e.venue]+' lisas uue ürituse: '+e.title+(fresh.length>1?' (+'+(fresh.length-1)+' veel)':''),icon:'icon-192.png',tag:'cc-new-events',data:{url:'./#e-'+e.id}});
  seen.notified=(seen.notified||[]).concat(fresh.map(x=>x.id)).slice(-200);
  await meta.put('cc-seen',new Response(JSON.stringify(seen)));
}
self.addEventListener('periodicsync',e=>{if(e.tag==='cc-events')e.waitUntil(checkEvents())});
self.addEventListener('notificationclick',e=>{
  e.notification.close();const url=(e.notification.data&&e.notification.data.url)||'./';
  e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>{
    for(const w of ws)if('focus' in w){w.navigate(url);return w.focus()}
    return clients.openWindow(url);
  }));
});
