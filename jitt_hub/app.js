/*
const DEMO_USER={email:'admin@admin.hu',password:'admin123',name:'Kovács Ádám',role:'Admin'};
const AUTH_KEY='jitt_hub_demo_session';
function storedSession(){return sessionStorage.getItem(AUTH_KEY)||localStorage.getItem(AUTH_KEY)}
function setAuthenticated(remember=false){const payload=JSON.stringify({email:DEMO_USER.email,name:DEMO_USER.name,role:DEMO_USER.role,loggedInAt:new Date().toISOString()});(remember?localStorage:sessionStorage).setItem(AUTH_KEY,payload);if(!remember)localStorage.removeItem(AUTH_KEY)}
function clearAuthentication(){sessionStorage.removeItem(AUTH_KEY);localStorage.removeItem(AUTH_KEY)}
function showApplication(){document.querySelector('#loginScreen').hidden=true;document.querySelector('#appShell').hidden=false;document.body.classList.add('is-authenticated')}
function showLogin(){document.querySelector('#appShell').hidden=true;document.querySelector('#loginScreen').hidden=false;document.body.classList.remove('is-authenticated');setTimeout(()=>document.querySelector('#loginEmail')?.focus(),0)}
function initializeAuthentication(){
  const form=document.querySelector('#loginForm'),email=document.querySelector('#loginEmail'),password=document.querySelector('#loginPassword'),error=document.querySelector('#loginError'),remember=document.querySelector('#rememberMe');
  document.querySelector('#passwordToggle').addEventListener('click',()=>{password.type=password.type==='password'?'text':'password'});
  document.querySelector('#forgotPassword').addEventListener('click',()=>{error.textContent='A demóban nincs jelszó-visszaállítás. Használd a teszt hozzáférést.'});
  form.addEventListener('submit',e=>{e.preventDefault();error.textContent='';const submit=form.querySelector('.login-submit');submit.disabled=true;submit.firstElementChild.textContent='Ellenőrzés…';setTimeout(()=>{const ok=email.value.trim().toLowerCase()===DEMO_USER.email&&password.value===DEMO_USER.password;if(ok){setAuthenticated(remember.checked);showApplication();toast(`Üdv újra, ${DEMO_USER.name}!`)}else{error.textContent='Hibás felhasználónév vagy jelszó.';form.classList.remove('shake');void form.offsetWidth;form.classList.add('shake');password.select()}submit.disabled=false;submit.firstElementChild.textContent='Bejelentkezés'},450)});
  document.querySelector('#logoutButton').addEventListener('click',()=>{clearAuthentication();showLogin();password.value='';error.textContent='Sikeresen kijelentkeztél.'});
  if(storedSession())showApplication();else showLogin();
}

const menu = [
  ['dashboard','⌂','Dashboard'],['shifts','▣','Műszakok'],['couriers','♧','Futárok'],['orders','▤','Rendelések'],['settlements','▧','Elszámolások'],['finance','▱','Pénzügy'],['imports','⇩','Importok'],['documents','▥','Dokumentumok'],['discord','☁','Discord'],['vehicles','▰','Járművek'],['reports','⌁','Riportok & BI'],['settings','⚙','Beállítások'],['audit','□','Audit napló']
];
const state={page:'dashboard',branch:'ALL',theme:localStorage.getItem('theme')||'light'};
const $=s=>document.querySelector(s), money=n=>new Intl.NumberFormat('hu-HU').format(n)+' Ft';

document.documentElement.dataset.theme=state.theme==='dark'?'dark':'';
$('#mainNav').innerHTML=menu.map(([id,icon,label])=>`<button class="nav-item ${id==='dashboard'?'active':''}" data-page="${id}"><span class="nav-icon">${icon}</span><span class="nav-label">${label}</span></button>`).join('');
$('#mainNav').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(!b)return;state.page=b.dataset.page;document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x===b));render();$('#sidebar').classList.remove('open')});
$('#branchTabs').addEventListener('click',e=>{const b=e.target.closest('[data-branch]');if(!b)return;state.branch=b.dataset.branch;document.querySelectorAll('[data-branch]').forEach(x=>x.classList.toggle('active',x===b));toast(`${b.textContent} nézet betöltve`);render()});
$('#themeToggle').onclick=()=>{state.theme=state.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=state.theme==='dark'?'dark':'';localStorage.setItem('theme',state.theme)};
$('#menuToggle').onclick=()=>$('#sidebar').classList.toggle('open');
function toast(msg){const t=$('#toast');t.textContent=msg;t.style.cssText='position:fixed;right:20px;bottom:20px;background:#111;color:#fff;padding:12px 16px;border-radius:10px;z-index:99;opacity:1';setTimeout(()=>t.style.opacity=0,1800)}
function setHead(title,sub){$('#pageTitle').textContent=title;$('#pageSubtitle').textContent=sub}
const badge=(text,type='gray')=>`<span class="badge ${type}">${text}</span>`;
const person=(name)=>`<div class="person"><span class="person-avatar">${name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><span>${name}</span></div>`;
const table=(heads,rows)=>`<div class="table-wrap"><table class="table"><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
function lineChart(vals=[35,48,30,58,45,67,76]){const pts=vals.map((v,i)=>`${i*(100/(vals.length-1))},${100-v}`).join(' ');return `<div class="chart line-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none"><polyline fill="none" stroke="var(--green)" stroke-width="2.5" points="${pts}"/><polyline fill="color-mix(in srgb,var(--green) 13%, transparent)" stroke="none" points="0,100 ${pts} 100,100"/></svg></div>`}
function bars(vals=[35,60,42,72,54,86,67,80,65,90]){return `<div class="chart"><div class="bars">${vals.map(v=>`<span style="height:${v}%"></span>`).join('')}</div></div>`}
function warehouse(name,a,s,r,m){return `<div class="card warehouse"><div class="warehouse-title"><strong>⌂ ${name}</strong><small class="muted">Frissítve: 09:32:15 ↻</small></div><div class="warehouse-stats"><div class="warehouse-stat"><span>Aktív futárok</span><b>${a}</b><small class="good">Online: ${a-5}</small></div><div class="warehouse-stat"><span>Műszakok ma</span><b>${s}</b><small class="good">Befejezve: ${Math.floor(s/2)}</small></div><div class="warehouse-stat"><span>Útvonal kockázatok</span><b class="warn">${r}</b><small class="warn">Magas: ${Math.max(1,r-3)}</small></div><div class="warehouse-stat"><span>Hiányzó sorok</span><b class="bad">${m}</b><small class="bad">Új: ${Math.min(2,m)}</small></div></div></div>`}
function quick(title,icon,rows,action='Megnyitás'){return `<div class="card quick-card"><div class="split"><div class="quick-icon">${icon}</div>${badge(rows[0][1],rows[0][2]||'green')}</div><h3>${title}</h3><div class="rows">${rows.slice(1).map(x=>`<div class="row"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('')}</div><button class="btn secondary" onclick="toast('${title}')">${action}</button></div>`}
function dashboard(){setHead('Operations Dashboard','Valós idejű áttekintés az összes raktárról');return `<div class="grid layout-main"><div class="grid"><div class="grid grid-2">${warehouse('BUD1',32,18,5,3)}${warehouse('BUD2',28,16,3,1)}</div><div class="grid grid-6">${quick('Műszak ellenőrzés','✓',[['9','red'],['Késésben lévő','6'],['Ütközések','2'],['Hiányzók','1']])}${quick('Műszak mentés','⇩',[['2','green'],['Mentésre vár','2'],['Sikertelen','0'],['Utolsó mentés','09:31']],'Mentés most')}${quick('Futár pénzügy','▱',[['7','orange'],['Elszámolásra vár','7'],['Jóváhagyásra vár','3'],['Hibás tétel','1']])}${quick('Discord értesítések','☁',[['1','gray'],['Küldésre vár','1'],['Sikertelen','0'],['Utolsó küldés','09:30']])}${quick('Dokumentumok','▥',[['3','gray'],['Lejárt','1'],['Lejár 7 napon belül','2'],['Összes dokumentum','128']])}${quick('Mai futárok','♧',[['60','gray'],['Összes futár','60'],['Aktív','55'],['Inaktív / szünet','5']])}</div><div class="grid grid-4"><div class="card"><h3>Rendelések áttekintés</h3><div class="split"><div><div class="value"><b>1 651</b></div><small>Utolsó 7 nap</small></div><span class="trend up">+12.5%</span></div>${lineChart()}</div><div class="card"><h3>Teljesített körök</h3><div class="split"><div><b style="font-size:25px">342</b><small class="muted"> teljesített kör</small></div><span class="trend up">+8.3%</span></div>${lineChart([50,64,45,61,49,70,66])}</div><div class="card"><h3>Kifizetések összesen</h3><div class="split"><b style="font-size:25px">12 850 000 Ft</b><span class="trend up">+15.7%</span></div>${bars()}</div><div class="card"><h3>Futár aktivitás</h3><div class="split"><div class="donut"></div><div class="metric-list"><div>Aktív <b>55</b></div><div>Szünet <b>5</b></div><div>Inaktív <b>3</b></div></div></div></div></div><div class="grid grid-2"><div class="card"><div class="card-head"><h3>Következő műszakok – áttekintés</h3><button class="btn ghost">Szűrők</button></div>${shiftsTable()}</div><div class="card"><div class="card-head"><h3>Térkép – aktív futárok</h3>${badge('BUD1','green')}</div>${mapBlock()}</div></div></div><aside><div class="card"><h3>♧ Élő figyelmeztetések</h3>${alertBlock()}</div><div class="card" style="margin-top:14px"><h3>Javasolt cserék</h3>${[['BUD1 – 09:30','2 javaslat'],['BUD1 – 10:00','1 javaslat'],['BUD2 – 09:45','1 javaslat']].map(x=>`<div class="metric-row"><span>${x[0]}</span><a>${x[1]}</a></div>`).join('')}</div><div class="card" style="margin-top:14px"><h3>Szinkron állapot</h3>${['MuszakPro','Jitt rendszer','Discord','Dokumentumok'].map(x=>`<div class="metric-row"><span>${x}</span><span class="trend up">● OK</span></div>`).join('')}</div></aside></div>`}
function shiftsTable(){return table(['Raktár','Futár','Következő műszak','Késés','Ajánlott csere','Státusz'],[['BUD1',person('Kovács Ádám'),'09:00–13:00','25 p','Szabó Bence',badge('Késésben','red')],['BUD1',person('Tóth Márk'),'09:15–13:15','18 p','Varga Péter',badge('Késésben','orange')],['BUD1',person('Szabó Linda'),'09:30–13:30','–','–',badge('Időben','green')],['BUD2',person('Nagy Boglárka'),'09:30–13:30','15 p','Kiss László',badge('Késésben','orange')],['BUD2',person('Horváth Dániel'),'09:45–13:45','–','–',badge('Időben','green')]])}
function mapBlock(){return `<div class="map"><span class="pin" style="left:24%;top:35%"></span><span class="pin orange" style="left:62%;top:24%"></span><span class="pin" style="left:49%;top:58%"></span><span class="pin red" style="left:74%;top:68%"></span><span class="pin" style="left:30%;top:75%"></span></div><div class="split" style="margin-top:10px"><small>● Aktív</small><small>● Szünet</small><small>● Inaktív</small></div>`}
function alertBlock(){return `<div class="alert warning"><div class="split"><strong>Következő műszak késésben</strong>${badge('6','red')}</div><p><b>BUD1 – Kovács Ádám</b><br><small>09:00 helyett 09:25</small></p><p><b>BUD1 – Tóth Márk</b><br><small>09:15 helyett 09:33</small></p></div><div class="alert"><div class="split"><strong>Dokumentum lejár</strong>${badge('3','orange')}</div><p><small>3 futár dokumentuma 7 napon belül lejár.</small></p></div>`}
function pageHeader(title,desc,actions=''){return `<div class="card"><div class="card-head"><div><h3>${title}</h3><p class="muted">${desc}</p></div><div class="toolbar">${actions}</div></div></div>`}
function genericKpis(items){return `<div class="grid grid-4">${items.map(([t,v,s,c])=>`<div class="card kpi"><span class="muted">${t}</span><span class="value">${v}</span><span class="trend ${c||'up'}">${s}</span></div>`).join('')}</div>`}
function shifts(){setHead('Műszakok','Tervezés, ellenőrzés és cserejavaslatok');return `${pageHeader('Műszakkezelő','Élő státuszok, ütközések és módosítások','<button class="btn">+ Új műszak</button><button class="btn ghost">Export</button>')}${genericKpis([['Mai műszakok','34','+4 tegnaphoz képest'],['Késésben','6','Azonnali figyelem','down'],['Cserejavaslat','4','2 kritikus','down'],['Lefedettség','94%','Cél: 96%']])}<div class="card" style="margin-top:14px"><div class="tabs"><button class="tab active">Mai nap</button><button class="tab">Heti nézet</button><button class="tab">Ütközések</button><button class="tab">Cserék</button></div>${shiftsTable()}</div>`}
function couriers(){setHead('Futárok','Futárprofilok, teljesítmény és megfelelőség');const rows=['Kovács Ádám','Tóth Márk','Szabó Linda','Nagy Boglárka','Horváth Dániel','Mészáros Kevin'].map((n,i)=>[person(n),i<3?'BUD1':'BUD2',badge(i===5?'Szünet':'Aktív',i===5?'gray':'green'),`${86+i*2}%`,money(185000+i*17500),badge(i===3?'Lejár hamar':'Rendben',i===3?'orange':'green')]);return `${pageHeader('Futártörzs','Keresés, szűrés és profilkezelés','<input class="input" placeholder="Keresés név alapján"><button class="btn">+ Új futár</button>')}${genericKpis([['Összes futár','63','+3 ebben a hónapban'],['Aktív','55','87% aktivitás'],['Szünet / inaktív','8','-1 a múlt héthez képest'],['Hiányzó dokumentum','4','Ellenőrzést igényel','down']])}<div class="card" style="margin-top:14px">${table(['Futár','Raktár','Státusz','Pontosság','Aktuális kifizetés','Dokumentum'],rows)}</div>`}
function orders(){setHead('Rendelések','Rendelésfolyam, hibák és teljesítési SLA');const rows=Array.from({length:8},(_,i)=>[`#JH-${8021+i}`,i%2?'BUD2':'BUD1',person(['Kovács Ádám','Szabó Linda','Tóth Márk'][i%3]),`${9+i}:2${i}`,money(3200+i*240),badge(i===3?'Késik':i===6?'Törölve':'Teljesítve',i===3?'orange':i===6?'red':'green')]);return `${pageHeader('Rendelésközpont','Valós idejű rendelésfigyelés','<input class="input" placeholder="Rendelésszám"><select class="select"><option>Minden státusz</option><option>Teljesítve</option><option>Késik</option></select>')}${genericKpis([['Mai rendelések','286','+9.8% tegnaphoz képest'],['SLA teljesítés','96.4%','Cél felett'],['Átlagos idő','31 perc','-3 perc javulás'],['Hibás rendelés','7','2.4%','down']])}<div class="grid grid-3" style="margin-top:14px"><div class="card"><h3>Óránkénti volumen</h3>${bars([20,32,42,65,88,70,55,80,92,67])}</div><div class="card"><h3>SLA trend</h3>${lineChart([66,68,73,75,78,82,86])}</div><div class="card"><h3>Hibatípusok</h3><div class="metric-list"><div class="metric-row"><span>Késés</span><b>4</b></div><div class="metric-row"><span>Hiányzó tétel</span><b>2</b></div><div class="metric-row"><span>Címhiba</span><b>1</b></div></div></div></div><div class="card" style="margin-top:14px">${table(['Rendelés','Raktár','Futár','Idő','Érték','Státusz'],rows)}</div>`}
function settlements(){setHead('Elszámolások','Futárkifizetések, bónuszok és levonások');const rows=['Kovács Ádám','Tóth Márk','Szabó Linda','Nagy Boglárka','Horváth Dániel'].map((n,i)=>[person(n),`${42+i*5}`,money(168000+i*21000),money(12000+i*1500),money(i*2200),money(178000+i*20400),badge(i===1?'Jóváhagyásra vár':'Kész',i===1?'orange':'green')]);return `${pageHeader('Elszámolási központ','Időszaki kifizetések áttekintése','<select class="select"><option>2026. július</option></select><button class="btn">Új elszámolás</button>')}${genericKpis([['Fizetendő összesen','12.85 M Ft','+15.7% előző hónap'],['Feldolgozásra vár','7','3 prioritásos','down'],['Jóváhagyásra vár','3','Átlag 1.2 nap','down'],['Hibás tétel','1','Manuális ellenőrzés','down']])}<div class="card" style="margin-top:14px">${table(['Futár','Körök','Alapdíj','Bónusz','Levonás','Fizetendő','Státusz'],rows)}</div>`}
function finance(){setHead('Pénzügy','Cashflow, költségek és kifizetések');return `${pageHeader('Pénzügyi áttekintés','Összesített pénzügyi teljesítmény','<button class="btn ghost">CSV export</button><button class="btn">Riport készítése</button>')}${genericKpis([['Mai bevétel','2.45 M Ft','+18.6% tegnaphoz képest'],['Havi kifizetés','12.85 M Ft','+15.7% előző hónap'],['Működési költség','4.32 M Ft','-2.4% tervhez képest'],['Bruttó marzs','31.8%','+1.9 pp']])}<div class="grid grid-2" style="margin-top:14px"><div class="card"><h3>Bevétel trend</h3>${lineChart([35,45,62,54,71,68,80,76,92,88])}</div><div class="card"><h3>Költségmegoszlás</h3><div class="metric-list"><div><div class="split"><span>Futárkifizetés</span><b>61%</b></div><div class="progress"><span style="width:61%"></span></div></div><div><div class="split"><span>Operáció</span><b>22%</b></div><div class="progress"><span style="width:22%"></span></div></div><div><div class="split"><span>Jármű és eszköz</span><b>11%</b></div><div class="progress"><span style="width:11%"></span></div></div><div><div class="split"><span>Egyéb</span><b>6%</b></div><div class="progress"><span style="width:6%"></span></div></div></div></div></div>`}
function imports(){setHead('Importok','Adatbetöltés, validáció és előnézet');return `${pageHeader('Import Center','Excel és CSV állományok feldolgozása','<button class="btn">Fájl feltöltése</button>')}${genericKpis([['Mai import','8','7 sikeres'],['Feldolgozás alatt','1','64% kész'],['Hibás sor','12','3 fájlban','down'],['Utolsó sikeres','09:31','MűszakPro export']])}<div class="grid grid-2" style="margin-top:14px"><div class="card"><h3>Új import</h3><div class="empty"><div style="font-size:40px">⇧</div><p>Húzd ide az Excel vagy CSV fájlt</p><button class="btn">Tallózás</button></div></div><div class="card"><h3>Validációs összegzés</h3><div class="metric-list"><div class="metric-row"><span>Érvényes sorok</span><b>1 842</b></div><div class="metric-row"><span>Duplikációk</span><b>4</b></div><div class="metric-row"><span>Hiányzó futár</span><b>6</b></div><div class="metric-row"><span>Formátumhiba</span><b>2</b></div></div></div></div>`}
function documents(){setHead('Dokumentumok','Szerződések, igazolások és lejáratok');const rows=['Kovács Ádám','Tóth Márk','Szabó Linda','Nagy Boglárka','Horváth Dániel'].map((n,i)=>[person(n),['Szerződés','Jogosítvány','Adóigazolás'][i%3],`2026.0${8+i}.1${i}`,badge(i===1?'Lejár hamar':'Érvényes',i===1?'orange':'green'),'<button class="btn ghost">Megnyitás</button>']);return `${pageHeader('Dokumentumtár','Központi dokumentumkezelés','<input class="input" placeholder="Keresés"><button class="btn">+ Feltöltés</button>')}${genericKpis([['Összes dokumentum','128','+6 ebben a hónapban'],['Lejár 30 napon belül','8','4 prioritásos','down'],['Lejárt','1','Azonnali intézkedés','down'],['Hiányzó','3','Profilok blokkolva','down']])}<div class="card" style="margin-top:14px">${table(['Futár','Dokumentum','Lejárat','Státusz','Művelet'],rows)}</div>`}
function discord(){setHead('Discord','Értesítések, sablonok és kézbesítési állapot');return `${pageHeader('Discord központ','Automatikus és manuális értesítések','<button class="btn">Új üzenet</button>')}${genericKpis([['Mai üzenetek','46','98% kézbesítve'],['Küldésre vár','1','09:35-re ütemezve'],['Sikertelen','0','Minden rendben'],['Aktív sablon','12','3 automatikus']])}<div class="grid grid-2" style="margin-top:14px"><div class="card"><h3>Üzenetküldés</h3><select class="select" style="width:100%;margin-bottom:10px"><option>#budapest-operations</option><option>#courier-alerts</option></select><textarea class="input" style="width:100%;height:150px" placeholder="Üzenet..."></textarea><button class="btn" style="margin-top:10px">Küldés</button></div><div class="card"><h3>Legutóbbi aktivitás</h3><div class="activity-feed">${['Műszakkezdés emlékeztető elküldve','Elszámolás elkészült értesítés','Dokumentum lejárati figyelmeztetés','Késési riasztás'].map((x,i)=>`<div class="activity-item"><span class="feed-dot"></span><div><b>${x}</b><small><br>${9+i}:3${i}</small></div>${badge(i===3?'Riasztás':'Kézbesítve',i===3?'orange':'green')}</div>`).join('')}</div></div></div>`}
function vehicles(){setHead('Járművek','Flottaállapot, szerviz és biztosítás');const rows=['JH-101','JH-104','JH-112','JH-118','JH-123'].map((id,i)=>[id,['Toyota Yaris','Dacia Sandero','Renault Clio'][i%3],i%2?'BUD2':'BUD1',badge(i===2?'Szerviz':'Aktív',i===2?'orange':'green'),`${62400+i*8300} km`,`2026.0${8+i}.2${i}`]);return `${pageHeader('Flottakezelés','Járművek és karbantartási feladatok','<button class="btn">+ Jármű</button>')}${genericKpis([['Összes jármű','27','24 aktív'],['Szervizben','2','1 sürgős','down'],['Biztosítás lejár','3','30 napon belül','down'],['Átlag kihasználtság','78%','+4 pp']])}<div class="card" style="margin-top:14px">${table(['Azonosító','Típus','Raktár','Státusz','Kilométer','Következő szerviz'],rows)}</div>`}
function reports(){setHead('Riportok & BI','Operációs és pénzügyi elemzések');return `${pageHeader('Business Intelligence','Interaktív riportok és trendek','<select class="select"><option>Utolsó 30 nap</option></select><button class="btn">Dashboard mentése</button>')}${genericKpis([['Rendelés növekedés','+12.5%','stabil trend'],['Kifizetés / rendelés','4 612 Ft','-3.2% javulás'],['Futár megtartás','93.1%','+1.8 pp'],['SLA','96.4%','cél felett']])}<div class="grid grid-3" style="margin-top:14px"><div class="card"><h3>Rendelés trend</h3>${lineChart([32,38,44,41,55,61,66,72])}</div><div class="card"><h3>Kifizetési trend</h3>${bars([45,38,52,60,48,69,74,82])}</div><div class="card"><h3>Raktári megoszlás</h3><div class="split"><div class="donut"></div><div><p><b>BUD1</b> 54%</p><p><b>BUD2</b> 46%</p></div></div></div></div><div class="card" style="margin-top:14px"><h3>Top teljesítményű futárok</h3>${table(['Futár','Raktár','Rendelés','Pontosság','Értékelés'],[[person('Szabó Linda'),'BUD1','184','98.7%','4.96'],[person('Kovács Ádám'),'BUD1','176','97.9%','4.91'],[person('Nagy Boglárka'),'BUD2','169','97.4%','4.88']])}</div>`}
function settings(){setHead('Beállítások','Rendszer, jogosultságok és integrációk');return `${pageHeader('Rendszerbeállítások','Konfigurációs központ','<button class="btn">Módosítások mentése</button>')}<div class="grid grid-2" style="margin-top:14px"><div class="card"><h3>Általános</h3><label>Alapértelmezett raktár<select class="select" style="width:100%;margin:6px 0 14px"><option>Összes</option><option>BUD1</option><option>BUD2</option></select></label><label>Automatikus frissítés<select class="select" style="width:100%;margin-top:6px"><option>30 másodperc</option><option>1 perc</option></select></label></div><div class="card"><h3>Integrációk</h3>${['Supabase','MűszakPro','Discord','Google Drive'].map(x=>`<div class="metric-row"><span>${x}</span>${badge('Kapcsolódva','green')}</div>`).join('')}</div><div class="card"><h3>Jogosultságok</h3>${['Admin','Operációs vezető','Pénzügy','Megtekintő'].map((x,i)=>`<div class="metric-row"><span>${x}</span><button class="btn ghost">${8-i*2} felhasználó</button></div>`).join('')}</div><div class="card"><h3>Értesítések</h3>${['Késési riasztások','Dokumentum lejárat','Sikertelen import','Szinkronhiba'].map(x=>`<div class="metric-row"><span>${x}</span><input type="checkbox" checked></div>`).join('')}</div></div>`}
function audit(){setHead('Audit napló','Felhasználói és rendszeresemények');const rows=[['09:32','Kovács Ádám','Elszámolás jóváhagyva','#SET-2407',badge('Sikeres','green')],['09:31','Rendszer','MűszakPro import','1 842 sor',badge('Sikeres','green')],['09:28','Nagy Anna','Futárprofil módosítva','Tóth Márk',badge('Módosítás','blue')],['09:24','Rendszer','Discord riasztás','Késési esemény',badge('Figyelmeztetés','orange')],['09:18','Kiss Péter','Dokumentum törölve','doc_118.pdf',badge('Törlés','red')]];return `${pageHeader('Audit események','Teljes változás- és hozzáférési napló','<input class="input" placeholder="Keresés"><button class="btn ghost">Export</button>')}${genericKpis([['Mai esemény','214','+11% átlaghoz képest'],['Felhasználói művelet','86','40%'],['Automatikus esemény','128','60%'],['Kritikus esemény','1','Ellenőrzést igényel','down']])}<div class="card" style="margin-top:14px">${table(['Idő','Felhasználó','Esemény','Részlet','Státusz'],rows)}</div>`}
const pages={dashboard,shifts,couriers,orders,settlements,finance,imports,documents,discord,vehicles,reports,settings,audit};
function render(){const fn=pages[state.page]||dashboard;$('#pageContent').innerHTML=fn()}
render();
initializeAuthentication();
*/

