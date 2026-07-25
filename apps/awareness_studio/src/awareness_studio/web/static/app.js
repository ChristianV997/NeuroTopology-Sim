'use strict';
const $ = (selector) => document.querySelector(selector);
let snapshot = null;

function esc(value) { const node = document.createElement('span'); node.textContent = String(value ?? ''); return node.innerHTML; }
function bytes(value) { if (value < 1024) return `${value} B`; if (value < 1048576) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1048576).toFixed(1)} MB`; }
function age(iso) { const ms = Date.now() - new Date(iso).getTime(); const days = Math.floor(ms / 86400000); if (days > 0) return `${days}d ago`; const hours = Math.floor(ms / 3600000); return hours > 0 ? `${hours}h ago` : 'recently'; }

function renderMetrics(data) {
  const labels = [['simulation_reports','Simulation reports','⌁'],['output_artifacts','Output artifacts','▱'],['command_center_payloads','Command payloads','◇'],['rag_artifacts','RAG assets','◎']];
  $('#metrics').innerHTML = labels.map(([key,label,icon]) => `<article class="metric"><span class="metric-icon">${icon}</span><div><strong>${data.counts[key]}</strong><p>${label}</p></div><span class="verified">REPO</span></article>`).join('');
}

function reportRow(item) {
  return `<button class="report-row previewable" data-path="${esc(item.path)}"><span class="report-index">${String(snapshot.simulations.indexOf(item)+1).padStart(2,'0')}</span><span class="report-main"><b>${esc(item.title)}</b><small>${esc(item.path)}</small></span>${item.dataset ? `<span class="dataset">${esc(item.dataset)}</span>` : ''}<span class="file-meta">${bytes(item.bytes)}<small>${age(item.updated_at)}</small></span><span class="arrow">↗</span></button>`;
}
function renderReports(query='') {
  const terms = query.toLowerCase(); const items = snapshot.simulations.filter(x => `${x.title} ${x.path} ${x.dataset || ''}`.toLowerCase().includes(terms));
  $('#simulations').innerHTML = items.length ? items.map(reportRow).join('') : '<div class="empty">No matching reports in this checkout.</div>';
  $('#report-count').textContent = `${items.length} / ${snapshot.simulations.length}`;
}
function renderDistribution(groups) {
  const shown = groups.slice(0,8), max = Math.max(...shown.map(x=>x.count),1);
  $('#distribution').innerHTML = shown.map((x,i) => `<div class="bar-row"><span>${esc(x.name.replaceAll('_',' '))}</span><div class="bar-track"><i style="width:${x.count/max*100}%;--delay:${i*40}ms"></i></div><b>${x.count}</b></div>`).join('');
}
function renderRecent(items) {
  $('#recent').innerHTML = items.slice(0,7).map(x => `<button class="recent-row previewable" data-path="${esc(x.path)}"><span class="type">${esc(x.kind.toUpperCase())}</span><span><b>${esc(x.name)}</b><small>${esc(x.path)} · ${bytes(x.bytes)}</small></span><time>${age(x.updated_at)}</time></button>`).join('');
}
function bindPreviews() { document.querySelectorAll('.previewable').forEach(el => el.addEventListener('click', () => preview(el.dataset.path))); }
async function preview(path) { const dialog=$('#preview'); $('#preview-title').textContent=path; $('#preview-body').textContent='Loading repository artifact…'; dialog.showModal(); try { const r=await fetch(`/research-ops/file?path=${encodeURIComponent(path)}`); const d=await r.json(); if(!r.ok) throw new Error(d.detail); $('#preview-body').textContent=d.content; } catch(e) { $('#preview-body').textContent=`Preview unavailable: ${e.message}`; } }

async function load() {
  $('#refresh').classList.add('spinning');
  try {
    const response = await fetch('/research-ops/snapshot', {cache:'no-store'}); if (!response.ok) throw new Error(response.statusText); snapshot = await response.json();
    renderMetrics(snapshot); renderReports($('#search').value); renderDistribution(snapshot.artifact_groups); renderRecent(snapshot.recent_artifacts);
    $('#guardrails').innerHTML = snapshot.guardrails.map(x=>`<span>✓ ${esc(x)}</span>`).join('');
    $('#generated-at').textContent = `Scanned ${new Date(snapshot.generated_at).toLocaleString()}`; $('#rail-status').textContent = `${snapshot.counts.output_artifacts} artifacts indexed`;
    bindPreviews(); $('.live-dot').classList.add('ok');
  } catch (error) { $('#rail-status').textContent='inventory unavailable'; $('#simulations').innerHTML=`<div class="empty">Could not load repository inventory: ${esc(error.message)}</div>`; }
  finally { $('#refresh').classList.remove('spinning'); }
}

$('#refresh').addEventListener('click', load); $('#search').addEventListener('input', e => { if(snapshot){renderReports(e.target.value);bindPreviews();} });
$('#preview-close').addEventListener('click',()=>$('#preview').close());
document.querySelectorAll('.nav-item').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));btn.classList.add('active');const target={overview:'.hero',simulations:'#simulations',artifacts:'#recent',payloads:'#distribution'}[btn.dataset.view];document.querySelector(target)?.scrollIntoView({behavior:'smooth',block:'center'});}));
load();
