/* Monthly trend view. Unknown measurements remain gaps, not zero values. */
let loadedTrendMonth = null;
let trendLoadSequence = 0;

function trendValue(value, kind) {
  if (value === null || value === undefined) return '—';
  return kind === 'money' ? huf(value) : kind === 'hours' ? hours(value) : `${nf.format(value)} db`;
}

function trendChange(rows, field, kind) {
  const first = rows[0]?.[field], last = rows[rows.length-1]?.[field];
  if (first == null || last == null) return 'A változás nem mérhető';
  const difference = last-first;
  const sign = difference > 0 ? '+' : difference < 0 ? '−' : '';
  const unit = kind === 'money' ? huf(Math.abs(difference)) : kind === 'hours' ? hours(Math.abs(difference)) : `${nf.format(Math.abs(difference))} db`;
  return `${sign}${unit} az első hónaphoz képest`;
}

function trendChart(rows, series, kind, title) {
  const left=72, top=26, bottom=191, width=500, height=240;
  const max=Math.max(1,...rows.flatMap(row=>series.map(s=>Number(row[s.key])||0)));
  const y=value=>bottom-(Number(value)/max)*(bottom-top);
  const x=index=>left+55+index*145;
  const axis=kind==='money'?value=>short(value):kind==='hours'?value=>`${nf.format(value)} óra`:value=>nf.format(value);
  let svg=`<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>`;
  for(let step=0;step<=3;step++){
    const value=max*step/3, pos=y(value);
    svg+=`<line x1="${left}" x2="490" y1="${pos}" y2="${pos}" stroke="#e0e5ee"/><text x="${left-8}" y="${pos+4}" text-anchor="end">${esc(axis(value))}</text>`;
  }
  rows.forEach((row,index)=>{
    svg+=`<text x="${x(index)}" y="218" text-anchor="middle">${esc(monthLabel(row.month))}</text>`;
    series.forEach((s,seriesIndex)=>{
      const value=row[s.key];
      const center=x(index)+(seriesIndex-(series.length-1)/2)*34;
      if(value==null){svg+=`<text x="${center}" y="${bottom-8}" text-anchor="middle">—</text>`;return;}
      const pos=y(value),barWidth=series.length>1?27:52;
      svg+=`<rect x="${center-barWidth/2}" y="${pos}" width="${barWidth}" height="${bottom-pos}" rx="4" fill="${s.color}"><title>${esc(monthLabel(row.month))} · ${esc(s.label)}: ${esc(trendValue(value,kind))}</title></rect><text x="${center}" y="${Math.max(14,pos-7)}" text-anchor="middle">${esc(kind==='money'?short(value):nf.format(value))}</text>`;
    });
  });
  return svg+'</svg>';
}