const DEMO_USER = {
  email: "admin@admin.hu",
  password: "admin123",
  name: "Gurzó Balázs",
  role: "Admin"
};

const links = {
  pwa: "https://giriton-courier-pwa.onrender.com",
  devtest: "https://devtest.streamlit.app/",
  github: "https://github.com/jitthungarydsp/giriton-dashboard",
  hub: "https://jitthub.jitthub.workers.dev/"
};

const pages = [
  { id: "vehicles", label: "Járművek", icon: "▣" }
];

const modules = [
  { id: "pwa", title: "Futár PWA", group: "Éles", status: "online", metric: "73 aktív futár", text: "Elszámolás, TIG, útvonalak, reklamációk.", link: links.pwa },
  { id: "settlement", title: "Elszámolás", group: "Éles", status: "figyelni", metric: "7 ellenőrzés", text: "JITT, Kiflis, korrekció, TIG végösszeg.", link: links.devtest },
  { id: "bonusReport", title: "Excel kimutatás", group: "Új", status: "terv", metric: "Delay + compliance", text: "Futár, Excel túrák, bónuszok és PWA/mart műszakadatok.", link: "#" },
  { id: "shifts", title: "Műszak minőség", group: "Következő", status: "terv", metric: "DB készül", text: "Show, no-show, késés, műszak compliance.", link: "#" },
  { id: "robots", title: "Robot futtatások", group: "Automata", status: "online", metric: "4 napi job", text: "DSP, bónusz/malus, booking log, járművek.", link: "#" },
  { id: "discord", title: "Discord üzenetek", group: "Beköthető", status: "terv", metric: "12 sablon", text: "Bónusz, műszak, dokumentum értesítések.", link: "#" },
  { id: "documents", title: "Dokumentumtár", group: "Beköthető", status: "terv", metric: "TIG + számla", text: "Feltöltések, számlák, TIG, audit.", link: "#" },
  { id: "fleet", title: "Járművek", group: "Beköthető", status: "terv", metric: "Sheet sync", text: "Ki milyen autóval fut ma és holnap.", link: "#" },
  { id: "bi", title: "Riportok", group: "Beköthető", status: "terv", metric: "Napi + havi", text: "Kifizetés, teljesítmény, vállalkozói díj.", link: "#" }
];

