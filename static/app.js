/* LeadHunter Pro — Frontend Logic */

let currentSearchId = null;
let currentLeads = [];

// ─── Search ──────────────────────────────────
async function startSearch(e) {
    e.preventDefault();
    const query = document.getElementById('query').value.trim();
    const location = document.getElementById('location').value.trim();
    if (!query || !location) return alert('Enter business type and location');

    const sources = [];
    document.querySelectorAll('.source-check input:checked').forEach(cb => sources.push(cb.value));
    if (sources.length === 0) return alert('Select at least one source');

    document.getElementById('searchBtn').disabled = true;
    document.getElementById('searchBtn').innerHTML = '<span class="spinner"></span> Searching...';
    showProgress();

    try {
        const resp = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, location, sources }),
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentSearchId = data.search_id;
        pollProgress(data.search_id);
    } catch (err) {
        alert('Error: ' + err.message);
        resetSearchBtn();
    }
}

function resetSearchBtn() {
    const btn = document.getElementById('searchBtn');
    btn.disabled = false;
    btn.innerHTML = '🔍 Hunt Leads';
}

// ─── Progress ────────────────────────────────
function showProgress() {
    document.getElementById('progressSection').classList.add('active');
}

function hideProgress() {
    document.getElementById('progressSection').classList.remove('active');
}

async function pollProgress(searchId) {
    const evtSource = new EventSource(`/api/search/${searchId}/progress`);
    evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateProgressUI(data);
        if (data.status === 'completed' || data.status === 'error') {
            evtSource.close();
            resetSearchBtn();
            if (data.status === 'completed') {
                loadLeads(searchId);
            }
        }
    };
    evtSource.onerror = () => {
        evtSource.close();
        resetSearchBtn();
    };
}

function updateProgressUI(data) {
    const stageEl = document.getElementById('progressStage');
    const barEl = document.getElementById('progressBarFill');
    const msgEl = document.getElementById('progressMessage');
    const logsEl = document.getElementById('progressLogs');

    const stageNames = {
        google_maps: '🗺️ Google Maps',
        justdial: '📞 JustDial',
        saving: '💾 Saving to Database',
        dedup: '🔄 Deduplication',
        website_analysis: '🌐 Website Analysis',
        scoring: '⚡ Scoring Leads',
        retry: '🔄 Retrying Failed',
        resuming: '▶️ Resuming',
        done: '✅ Complete',
        error: '❌ Error',
    };

    stageEl.textContent = stageNames[data.stage] || data.stage;
    msgEl.textContent = data.message || '';

    if (data.total > 0) {
        const pct = Math.round((data.progress / data.total) * 100);
        barEl.style.width = pct + '%';
    } else {
        barEl.style.width = '30%';
        barEl.style.animation = 'pulse 1.5s infinite';
    }

    if (data.logs && data.logs.length) {
        logsEl.textContent = data.logs.slice(-15).join('\n');
        logsEl.scrollTop = logsEl.scrollHeight;
    }
}

// ─── Load Leads ──────────────────────────────
let leadsOffset = 0;
let leadsHasMore = false;
const LEADS_PAGE = 100;

async function loadLeads(searchId) {
    try {
        leadsOffset = 0;
        currentSearchId = searchId;
        const resp = await fetch(`/api/search/${searchId}/leads?limit=${LEADS_PAGE}&offset=0`);
        const data = await resp.json();
        currentLeads = data.leads || [];
        leadsHasMore = data.has_more;
        renderLeads(currentLeads, data.total);
        hideProgress();
    } catch (err) {
        console.error('Failed to load leads:', err);
    }
}

async function loadMoreLeads() {
    leadsOffset += LEADS_PAGE;
    const resp = await fetch(`/api/search/${currentSearchId}/leads?limit=${LEADS_PAGE}&offset=${leadsOffset}`);
    const data = await resp.json();
    currentLeads = currentLeads.concat(data.leads || []);
    leadsHasMore = data.has_more;
    renderLeads(currentLeads, data.total);
}