function renderTrends(payload) {
  const rows=payload.months||[];
  if(!rows.length){$('#trend-body').innerHTML='<div class="empty">Nincs elérhető havi adat.</div>';return;}
  const last=rows[rows.length-1];
  const specs=[
    ['Reklamációk','complaintCount','count','Az elszámolási hónap aktív pénzügyi reklamációi; törölt és külön előlegfolyamatok nélkül.'],
    ['Átlagos válaszidő','responseAverageHours','hours','Csak a válasz időpontjával rendelkező ügyekből. A hiányzó időpont nem nulla órás válasz.'],
    ['Bónuszok','bonusHuf','money','Teljesítmény- és egyéb bónusz, JITT-bónusz és Kifli-bónusz együtt; pozitív korrekció nélkül.'],
    ['Maluszok','malusHuf','money','Kifli- és JITT-maluszok összege, egyéb levonások nélkül.'],
    ['Hozzáadott előlegek','advanceCount','count','Aktív előlegtervek és tervhez még nem kapcsolt jóváhagyott igények darabszáma, kezdő hónap szerint. Nem a levonási részletek száma.'],
  ];
  $('#trend-period').textContent=`${monthLabel(rows[0].month)} – ${monthLabel(last.month)} · a kártyák az utolsó hónapot mutatják.`;
  const kpis=specs.map(([label,field,kind,help])=>`<article class="kpi"><label>${label} <span class="help" tabindex="0" title="${esc(help)}">?</span></label><b>${trendValue(last[field],kind)}</b><p>${trendChange(rows,field,kind)}</p></article>`).join('');
  const panel=(title,series,kind,note)=>`<article class="panel"><h3>${title}</h3>${trendChart(rows,series,kind,title)}${series.length>1?`<div class="trend-keys">${series.map(s=>`<span><i style="background:${s.color}"></i>${s.label}</span>`).join('')}</div>`:''}<p class="trend-note">${note}</p></article>`;
  const charts=[
    panel('Reklamációk darabszáma',[{key:'complaintCount',label:'Reklamáció',color:'#3867ef'}],'count','Az adott elszámolási hónaphoz tartozó ügyek, a folyamatban lévő elszámolásokkal együtt.'),
    panel('Átlagos válaszidő',[{key:'responseAverageHours',label:'Átlagos válaszidő',color:'#38b3c7'}],'hours',rows.map(r=>`${esc(monthLabel(r.month))}: ${nf.format(r.responseTimedCount)} mérhető válasz`).join(' · ')),
    panel('Bónuszok és maluszok',[{key:'bonusHuf',label:'Bónusz',color:'#49ae78'},{key:'malusHuf',label:'Malusz',color:'#e56762'}],'money','Futáronként a legutóbbi mentett pénzügyi verzióból. A hiányos lefedettséget a havi táblázat jelzi.'),
    panel('Hozzáadott fizetési előlegek száma',[{key:'advanceCount',label:'Új előleg',color:'#d88851'}],'count','Egy kapcsolt igény és törlesztési terv egy előlegnek számít. A megadott kezdő hónap szerint, nem igazolt banki kifizetésként.'),
  ].join('');
  const table=`<article class="panel" style="margin-top:14px"><h3>Havi részletezés és adatlefedettség</h3><div class="trend-table-wrap"><table class="table trend-table"><thead><tr><th>Hónap</th><th>Reklamáció</th><th>Átlag válaszidő</th><th>Bónusz</th><th>Malusz</th><th>Új előleg</th><th>Pénzügyi forrás</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(monthLabel(r.month))}</td><td>${trendValue(r.complaintCount,'count')}</td><td>${trendValue(r.responseAverageHours,'hours')}</td><td>${trendValue(r.bonusHuf,'money')}</td><td>${trendValue(r.malusHuf,'money')}</td><td>${nf.format(r.advanceCount)} db<br><small>${huf(r.advanceAmountHuf)}</small></td><td class="${r.courierCount!=null&&r.financeCoveredCouriers<r.courierCount?'trend-missing':''}">${nf.format(r.financeCoveredCouriers)} / ${r.courierCount??'—'} futár</td></tr>`).join('')}</tbody></table></div><p class="trend-note">A „—” hiányzó vagy nem mérhető adatot jelent. Az aktuális, még nyitott hónap értékei részlegesek lehetnek. Az előleg hozzáadása nem növeli a bónuszösszeget.</p></article>`;
  $('#trend-body').innerHTML=`<div class="trend-kpis">${kpis}</div><div class="trend-grid">${charts}</div>${table}`;
}

async function loadTrends() {
  const month=$('#month').value;
  if(loadedTrendMonth===month)return;
  const sequence=++trendLoadSequence;
  $('#trend-status').textContent='Betöltés…';$('#trend-error').hidden=true;
  $('#trend-body').innerHTML='<div class="empty">A három hónap adatainak betöltése…</div>';
  try {
    const payload=await api(`/api/settlement-trends?month=${encodeURIComponent(month)}`);
    if(sequence!==trendLoadSequence||$('#month').value!==month)return;
    renderTrends(payload);loadedTrendMonth=month;$('#trend-status').textContent='3 hónap · adatbázisból';
  }catch(error){
    if(sequence!==trendLoadSequence)return;
    $('#trend-error').textContent=`A tendenciák nem tölthetők be: ${error.message}`;$('#trend-error').hidden=false;
    $('#trend-body').innerHTML='';$('#trend-status').textContent='Adathiba';
  }
}