const tasks = [
  ["Mobil snapshot frissítés", "PWA pénzügyi bontás ellenőrzése", "Ma"],
  ["TIG ellenőrzés", "KP sor és határidő egységesítve", "Kész"],
  ["Előleg folyamat", "Ne írja felül a havi státuszt", "Kész"],
  ["Jármű sheet", "Napi sync job előkészítése", "Következő"],
  ["Discord bónusz értesítés", "Sablonok és küldés", "Terv"]
];

const fallbackReport = {
  month: "2026-07",
  source: "fallback",
  totals: { orders: 766, routes: 64, delayBonus: 192000, complianceBonus: 64000 },
  couriers: [
    {
      courierId: "demo-a",
      name: "Futár A",
      warehouse: "BUD2",
      orders: 603,
      routes: 46,
      delayBonus: 138000,
      complianceBonus: 46000,
      shifts: [
        {
          workDate: "2026-07-03",
          shiftName: "BUD2-10:00",
          checkedInAt: "2026-07-03T09:54:00",
          availableAt: "2026-07-03T09:54:00",
          noShow: false,
          routes: [
            {
              routeId: "demo-01",
              routeType: "normal",
              assignedAt: "2026-07-03T10:10:00",
              routeDurationMinutes: 150,
              addressCount: 13,
              plannedReturnAt: "2026-07-03T12:40:00",
              realReturnAt: "2026-07-03T12:35:00",
              timeWindowLateCount: 0,
              timeWindowLateTotalMinutes: 0
            }
          ]
        }
      ]
    }
  ]
};