function renderLeads(leads, total) {
    const container = document.getElementById('leadsGrid');
    const section = document.getElementById('resultsSection');
    const countEl = document.getElementById('resultsCount');

    if (!leads.length) {
        container.innerHTML = `<div class="empty-state">
            <div class="icon">🔍</div>
            <h3>No leads found</h3>
            <p>Try a different search query or expand your location radius.</p>
        </div>`;
        section.style.display = 'block';
        return;
    }

    countEl.textContent = `Showing ${leads.length} of ${total || leads.length} leads`;
    section.style.display = 'block';

    container.innerHTML = leads.map((lead, i) => {
        const score = lead.ai_ranking_score || 0;
        let scoreClass = 'skip';
        if (score >= 70) scoreClass = 'hot';
        else if (score >= 45) scoreClass = 'warm';
        else if (score >= 25) scoreClass = 'cold';

        let ai = {};
        try { ai = JSON.parse(lead.ai_analysis || '{}'); } catch(e) {}
        const verdict = ai.verdict || 'WARM';
        const pitch = ai.pitch || '';

        const rating = lead.rating ? `⭐ ${lead.rating}` : '';
        const reviews = lead.review_count ? `(${lead.review_count})` : '';
        const phone = lead.phone ? `📞 ${lead.phone}` : '';
        const hasWebsite = lead.website ? '' : '<span class="no-website-flag">🚫 No Website</span>';

        return `<div class="lead-card animate-in" style="animation-delay:${Math.min(i, 20) * 0.03}s" onclick="showLeadDetail(${lead.id})">
            <div class="lead-score ${scoreClass}">${score}</div>
            <div class="lead-info">
                <div class="lead-name">
                    ${lead.business_name || 'Unknown'}
                    <span class="source-tag ${lead.source}">${lead.source === 'google_maps' ? 'GMaps' : 'JD'}</span>
                    ${hasWebsite}
                </div>
                <div class="lead-meta">
                    ${lead.category ? `<span>🏷️ ${lead.category}</span>` : ''}
                    ${rating ? `<span>${rating} ${reviews}</span>` : ''}
                    ${phone ? `<span>${phone}</span>` : ''}
                    ${lead.address ? `<span>📍 ${(lead.address || '').substring(0, 50)}</span>` : ''}
                </div>
            </div>
            <div class="lead-actions">
                <span class="verdict-badge ${verdict}">${verdict}</span>
                ${pitch ? `<span class="lead-pitch">${pitch}</span>` : ''}
            </div>
        </div>`;
    }).join('') + (leadsHasMore ? `<div style="text-align:center;padding:20px;grid-column:1/-1">
        <button onclick="loadMoreLeads()" class="btn btn-primary" style="padding:12px 32px;font-size:15px">Load More (next 100) ↓</button>
    </div>` : '');
}

// ─── Filters ─────────────────────────────────
function filterLeads(type) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    let filtered = [...currentLeads];
    switch (type) {
        case 'hot': filtered = filtered.filter(l => l.ai_ranking_score >= 70); break;
        case 'warm': filtered = filtered.filter(l => l.ai_ranking_score >= 45 && l.ai_ranking_score < 70); break;
        case 'no-website': filtered = filtered.filter(l => !l.website); break;
        case 'has-website': filtered = filtered.filter(l => !!l.website); break;
        case 'contact': filtered = filtered.filter(l => l.worth_contacting === 1); break;
    }
    renderLeads(filtered);
}

// ─── Lead Detail Modal ───────────────────────
async function showLeadDetail(leadId) {
    const lead = currentLeads.find(l => l.id === leadId);
    if (!lead) return;

    const modal = document.getElementById('modalOverlay');
    const content = document.getElementById('modalContent');

    let ai = {};
    try { ai = JSON.parse(lead.ai_analysis || '{}'); } catch(e) {}
    let wa = {};
    try { wa = JSON.parse(lead.website_analysis || '{}'); } catch(e) {}
    let raw = {};
    try { raw = JSON.parse(lead.raw_data || '{}'); } catch(e) {}

    const websiteInfo = lead.website
        ? `<a href="${lead.website}" target="_blank">${lead.website}</a>`
        : '<span style="color:var(--success)">No Website — OPPORTUNITY!</span>';

    const mapsLink = raw.maps_url
        ? `<a href="${raw.maps_url}" target="_blank">📍 Open in Google Maps</a>`
        : 'N/A';

    const webScore = lead.website_score >= 0
        ? `${lead.website_score}/100`
        : 'N/A (no website)';

    // Website analysis report data

    
    const reportBullets = (wa.detailed_report || [])
        .map(r => `<li style="margin-bottom:6px">${r}</li>`).join('');
    const recBullets = (wa.recommendations || [])
        .map(r => `<li style="margin-bottom:6px;color:var(--accent)">${r}</li>`).join('');

    content.innerHTML = `
        <div class="modal-header">
            <div>
                <h2 style="font-size:22px;margin-bottom:4px">${lead.business_name || 'Unknown'}</h2>
                <span style="color:var(--text-muted);font-size:13px">${lead.category || ''} · ${lead.source}</span>
            </div>
            <button class="modal-close" onclick="closeModal()">✕</button>
        </div>
        <div class="detail-grid">
            <div class="detail-item"><label>Score</label><div class="value" style="font-size:24px;font-weight:800;color:${lead.ai_ranking_score >= 70 ? 'var(--hot)' : lead.ai_ranking_score >= 45 ? 'var(--warm)' : 'var(--cold)'}">${lead.ai_ranking_score}/100</div></div>
            <div class="detail-item"><label>Verdict</label><div class="value"><span class="verdict-badge ${ai.verdict || 'WARM'}" style="font-size:14px">${ai.verdict || 'N/A'}</span></div></div>
            <div class="detail-item"><label>Phone</label><div class="value">${lead.phone ? `<a href="tel:${lead.phone}">${lead.phone}</a>` : 'Not found'}</div></div>
            <div class="detail-item"><label>Rating</label><div class="value">${lead.rating ? `⭐ ${lead.rating} (${lead.review_count} reviews)` : 'N/A'}</div></div>
            <div class="detail-item"><label>Website</label><div class="value">${websiteInfo}</div></div>
            <div class="detail-item"><label>Website Score</label><div class="value">${webScore}</div></div>
            <div class="detail-item" style="grid-column:1/-1"><label>Google Business Listing</label><div class="value">${mapsLink} &nbsp;|&nbsp; <a href="https://www.google.com/search?q=${encodeURIComponent((lead.business_name || '') + ' ' + (lead.address || ''))}" target="_blank">🔍 View on Google Search</a></div></div>
            <div class="detail-item" style="grid-column:1/-1"><label>Address</label><div class="value">${lead.address || 'N/A'}</div></div>
            <div class="detail-item"><label>Business Size</label><div class="value">${lead.business_size || 'Unknown'}</div></div>
            <div class="detail-item"><label>Worth Contacting</label><div class="value">${lead.worth_contacting ? '✅ Yes' : '❌ No'}</div></div>
        </div>
        ${ai.pitch ? `<div class="detail-item" style="margin-bottom:16px"><label>💡 Pitch Angle</label><div class="value">${ai.pitch}</div></div>` : ''}
        ${wa.verdict ? `<div style="padding:12px;border-radius:8px;background:rgba(255,255,255,0.05);margin-bottom:16px;font-weight:600">${wa.verdict}</div>` : ''}
        ${reportBullets ? `
            <h4 style="margin-bottom:8px;color:var(--accent)">📋 Website Report</h4>
            <ul style="list-style:none;padding:0;margin-bottom:16px;font-size:13px;line-height:1.6">${reportBullets}</ul>
        ` : ''}
        ${recBullets ? `
            <h4 style="margin-bottom:8px;color:var(--success)">🔧 What You Can Improve For Them</h4>
            <ul style="list-style:none;padding:0;margin-bottom:16px;font-size:13px;line-height:1.6">${recBullets}</ul>
        ` : ''}
        ${!reportBullets && !lead.website ? `
            <div style="padding:16px;border-radius:8px;background:rgba(255,107,107,0.1);border:1px solid rgba(255,107,107,0.3);margin-bottom:16px">
                <h4 style="color:var(--hot);margin-bottom:8px">🔥 NO WEBSITE — Best Lead Type</h4>
                <ul style="list-style:none;padding:0;font-size:13px">
                    <li>• They have NO online presence at all</li>
                    <li>• ${lead.review_count || 0} Google reviews proves they have students</li>
                    <li>• Competitors with websites are stealing their students</li>
                    <li>• Pitch: "You have ${lead.review_count || 0} reviews but no website — students searching online go to your competitor"</li>
                </ul>
            </div>
        ` : ''}`;

    modal.style.display = 'flex';
    modal.classList.add('active');
}