const state = {
  page: "vehicles",
  theme: localStorage.getItem("jittHubTheme") || "light",
  reportMonth: "2026-07",
  reportCourierId: "",
  reportToken: sessionStorage.getItem("jittHubReportToken") || "",
  vehicleDate: new Date().toISOString().slice(0, 10),
  vehicleWarehouse: "all",
  vehicleStatus: "all",
  vehicleSearch: ""
};

const reportState = {
  loading: false,
  loadedMonth: "",
  data: null,
  error: ""
};

const vehicleState = {
  loading: false,
  loadedDate: "",
  data: null,
  error: ""
};

const vehicleSaveState = {
  saving: false,
  message: "",
  error: ""
};

const $ = (selector) => document.querySelector(selector);
const formatMoney = (value) => new Intl.NumberFormat("hu-HU").format(value) + " Ft";

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("hu-HU", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatMinutes(value) {
  const minutes = toNumber(value);
  if (!minutes) return "-";
  return `${Math.round(minutes)} perc`;
}

function formatLate(route) {
  const count = toNumber(route.timeWindowLateCount);
  const total = toNumber(route.timeWindowLateTotalMinutes);
  if (!count && !total) return "Nincs";
  if (count && total) return `${count} cím / ${Math.round(total)} perc`;
  if (count) return `${count} cím`;
  return `${Math.round(total)} perc`;
}

function currentReport() {
  return reportState.data || fallbackReport;
}

function reportCouriers() {
  const data = currentReport();
  return Array.isArray(data.couriers) ? data.couriers : [];
}

function selectReportCourier() {
  const couriers = reportCouriers();
  if (!couriers.length) return null;
  return couriers.find((courier) => String(courier.courierId) === String(state.reportCourierId)) || couriers[0];
}

function ensureReportLoaded() {
  if (reportState.loading || reportState.loadedMonth === state.reportMonth) return;
  window.setTimeout(loadReport, 0);
}

async function loadReport() {
  if (reportState.loading) return;
  reportState.loading = true;
  reportState.error = "";
  render();

  try {
    const response = await fetch(`/api/route-quality?month=${encodeURIComponent(state.reportMonth)}`, {
      headers: {
        Accept: "application/json",
        ...(state.reportToken ? { "x-hub-report-token": state.reportToken } : {})
      }
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    const data = await response.json();
    reportState.data = data;
    reportState.loadedMonth = state.reportMonth;
    if (!data.couriers?.some((courier) => String(courier.courierId) === String(state.reportCourierId))) {
      state.reportCourierId = data.couriers?.[0]?.courierId ? String(data.couriers[0].courierId) : "";
    }
  } catch (error) {
    reportState.error = error.message || "A riport API nem elérhető.";
    reportState.data = null;
    reportState.loadedMonth = state.reportMonth;
  } finally {
    reportState.loading = false;
    render();
  }
}

function setTheme() {
  document.documentElement.dataset.theme = state.theme;
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 1800);
}

function openTarget(id) {
  const url = links[id];
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  toast("Ez a modul még bekötésre vár.");
}

function renderNavigation() {
  $("#mainNav").innerHTML = pages.map((page) => `
    <button class="nav-pill ${page.id === state.page ? "active" : ""}" data-page="${page.id}">
      <span>${page.icon}</span>
      <b>${page.label}</b>
    </button>
  `).join("");
}

function statusLabel(status) {
  const labels = { online: "Online", figyelni: "Figyelni", terv: "Terv" };
  return `<span class="status ${status}">${labels[status] || status}</span>`;
}

function moduleCard(module) {
  return `
    <article class="module-card">
      <div class="module-top">
        <span class="module-group">${module.group}</span>
        ${statusLabel(module.status)}
      </div>
      <h3>${module.title}</h3>
      <p>${module.text}</p>
      <div class="module-bottom">
        <strong>${module.metric}</strong>
        <button class="small-action" data-open="${module.id}">Megnyitás</button>
      </div>
    </article>
  `;
}

function healthCard(title, value, text, tone = "good") {
  return `
    <article class="health-card ${tone}">
      <span>${title}</span>
      <b>${value}</b>
      <small>${text}</small>
    </article>
  `;
}

function taskList() {
  return `
    <div class="task-list">
      ${tasks.map(([title, text, tag]) => `
        <div class="task-row">
          <div><b>${title}</b><span>${text}</span></div>
          <em>${tag}</em>
        </div>
      `).join("")}
    </div>
  `;
}

function homePage() {
  $("#pageTitle").textContent = "Command Center";
  $("#pageSubtitle").textContent = "Egy kezdőoldal, ami nem csak szép, hanem rögtön használható.";
  return `
    <section class="command-grid">
      <div class="command-main">
        <div class="focus-card">
          <span class="eyebrow">Mai fókusz</span>
          <h2>Elszámolás, PWA, TIG és műszakminőség egy közös belépési pontról.</h2>
          <p>A Hub nem váltja ki a rendszereket, hanem rendet rak közöttük. Minden fontos modul egy helyről indul, a státuszok pedig később Supabase-ből vagy jobokból jöhetnek.</p>
          <div class="action-row">
            <button class="primary-action" data-open="pwa">Futár PWA</button>
            <button class="secondary-action" data-open="devtest">Elszámolás admin</button>
            <button class="secondary-action" data-open="github">GitHub</button>
          </div>
        </div>
        <div class="module-grid">${modules.map(moduleCard).join("")}</div>
      </div>
      <aside class="command-side">
        <div class="panel">
          <h3>Rendszerállapot</h3>
          <div class="health-grid">
            ${healthCard("PWA", "OK", "Elérhető", "good")}
            ${healthCard("Elszámolás", "7", "ellenőrizendő", "warn")}
            ${healthCard("Robotok", "4", "napi job", "good")}
            ${healthCard("Adatminőség", "2", "nyitott kérdés", "warn")}
          </div>
        </div>
        <div class="panel">
          <h3>Mai teendők</h3>
          ${taskList()}
        </div>
      </aside>
    </section>
  `;
}

function opsPage() {
  $("#pageTitle").textContent = "Operáció";
  $("#pageSubtitle").textContent = "Futárok, műszakok, útvonalak és napi kontroll.";
  return `
    <section class="section-stack">
      <div class="metric-strip">
        ${healthCard("Aktív futár", "73", "BUD1 + BUD2")}
        ${healthCard("Mai műszak", "126", "foglalás alapján")}
        ${healthCard("Kockázatos műszak", "9", "késés/no-show", "warn")}
        ${healthCard("Jármű eltérés", "3", "sheet alapján", "warn")}
      </div>
      <div class="panel">
        <h3>Operációs modulok</h3>
        <div class="module-grid">${modules.filter((item) => ["pwa", "shifts", "robots", "fleet"].includes(item.id)).map(moduleCard).join("")}</div>
      </div>
      <div class="panel split-panel">
        <div>
          <h3>Műszakminőség terv</h3>
          <p>Ide kötném be a show/no-show riportot, a műszak kezdését, a sorba állást, és azt, hogy a futár időben visszaért-e a következő műszakhoz.</p>
        </div>
        <div class="mini-table">
          <div><b>Forrás</b><span>attendance + dsp route story</span></div>
          <div><b>Mentés</b><span>Supabase quality táblák</span></div>
          <div><b>Kimenet</b><span>napi és havi százalék</span></div>
        </div>
      </div>
    </section>
  `;
}

function moneyPage() {
  $("#pageTitle").textContent = "Pénzügy";
  $("#pageSubtitle").textContent = "Elszámolás, TIG, bónuszok, maluszok és kifizetés.";
  return `
    <section class="section-stack">
      <div class="metric-strip">
        ${healthCard("Fizetendő", formatMoney(22929355), "jelenlegi hónap")}
        ${healthCard("Vállalkozói díj", formatMoney(24106292), "kontroll érték")}
        ${healthCard("Kiflis tételek", "-83 000 Ft", "részletezve", "warn")}
        ${healthCard("JITT tételek", "-57 646 Ft", "sheet/DB", "warn")}
      </div>
      <div class="panel">
        <h3>Pénzügyi modulok</h3>
        <div class="module-grid">${modules.filter((item) => ["settlement", "documents", "bi"].includes(item.id)).map(moduleCard).join("")}</div>
      </div>
      <div class="panel split-panel">
        <div>
          <h3>Ahogy én összeraknám</h3>
          <p>Az admin devtest számítása legyen az igazságforrás. A PWA csak publikált snapshotot olvas. A TIG ugyanabból a végösszegből épül, hogy ne legyen eltérés a kártya, PWA és TIG között.</p>
        </div>
        <div class="mini-table">
          <div><b>Admin</b><span>számol és publikál</span></div>
          <div><b>Mobil</b><span>csak megjelenít</span></div>
          <div><b>TIG</b><span>ugyanazt a payable sort használja</span></div>
        </div>
      </div>
    </section>
  `;
}

function reportPage() {
  $("#pageTitle").textContent = "Műszak és túra kimutatás";
  $("#pageSubtitle").textContent = "Hónap → futár → műszak → túra szintű alábontás a DSP/mart adatokból.";
  ensureReportLoaded();
  const data = currentReport();
  const couriers = reportCouriers();
  const selected = selectReportCourier();
  const totals = data.totals || {};
  const totalDelay = toNumber(totals.delayBonus);
  const totalCompliance = toNumber(totals.complianceBonus);
  const totalRoutes = toNumber(totals.routes);
  const totalOrders = toNumber(totals.orders);

  if (!selected) {
    return `
      <section class="section-stack">
        <div class="panel empty-report">
          <h3>Nincs megjeleníthető adat</h3>
          <p>Ehhez a hónaphoz nem találtam futár/műszak sort.</p>
        </div>
      </section>
    `;
  }

  const routeRows = (selected.shifts || []).flatMap((shift) =>
    (shift.routes || []).map((route) => ({ shift, route }))
  );

  return `
    <section class="section-stack">
      ${reportState.error ? `
        <div class="panel report-warning">
          <b>A valós riport API még nem adott adatot.</b>
          <span>${escapeHtml(reportState.error)}</span>
        </div>
      ` : ""}
      <div class="metric-strip">
        ${healthCard("Delay bónusz", formatMoney(totalDelay), "havi összesítő")}
        ${healthCard("Compliance bónusz", formatMoney(totalCompliance), "havi összesítő")}
        ${healthCard("Kör", totalRoutes, "kifutott túra")}
        ${healthCard("Cím", totalOrders, "túra darabszám")}
      </div>

      <div class="panel report-control">
        <div>
          <span class="eyebrow">${data.source === "supabase" ? "Élő DB adat" : "Előnézeti adat"}</span>
          <h3>Hónap és futár kiválasztása</h3>
          <p>A riport a meglévő route story és shift quality táblákból épül fel. A sorrend: hónap, futár, műszak, majd azon belül a túrák/megrendelések részletei.</p>
        </div>
        <div class="report-control-fields">
          <label>
            Hónap
            <input class="hub-select" id="reportMonthInput" type="month" value="${escapeHtml(state.reportMonth)}">
          </label>
          <label>
            Futár
            <select class="hub-select" id="reportCourierSelect">
              ${couriers.map((courier) => `<option value="${escapeHtml(courier.courierId)}" ${String(courier.courierId) === String(selected.courierId) ? "selected" : ""}>${escapeHtml(courier.name)} · ${escapeHtml(courier.warehouse || "-")}</option>`).join("")}
            </select>
          </label>
          <label>
            Riport kulcs
            <input class="hub-select" id="reportTokenInput" type="password" value="${escapeHtml(state.reportToken)}" placeholder="belső riport kulcs">
          </label>
          <button class="small-action" id="reportRefreshButton" type="button">${reportState.loading ? "Töltés..." : "Frissítés"}</button>
        </div>
      </div>

      <div class="report-profile">
        <article class="panel report-summary">
          <span class="eyebrow">Kiválasztott futár</span>
          <h3>${escapeHtml(selected.name)}</h3>
          <div class="report-kpi-grid">
            <div><span>Raktár</span><b>${escapeHtml(selected.warehouse || "-")}</b></div>
            <div><span>Megrendelés / cím</span><b>${toNumber(selected.orders)}</b></div>
            <div><span>Kifutott túra</span><b>${toNumber(selected.routes)}</b></div>
            <div><span>Műszak</span><b>${(selected.shifts || []).length}</b></div>
            <div><span>Delay bónusz</span><b>${formatMoney(toNumber(selected.delayBonus))}</b></div>
            <div><span>Compliance bónusz</span><b>${formatMoney(toNumber(selected.complianceBonus))}</b></div>
          </div>
        </article>

        <article class="panel report-flow">
          <h3>Adatforrás</h3>
          <div class="flow-steps">
            <div><b>1</b><span>mart_dsp_route_stories</span><small>túra, cím, kiosztás, visszaérkezés</small></div>
            <div><b>2</b><span>dsp_courier_shift_quality_report</span><small>műszak, show/no-show, késés</small></div>
            <div><b>3</b><span>raw_jitt_invoice_perf_couriers_daily</span><small>delay és compliance bónusz összesítő</small></div>
          </div>
        </article>
      </div>

      <div class="panel">
        <div class="card-head">
          <div>
            <h3>Túra / megrendelés alábontás</h3>
            <p class="muted">Minden sor egy futott túra vagy route story rekord. Itt látszik mikor kapott címet, mekkora volt a túra és volt-e időablakos késés.</p>
          </div>
          <button class="small-action" onclick="toast('Itt később Excel export indul.')">Export</button>
        </div>
        <div class="report-table route-report-table">
          <div class="report-table-head">
            <span>Dátum</span><span>Műszak</span><span>Megrendelés / túra</span><span>Bejelentkezés</span><span>Túra hossza</span><span>Címet kapott</span><span>Darab</span><span>Tervezett vissza</span><span>Valós vissza</span><span>Időablak késés</span>
          </div>
          ${routeRows.length ? routeRows.map(({ shift, route }) => `
            <div class="report-table-row">
              <span>${escapeHtml(shift.workDate || "-")}</span>
              <span>${escapeHtml(shift.shiftName || "-")}</span>
              <span>${escapeHtml(route.routeId || "-")}</span>
              <span>${formatDateTime(shift.checkedInAt || shift.queueStartedAt || shift.availableAt)}</span>
              <span>${formatMinutes(route.routeDurationMinutes)}</span>
              <span>${formatDateTime(route.assignedAt)}</span>
              <span>${toNumber(route.addressCount)}</span>
              <span>${formatDateTime(route.plannedReturnAt)}</span>
              <span>${formatDateTime(route.realReturnAt)}</span>
              <span>${formatLate(route)}</span>
            </div>
          `).join("") : `<div class="report-empty-row">Ehhez a futárhoz nincs túra sor ebben a hónapban.</div>`}
        </div>
      </div>

      <div class="panel">
        <div class="card-head">
          <div>
            <h3>Műszak alábontás</h3>
            <p class="muted">A műszak kártyákon látszik a bejelentkezés, sorba állás, no-show jelölés és az adott műszak túrái.</p>
          </div>
          <span class="status ${reportState.loading ? "terv" : "online"}">${reportState.loading ? "Töltés" : "Betöltve"}</span>
        </div>
        <div class="shift-detail-grid">
          ${(selected.shifts || []).map((shift) => `
            <article>
              <div><b>${escapeHtml(shift.workDate || "-")}</b><span>${escapeHtml(shift.shiftName || "-")}</span></div>
              <dl>
                <div><dt>Mikor jelentkezett be</dt><dd>${formatDateTime(shift.checkedInAt || shift.queueStartedAt || shift.availableAt)}</dd></div>
                <div><dt>Elérhető volt</dt><dd>${formatDateTime(shift.availableAt)}</dd></div>
                <div><dt>Sorba állt</dt><dd>${formatDateTime(shift.queueStartedAt)}</dd></div>
                <div><dt>Túrák</dt><dd>${(shift.routes || []).length}</dd></div>
                <div><dt>No-show</dt><dd>${shift.noShow ? "Igen" : "Nem"}</dd></div>
                <div><dt>Megjegyzés</dt><dd>${escapeHtml(shift.noShowReason || shift.qualityNote || "OK")}</dd></div>
              </dl>
            </article>
          `).join("") || `<div class="report-empty-row">Ehhez a futárhoz nincs műszak sor ebben a hónapban.</div>`}
        </div>
      </div>
    </section>
  `;
}

function dataPage() {
  $("#pageTitle").textContent = "Adatok";
  $("#pageSubtitle").textContent = "Importok, jobok, szinkronok és hibák.";
  return `
    <section class="section-stack">
      <div class="metric-strip">
        ${healthCard("Utolsó DSP", "OK", "ma 06:00")}
        ${healthCard("Booking log", "OK", "Google Sheet")}
        ${healthCard("Bonus/malus", "Friss", "Excel + Sheet")}
        ${healthCard("Hibás sor", "12", "ellenőrzés", "warn")}
      </div>
      <div class="panel">
        <h3>Jobok, amiket ide raknék</h3>
        <div class="job-list">
          <div><b>dsp.py</b><span>napi teljesítmény és útvonal adatok</span><button class="small-action">Futtatás</button></div>
          <div><b>sync_loyalty_booking_log.py</b><span>MűszakPro LOG feldolgozás</span><button class="small-action">Futtatás</button></div>
          <div><b>import_google_bonus_malus_adjustments.py</b><span>JITT bónusz/malus DB sync</span><button class="small-action">Futtatás</button></div>
          <div><b>vehicle assignment sync</b><span>futár autó hozzárendelések</span><button class="small-action">Futtatás</button></div>
        </div>
      </div>
    </section>
  `;
}

function roadmapPage() {
  $("#pageTitle").textContent = "Bekötések";
  $("#pageSubtitle").textContent = "A látványterv mögé köthető konkrét adatforrások.";
  const rows = [
    ["Futár PWA", "pwa_api.py", "Éles link, snapshot, TIG", "Első"],
    ["Elszámolás admin", "devtest.py", "payable, vállalkozói díj, státusz", "Első"],
    ["Műszakminőség", "dsp route story + attendance", "show/no-show, késés, compliance", "Második"],
    ["Járművek", "Google Sheet", "napi autó hozzárendelés", "Második"],
    ["Discord", "Webhook vagy bot", "bónusz és műszak értesítés", "Harmadik"],
    ["Audit", "Supabase log táblák", "ki mit módosított", "Harmadik"]
  ];
  return `
    <section class="panel">
      <h3>Bekötési terv</h3>
      <div class="roadmap-table">
        ${rows.map(([name, source, output, phase]) => `
          <div>
            <b>${name}</b>
            <span>${source}</span>
            <span>${output}</span>
            <em>${phase}</em>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function formatDateOnly(value) {
  if (!value) return "-";
  const date = new Date(String(value).includes("T") ? value : `${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("hu-HU", { month: "2-digit", day: "2-digit" }).format(date);
}

function formatTimeOnly(value) {
  if (!value) return "-";
  const text = String(value);
  if (/^\d{2}:\d{2}/.test(text)) return text.slice(0, 5);
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return new Intl.DateTimeFormat("hu-HU", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatKm(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${new Intl.NumberFormat("hu-HU").format(Math.round(number))} km`;
}

function vehicleStatusClass(status) {
  if (status === "Kiosztva") return "good";
  if (status === "Tervezve") return "planned";
  if (status === "Szerviz esedékes") return "bad";
  if (status === "Szabad") return "free";
  return "warn";
}

function ensureVehiclesLoaded() {
  if (vehicleState.loading || vehicleState.loadedDate === state.vehicleDate) return;
  window.setTimeout(loadVehicles, 0);
}

async function loadVehicles() {
  if (vehicleState.loading) return;
  if (!state.reportToken) {
    vehicleState.data = null;
    vehicleState.loadedDate = state.vehicleDate;
    vehicleState.error = "Add meg a HUB riport kulcsot, hogy a járműadatokat DB-ből be lehessen tölteni.";
    render();
    return;
  }
  vehicleState.loading = true;
  vehicleState.error = "";
  render();
  try {
    const response = await fetch(`/api/vehicles?date=${encodeURIComponent(state.vehicleDate)}`, {
      headers: {
        Accept: "application/json",
        "x-hub-report-token": state.reportToken
      }
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    vehicleState.data = payload;
    vehicleState.loadedDate = state.vehicleDate;
    vehicleState.error = "";
  } catch (error) {
    vehicleState.data = null;
    vehicleState.loadedDate = state.vehicleDate;
    vehicleState.error = error.message || "A jármű API nem elérhető.";
  } finally {
    vehicleState.loading = false;
    render();
  }
}

function vehicleInputValue(id) {
  return $(`#${id}`)?.value.trim() || "";
}

async function saveVehicleService() {
  if (vehicleSaveState.saving) return;
  vehicleSaveState.message = "";
  vehicleSaveState.error = "";

  if (!state.reportToken) {
    vehicleSaveState.error = "Mentéshez add meg a riport kulcsot.";
    render();
    return;
  }

  const payload = {
    vehicle_plate: vehicleInputValue("vehicleEditPlate").toUpperCase(),
    car: vehicleInputValue("vehicleEditCar"),
    warehouse: vehicleInputValue("vehicleEditWarehouse").toUpperCase(),
    status: vehicleInputValue("vehicleEditStatus") || "active",
    odometer_km: vehicleInputValue("vehicleEditKm"),
    next_service_at: vehicleInputValue("vehicleEditNextService"),
    service_place: vehicleInputValue("vehicleEditServicePlace"),
    service_note: vehicleInputValue("vehicleEditNote"),
    updated_by: "jitt_hub"
  };

  if (!payload.vehicle_plate) {
    vehicleSaveState.error = "A rendszám kötelező.";
    render();
    return;
  }

  vehicleSaveState.saving = true;
  render();

  try {
    const response = await fetch("/api/vehicles", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-hub-report-token": state.reportToken
      },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    vehicleSaveState.message = `${payload.vehicle_plate} mentve.`;
    vehicleState.loadedDate = "";
    vehicleState.data = null;
    await loadVehicles();
  } catch (error) {
    vehicleSaveState.error = error.message || String(error);
  } finally {
    vehicleSaveState.saving = false;
    render();
  }
}

function vehicleWarehouses() {
  const vehicles = vehicleState.data?.vehicles || [];
  return Array.from(new Set(vehicles.map((vehicle) => vehicle.warehouse).filter(Boolean))).sort();
}

function filteredVehicles() {
  const search = state.vehicleSearch.trim().toLocaleLowerCase("hu-HU");
  return (vehicleState.data?.vehicles || []).filter((vehicle) => {
    if (state.vehicleWarehouse !== "all" && vehicle.warehouse !== state.vehicleWarehouse) return false;
    if (state.vehicleStatus !== "all" && vehicle.status !== state.vehicleStatus) return false;
    if (!search) return true;
    return [
      vehicle.plate,
      vehicle.car,
      vehicle.currentDriver,
      vehicle.warehouse,
      vehicle.servicePlace,
      vehicle.actualDriver,
      vehicle.actualPlate,
      vehicle.actualState
    ].some((value) => String(value || "").toLocaleLowerCase("hu-HU").includes(search));
  });
}

function vehicleSummaryCard(title, value, text, tone = "") {
  return `
    <article class="vehicle-summary-card ${tone}">
      <span>${escapeHtml(title)}</span>
      <b>${escapeHtml(value)}</b>
      <small>${escapeHtml(text || "")}</small>
    </article>
  `;
}

function vehicleToolbar() {
  const warehouses = vehicleWarehouses();
  return `
    <section class="vehicle-toolbar">
      <label>
        <span>Nap</span>
        <input id="vehicleDate" type="date" value="${escapeHtml(state.vehicleDate)}" />
      </label>
      <label>
        <span>Raktár</span>
        <select id="vehicleWarehouse">
          <option value="all">Összes raktár</option>
          ${warehouses.map((warehouse) => `<option value="${escapeHtml(warehouse)}" ${warehouse === state.vehicleWarehouse ? "selected" : ""}>${escapeHtml(warehouse)}</option>`).join("")}
        </select>
      </label>
      <label>
        <span>Állapot</span>
        <select id="vehicleStatus">
          ${["all", "Kiosztva", "Tervezve", "Szabad", "Szerviz esedékes"].map((status) => `<option value="${status}" ${status === state.vehicleStatus ? "selected" : ""}>${status === "all" ? "Minden állapot" : status}</option>`).join("")}
        </select>
      </label>
      <label class="wide">
        <span>Keresés</span>
        <input id="vehicleSearch" type="search" value="${escapeHtml(state.vehicleSearch)}" placeholder="Rendszám, autó, futár" />
      </label>
      <label class="wide">
        <span>Riport kulcs</span>
        <input id="vehicleTokenInput" type="password" value="${escapeHtml(state.reportToken)}" placeholder="HUB_REPORT_TOKEN" />
      </label>
      <button class="primary-action" id="vehicleRefreshButton" type="button">Frissítés</button>
    </section>
  `;
}

function vehicleEditor() {
  const statusOptions = [
    ["active", "Aktív"],
    ["service", "Szerviz"],
    ["damaged", "Sérült"],
    ["inactive", "Inaktív"]
  ];
  return `
    <section class="vehicle-editor">
      <div class="vehicle-editor-head">
        <div>
          <span>DB mentés</span>
          <h2>Új / módosított járműadat</h2>
          <p>Rendszám alapján új sort hoz létre vagy frissíti a meglévőt.</p>
        </div>
        <button class="primary-action" id="vehicleSaveButton" type="button" ${vehicleSaveState.saving ? "disabled" : ""}>
          ${vehicleSaveState.saving ? "Mentés..." : "Járműadat mentése"}
        </button>
      </div>
      <div class="vehicle-editor-grid">
        <label>
          <span>Rendszám</span>
          <input id="vehicleEditPlate" placeholder="pl. AIGH120" />
        </label>
        <label>
          <span>Autó típusa</span>
          <input id="vehicleEditCar" placeholder="pl. Opel Combo Van" />
        </label>
        <label>
          <span>Raktár</span>
          <input id="vehicleEditWarehouse" placeholder="pl. BUD2" />
        </label>
        <label>
          <span>Állapot</span>
          <select id="vehicleEditStatus">
            ${statusOptions.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
          </select>
        </label>
        <label>
          <span>Km állás</span>
          <input id="vehicleEditKm" type="number" min="0" step="1" placeholder="pl. 124500" />
        </label>
        <label>
          <span>Következő szerviz</span>
          <input id="vehicleEditNextService" type="date" />
        </label>
        <label>
          <span>Szerviz helye</span>
          <input id="vehicleEditServicePlace" placeholder="pl. BUD2 műhely" />
        </label>
        <label class="wide">
          <span>Megjegyzés</span>
          <textarea id="vehicleEditNote" placeholder="Szerviz, sérülés, státusz vagy kiosztási megjegyzés"></textarea>
        </label>
      </div>
      ${vehicleSaveState.error ? `<div class="vehicle-save-status error">${escapeHtml(vehicleSaveState.error)}</div>` : ""}
      ${vehicleSaveState.message ? `<div class="vehicle-save-status ok">${escapeHtml(vehicleSaveState.message)}</div>` : ""}
    </section>
  `;
}

function vehicleAssignments(vehicle) {
  const assignments = vehicle.assignments || [];
  if (!assignments.length) return `<div class="vehicle-assignment-empty">Nincs következő kiosztás.</div>`;
  return assignments.map((assignment) => `
    <div class="vehicle-assignment-row">
      <b>${formatDateOnly(assignment.workDate)}</b>
      <span>${escapeHtml(assignment.driverName || "-")}</span>
      <span>${formatTimeOnly(assignment.shiftStart)}-${formatTimeOnly(assignment.shiftEnd)}</span>
      <em>${escapeHtml(assignment.warehouse || "-")}</em>
    </div>
  `).join("");
}

function vehicleCard(vehicle) {
  const statusClass = vehicleStatusClass(vehicle.status);
  const title = vehicle.plate || vehicle.car || "Ismeretlen jármű";
  return `
    <article class="vehicle-card ${statusClass}">
      <header>
        <div>
          <span>${escapeHtml(vehicle.warehouse || "Nincs raktár")}</span>
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(vehicle.car || "Típus nincs megadva")}</p>
        </div>
        <strong class="vehicle-status ${statusClass}">${escapeHtml(vehicle.status || "Nincs adat")}</strong>
      </header>
      <div class="vehicle-facts">
        <div><span>Kinél van</span><b>${escapeHtml(vehicle.currentDriver || "-")}</b></div>
        <div><span>Valósan felvette</span><b>${escapeHtml(vehicle.actualDriver || "-")}</b></div>
        <div><span>Valós autó</span><b>${escapeHtml(vehicle.actualPlate || "-")}</b></div>
        <div><span>Live állapot</span><b>${escapeHtml(vehicle.actualState || "-")}</b></div>
        <div><span>Kiosztás napja</span><b>${formatDateOnly(vehicle.currentAssignmentDate)}</b></div>
        <div><span>Műszak</span><b>${formatTimeOnly(vehicle.currentShiftStart)}-${formatTimeOnly(vehicle.currentShiftEnd)}</b></div>
        <div><span>Km állás</span><b>${formatKm(vehicle.odometerKm)}</b></div>
        <div><span>Következő szerviz</span><b>${formatDateOnly(vehicle.nextServiceAt)}</b></div>
        <div><span>Szerviz helye</span><b>${escapeHtml(vehicle.servicePlace || "-")}</b></div>
        <div><span>Live frissítés</span><b>${formatDateOnly(vehicle.actualSeenAt)} ${formatTimeOnly(vehicle.actualSeenAt)}</b></div>
      </div>
      <details>
        <summary>Kocsi kiosztása</summary>
        <div class="vehicle-assignment-list">${vehicleAssignments(vehicle)}</div>
      </details>
    </article>
  `;
}

function vehiclesList() {
  if (vehicleState.loading) return `<div class="vehicle-empty">Járműadatok betöltése...</div>`;
  if (vehicleState.error) return `<div class="vehicle-empty error">${escapeHtml(vehicleState.error)}</div>`;
  const vehicles = filteredVehicles();
  if (!vehicles.length) return `<div class="vehicle-empty">Nincs jármű a kiválasztott szűrésre.</div>`;
  return `<section class="vehicle-grid">${vehicles.map(vehicleCard).join("")}</section>`;
}

function vehiclesPage() {
  ensureVehiclesLoaded();
  const totals = vehicleState.data?.totals || {};
  const source = vehicleState.data?.source || {};
  $("#pageTitle").textContent = "Járművek";
  $("#pageSubtitle").textContent = "Autóállapot, raktár, kiosztás, km és szerviz egy helyen.";
  return `
    ${vehicleToolbar()}
    <section class="vehicle-summary-grid">
      ${vehicleSummaryCard("Jármű összesen", totals.vehicles ?? "-", `Kiosztási sor: ${source.assignments ?? 0}`)}
      ${vehicleSummaryCard("Ma kiosztva", totals.assigned ?? "-", "Az adott napra", "good")}
      ${vehicleSummaryCard("Tervezve", totals.planned ?? "-", "Következő napokra", "planned")}
      ${vehicleSummaryCard("Szabad", totals.free ?? "-", "Nincs mai kiosztás", "free")}
      ${vehicleSummaryCard("Szerviz esedékes", totals.serviceDue ?? "-", "Szerviz DB alapján", "bad")}
    </section>
    <div class="vehicle-source">
      <span>Frissítve: ${escapeHtml(vehicleState.data?.generatedAt ? new Date(vehicleState.data.generatedAt).toLocaleString("hu-HU") : "-")}</span>
      <span>Route story sorok: ${source.routeStories ?? 0}</span>
      <span>Szerviz sorok: ${source.serviceRows ?? 0}</span>
      <span>Live fetch-drivers sorok: ${source.liveRows ?? 0}</span>
      <span>Live forrás: ${escapeHtml([source.liveRawTable, source.liveKmTable].filter(Boolean).join(" + ") || "-")}</span>
    </div>
    ${vehicleEditor()}
    <div id="vehicleListSlot">${vehiclesList()}</div>
  `;
}

function render() {
  renderNavigation();
  const renderer = {
    vehicles: vehiclesPage
  }[state.page] || vehiclesPage;
  $("#pageContent").innerHTML = renderer();
}

function showApp() {
  $("#loginScreen").hidden = true;
  $("#appShell").hidden = false;
  render();
}

function showLogin() {
  $("#appShell").hidden = true;
  $("#loginScreen").hidden = false;
}

function setup() {
  setTheme();
  $("#mainNav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (!button) return;
    state.page = button.dataset.page;
    render();
  });
  document.body.addEventListener("change", (event) => {
    if (event.target.id === "reportCourierSelect") {
      state.reportCourierId = event.target.value;
      render();
      return;
    }
    if (event.target.id === "reportMonthInput") {
      state.reportMonth = event.target.value || state.reportMonth;
      reportState.loadedMonth = "";
      reportState.data = null;
      state.reportCourierId = "";
      render();
      return;
    }
    if (event.target.id === "reportTokenInput") {
      state.reportToken = event.target.value.trim();
      if (state.reportToken) sessionStorage.setItem("jittHubReportToken", state.reportToken);
      else sessionStorage.removeItem("jittHubReportToken");
    }
    if (event.target.id === "vehicleDate") {
      state.vehicleDate = event.target.value || state.vehicleDate;
      vehicleState.loadedDate = "";
      vehicleState.data = null;
      loadVehicles();
      return;
    }
    if (event.target.id === "vehicleWarehouse") {
      state.vehicleWarehouse = event.target.value || "all";
      render();
      return;
    }
    if (event.target.id === "vehicleStatus") {
      state.vehicleStatus = event.target.value || "all";
      render();
      return;
    }
    if (event.target.id === "vehicleTokenInput") {
      state.reportToken = event.target.value.trim();
      if (state.reportToken) sessionStorage.setItem("jittHubReportToken", state.reportToken);
      else sessionStorage.removeItem("jittHubReportToken");
    }
  });
  document.body.addEventListener("input", (event) => {
    if (event.target.id === "vehicleSearch") {
      state.vehicleSearch = event.target.value || "";
      const target = $("#vehicleListSlot");
      if (target) target.innerHTML = vehiclesList();
    }
  });
  document.body.addEventListener("click", (event) => {
    if (event.target.closest("#vehicleRefreshButton")) {
      vehicleState.loadedDate = "";
      vehicleState.data = null;
      loadVehicles();
      return;
    }
    if (event.target.closest("#vehicleSaveButton")) {
      saveVehicleService();
      return;
    }
    if (event.target.closest("#reportRefreshButton")) {
      reportState.loadedMonth = "";
      reportState.data = null;
      loadReport();
      return;
    }
    const button = event.target.closest("[data-open]");
    if (!button) return;
    openTarget(button.dataset.open);
  });
  $("#themeToggle").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    localStorage.setItem("jittHubTheme", state.theme);
    setTheme();
  });
  $("#logoutButton").addEventListener("click", () => {
    sessionStorage.removeItem("jittHubSession");
    showLogin();
  });
  $("#passwordToggle").addEventListener("click", () => {
    const input = $("#loginPassword");
    input.type = input.type === "password" ? "text" : "password";
  });
  $("#loginForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const email = $("#loginEmail").value.trim().toLowerCase();
    const password = $("#loginPassword").value;
    if (email === DEMO_USER.email && password === DEMO_USER.password) {
      sessionStorage.setItem("jittHubSession", JSON.stringify({ user: DEMO_USER.name }));
      showApp();
      toast("Belépve a JITT Hubba.");
      return;
    }
    $("#loginError").textContent = "Hibás felhasználónév vagy jelszó.";
  });
  if (sessionStorage.getItem("jittHubSession")) {
    showApp();
  } else {
    showLogin();
  }
}

setup();