function closeModal() {
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.remove('active');
    overlay.style.display = 'none';
    callingSearchId = null;
    callingLead = null;
}

// ─── History ─────────────────────────────────
async function deleteSearch(searchId, e) {
    e.stopPropagation();
    if (!confirm('Delete this search and all its leads?')) return;
    await fetch(`/api/search/${searchId}`, { method: 'DELETE' });
    location.reload();
}

function exportCSV(searchId, e) {
    if (e) e.stopPropagation();
    if (!searchId) return alert('No search selected. Click a search from history first.');
    window.open(`/api/export/${searchId}`, '_blank');
}

async function resumeSearch(searchId, e) {
    if (e) e.stopPropagation();
    showProgress();
    try {
        const resp = await fetch(`/api/search/${searchId}/resume`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentSearchId = searchId;
        document.getElementById('progressMessage').textContent =
            `Resuming — ${data.saved_leads} leads found, processing...`;
        pollProgress(searchId);
    } catch (err) {
        alert('Resume failed: ' + err.message);
        hideProgress();
    }
}

async function retryFailed(searchId, e) {
    if (e) e.stopPropagation();
    showProgress();
    try {
        const resp = await fetch(`/api/retry-failed/${searchId}`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentSearchId = searchId;
        document.getElementById('progressMessage').textContent =
            `🔄 Retrying ${data.failed_count} failed URLs...`;
        pollProgress(searchId);
    } catch (err) {
        alert('Retry failed: ' + err.message);
        hideProgress();
    }
}

async function rescanSearch(searchId, e) {
    if (e) e.stopPropagation();
    showProgress();
    try {
        const resp = await fetch(`/api/search/${searchId}/rescan`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentSearchId = searchId;
        document.getElementById('progressMessage').textContent =
            `🔍 Re-scanning — skipping ${data.existing} already known businesses...`;
        pollProgress(searchId);
    } catch (err) {
        alert('Re-scan failed: ' + err.message);
        hideProgress();
    }
}

// ─── Calling CRM ─────────────────────────────
let callingSearchId = null;
let callingLead = null;
let callingStep = 0; // 0=phone, 1=details, 2=categorize

async function startCalling(searchId) {
    callingSearchId = searchId;
    callingStep = 0;
    const overlay = document.getElementById('modalOverlay');
    overlay.style.display = 'flex';
    overlay.classList.add('active');
    await loadNextCall();
}

async function loadNextCall() {
    const resp = await fetch(`/api/search/${callingSearchId}/next-call`);
    const data = await resp.json();

    if (data.done) {
        document.getElementById('modalContent').innerHTML = `
            <div style="text-align:center;padding:40px">
                <div style="font-size:48px;margin-bottom:16px">🎉</div>
                <h2 style="color:var(--accent)">All Done!</h2>
                <p>You've called every lead in this search.</p>
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:24px">
                    <div style="padding:16px;background:rgba(255,59,48,0.15);border-radius:12px">
                        <div style="font-size:24px;font-weight:700;color:#ff3b30">${data.stats.hot}</div><div>🔥 Hot</div>
                    </div>
                    <div style="padding:16px;background:rgba(255,149,0,0.15);border-radius:12px">
                        <div style="font-size:24px;font-weight:700;color:#ff9500">${data.stats.not_picked}</div><div>📵 Not Picked</div>
                    </div>
                    <div style="padding:16px;background:rgba(88,86,214,0.15);border-radius:12px">
                        <div style="font-size:24px;font-weight:700;color:#5856d6">${data.stats.transferred}</div><div>↗️ Transferred</div>
                    </div>
                    <div style="padding:16px;background:rgba(142,142,147,0.15);border-radius:12px">
                        <div style="font-size:24px;font-weight:700;color:#8e8e93">${data.stats.not_happening}</div><div>❌ Nope</div>
                    </div>
                </div>
                <button class="btn btn-secondary" onclick="closeModal()" style="margin-top:24px">Close</button>
            </div>`;
        return;
    }

    callingLead = data.lead;
    const wa = data.website_report || {};
    const mapsUrl = data.maps_url || '';
    const stats = data.stats;
    callingStep = 0;
    renderCallingStep(wa, mapsUrl, stats);
}

function renderCallingStep(wa, mapsUrl, stats) {
    const lead = callingLead;
    const statsBar = `<div style="display:flex;gap:16px;padding:12px 16px;background:rgba(255,255,255,0.03);border-radius:10px;margin-bottom:20px;font-size:13px">
        <span>📞 ${stats.pending} left</span>
        <span>🔥 ${stats.hot} hot</span>
        <span>📵 ${stats.not_picked} no pick</span>
        <span>↗️ ${stats.transferred} transferred</span>
        <span>❌ ${stats.not_happening} nope</span>
    </div>`;

    if (callingStep === 0) {
        // Step 1: Phone number
        document.getElementById('modalContent').innerHTML = `
            ${statsBar}
            <div style="text-align:center;padding:30px 0">
                <div style="font-size:14px;color:rgba(255,255,255,0.5);margin-bottom:8px">CALLING LEAD #${lead.id} · Score: ${lead.ai_ranking_score}/100</div>
                <h2 style="font-size:28px;margin-bottom:24px">${lead.business_name || 'Unknown'}</h2>
                <div style="font-size:42px;font-weight:700;color:var(--accent);margin-bottom:8px">
                    ${lead.phone ? `<a href="tel:${lead.phone}" style="color:var(--accent);text-decoration:none">${lead.phone}</a>` : 'No Phone ❌'}
                </div>
                <div style="font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:32px">${lead.category || ''} · ${lead.address || ''}</div>
                <button class="btn btn-primary" onclick="callingStep=1;renderCallingStep(${JSON.stringify(wa).replace(/"/g,'&quot;')},${JSON.stringify(mapsUrl).replace(/"/g,'&quot;')},${JSON.stringify(stats).replace(/"/g,'&quot;')})" style="font-size:16px;padding:12px 40px">
                    Continue →
                </button>
                <button class="btn btn-secondary" onclick="closeModal()" style="margin-left:12px">Exit</button>
            </div>`;
    } else if (callingStep === 1) {
        // Step 2: Business details
        const websiteInfo = lead.website
            ? `<a href="${lead.website}" target="_blank" style="color:var(--accent)">${lead.website}</a>`
            : '<span style="color:#34c759">No Website — OPPORTUNITY!</span>';
        const reportBullets = (wa.detailed_report || []).map(r => `<li style="margin-bottom:4px">${r}</li>`).join('');
        const recBullets = (wa.recommendations || []).map(r => `<li style="margin-bottom:4px;color:var(--accent)">${r}</li>`).join('');

        document.getElementById('modalContent').innerHTML = `
            ${statsBar}
            <h3 style="margin-bottom:16px">${lead.business_name}</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
                <div><strong>Category:</strong> ${lead.category || 'N/A'}</div>
                <div><strong>Rating:</strong> ${lead.rating ? `⭐ ${lead.rating} (${lead.review_count} reviews)` : 'N/A'}</div>
                <div><strong>Website:</strong> ${websiteInfo}</div>
                <div><strong>Score:</strong> ${lead.website_score >= 0 ? lead.website_score + '/100' : 'N/A'}</div>
            </div>
            ${wa.verdict ? `<div style="padding:10px;border-radius:8px;background:rgba(255,255,255,0.05);margin-bottom:12px;font-weight:600">${wa.verdict}</div>` : ''}
            ${reportBullets ? `<div style="margin-bottom:12px"><strong>📊 Website Report:</strong><ul style="margin:8px 0;padding-left:20px">${reportBullets}</ul></div>` : ''}
            ${recBullets ? `<div style="margin-bottom:16px"><strong>🔧 What You Can Improve:</strong><ul style="margin:8px 0;padding-left:20px">${recBullets}</ul></div>` : ''}
            <div style="display:flex;gap:10px;margin-bottom:12px">
                ${mapsUrl ? `<a href="${mapsUrl}" target="_blank" class="btn btn-secondary btn-sm">📍 Google Maps</a>` : ''}
                <a href="https://www.google.com/search?q=${encodeURIComponent((lead.business_name||'')+' '+(lead.address||''))}" target="_blank" class="btn btn-secondary btn-sm">🔍 Google Search</a>
            </div>
            <button class="btn btn-primary" onclick="callingStep=2;renderCallingStep(${JSON.stringify(wa).replace(/"/g,'&quot;')},${JSON.stringify(mapsUrl).replace(/"/g,'&quot;')},${JSON.stringify(stats).replace(/"/g,'&quot;')})" style="font-size:16px;padding:10px 36px">
                Continue → Categorize
            </button>`;
    } else if (callingStep === 2) {
        // Step 3: Categorize
        document.getElementById('modalContent').innerHTML = `
            ${statsBar}
            <h3 style="margin-bottom:8px">${lead.business_name}</h3>
            <p style="color:rgba(255,255,255,0.5);margin-bottom:20px">${lead.phone || 'No phone'} · ${lead.category || ''}</p>
            <div style="margin-bottom:20px">
                <label style="font-size:13px;color:rgba(255,255,255,0.6)">Notes (optional)</label>
                <textarea id="callNotes" rows="2" style="width:100%;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:8px;color:white;padding:10px;margin-top:6px;resize:none" placeholder="e.g. Spoke to owner, interested in website redesign..."></textarea>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <button onclick="categorizeCall('hot')" style="padding:16px;border-radius:12px;border:none;cursor:pointer;font-size:15px;font-weight:600;background:rgba(255,59,48,0.2);color:#ff3b30">🔥 Hot Lead</button>
                <button onclick="categorizeCall('call_later')" style="padding:16px;border-radius:12px;border:none;cursor:pointer;font-size:15px;font-weight:600;background:rgba(50,215,75,0.2);color:#32d74b">🕐 Call Later</button>
                <button onclick="categorizeCall('not_picked')" style="padding:16px;border-radius:12px;border:none;cursor:pointer;font-size:15px;font-weight:600;background:rgba(255,149,0,0.2);color:#ff9500">📵 Not Picked</button>
                <button onclick="categorizeCall('transferred')" style="padding:16px;border-radius:12px;border:none;cursor:pointer;font-size:15px;font-weight:600;background:rgba(88,86,214,0.2);color:#5856d6">↗️ Transferred</button>
                <button onclick="categorizeCall('not_happening')" style="padding:16px;border-radius:12px;border:none;cursor:pointer;font-size:15px;font-weight:600;background:rgba(142,142,147,0.2);color:#8e8e93;grid-column:1/-1">❌ Not Happening</button>
            </div>`;
    }
}

async function categorizeCall(status) {
    const notes = document.getElementById('callNotes')?.value || '';
    await fetch(`/api/lead/${callingLead.id}/call-status`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status, notes }),
    });
    await loadNextCall();
}

// ─── Init ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('searchForm').addEventListener('submit', startSearch);
    document.getElementById('modalOverlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
});
