// "Analyze Processing" tool: options panel, upload, and report rendering.
// Relies on loadPlotly(), showError(), and the loading / errorMessage /
// plotContainer elements defined by the page script in index.html.
(function() {
    const STORE_KEY = 'bunkerPlotter.analysisOptions';
    const GAS_CHOICES = ['Guide Iip (uA)', 'Gun Iip (uA)', 'Scan Iip (uA)'];
    const defaults = window.ANALYSIS_DEFAULTS;

    let files = [];

    const $ = id => document.getElementById(id);

    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function fmt(v, digits) {
        if (v === null || v === undefined || Number.isNaN(v)) return '–';
        return Number(v).toFixed(digits);
    }

    function fmtGas(v) {
        if (v === null || v === undefined) return '–';
        if (v >= 100) return v.toFixed(0);
        if (v >= 10) return v.toFixed(1);
        return v.toFixed(2);
    }

    // ---------------------------------------------------------------- options

    function loadOptions() {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(STORE_KEY)); } catch (e) {}
        const o = JSON.parse(JSON.stringify(defaults));
        if (saved) {
            ['gas_columns', 'on_threshold', 'transient_seconds', 'gas_limit'].forEach(k => {
                if (saved[k] !== undefined) o[k] = saved[k];
            });
            if (Array.isArray(saved.match)) {
                o.match.forEach(m => {
                    const s = saved.match.find(x => x.col === m.col);
                    if (s) { m.enabled = s.enabled; m.tol = s.tol; }
                });
            }
        }
        return o;
    }

    function saveOptions(o) {
        try { localStorage.setItem(STORE_KEY, JSON.stringify(o)); } catch (e) {}
    }

    function renderOptions() {
        const o = loadOptions();
        $('optGas').innerHTML = GAS_CHOICES.map(g => `
            <label class="opt-row"><input type="checkbox" value="${esc(g)}"
                ${o.gas_columns.includes(g) ? 'checked' : ''}> ${esc(g.replace(' (uA)', ''))}</label>
        `).join('');
        $('optThreshold').value = o.on_threshold;
        $('optTransient').value = o.transient_seconds;
        $('optGasLimit').value = o.gas_limit === null || o.gas_limit === undefined ? '' : o.gas_limit;
        $('optMatch').innerHTML = o.match.map((m, i) => `
            <tr>
              <td><label><input type="checkbox" data-i="${i}" class="m-on" ${m.enabled ? 'checked' : ''}>
                  ${esc(m.col)}</label></td>
              <td>± <input type="number" step="any" min="0" data-i="${i}" class="m-tol" value="${m.tol}">
                  ${m.relative ? '%' : ''}</td>
            </tr>`).join('');
    }

    function readOptions() {
        const o = JSON.parse(JSON.stringify(defaults));
        o.gas_columns = Array.from($('optGas').querySelectorAll('input:checked')).map(e => e.value);
        o.on_threshold = parseFloat($('optThreshold').value) || defaults.on_threshold;
        o.transient_seconds = parseFloat($('optTransient').value) || defaults.transient_seconds;
        const lim = parseFloat($('optGasLimit').value);
        o.gas_limit = Number.isFinite(lim) && lim > 0 ? lim : null;
        $('optMatch').querySelectorAll('.m-on').forEach(e => { o.match[+e.dataset.i].enabled = e.checked; });
        $('optMatch').querySelectorAll('.m-tol').forEach(e => {
            const v = parseFloat(e.value);
            if (Number.isFinite(v) && v >= 0) o.match[+e.dataset.i].tol = v;
        });
        return o;
    }

    // ---------------------------------------------------------------- flow

    function hide() {
        $('analysisPanel').style.display = 'none';
        hideReport();
    }

    function chooseFiles(list) {
        files = list.filter(f => f.name.toLowerCase().endsWith('.csv'));
        plotContainer.style.display = 'none';
        errorMessage.style.display = 'none';
        $('analysisReport').style.display = 'none';
        renderOptions();
        $('analysisFiles').innerHTML = `<b>${files.length} file(s):</b> ` +
            files.map(f => esc(f.name)).join(', ') +
            (files.length < 2 ? ' <i>(pick at least two to see progress between sessions)</i>' : '');
        $('analysisPanel').style.display = 'block';
    }

    function run() {
        if (!files.length) return;
        const o = readOptions();
        if (!o.gas_columns.length) { showError('Pick at least one gas reading.'); return; }
        saveOptions(o);
        errorMessage.style.display = 'none';
        hideReport();
        loading.style.display = 'block';

        const fd = new FormData();
        files.forEach(f => fd.append('files', f));
        fd.append('options', JSON.stringify(o));
        fetch('/analyze', { method: 'POST', body: fd })
            .then(r => r.json())
            .then(data => {
                loading.style.display = 'none';
                if (data.error) { showError(data.error); return; }
                renderReport(data);
            })
            .catch(err => {
                loading.style.display = 'none';
                showError('Analysis failed: ' + err);
            });
    }

    function hideReport() {
        const rep = $('analysisReport');
        if (window.Plotly) rep.querySelectorAll('.js-plotly-plot').forEach(d => Plotly.purge(d));
        rep.innerHTML = '';
        rep.style.display = 'none';
    }

    // ---------------------------------------------------------------- report

    function sessionCell(s) {
        return `<span class="swatch" style="background:${esc(s.color)}"></span>${esc(s.name)}`;
    }

    function badge(v) {
        if (!v) return '';
        const text = {better: 'lower gas', worse: 'higher gas', flat: 'no clear change',
                      further: 'further', less: 'less far', same: 'same',
                      ok: 'ok', warning: 'warning', trouble: 'trouble'}[v] || v;
        return `<span class="badge badge-${esc(v)}">${esc(text)}</span>`;
    }

    function renderSummary(d) {
        if (!d.summary.length) return '';
        return `<h2>Summary</h2><ul class="summary-list">` +
            d.summary.map(i => `<li class="tone-${esc(i.tone)}">${esc(i.text)}</li>`).join('') +
            `</ul>`;
    }

    function renderSessions(d) {
        const rows = d.sessions.map(s => `
            <tr>
              <td>${sessionCell(s)}</td>
              <td>${esc(s.start)} → ${esc(s.end)}</td>
              <td>${s.snap_ons}</td>
              <td>${s.dwells}</td>
              <td>${fmt(s.beam_on_minutes, 0)}</td>
              <td>${fmt(s.max_hz, 0)}</td>
              <td>${s.icath_run_drops ? `<span class="badge badge-warning">${s.icath_run_drops}</span>` : '0'}</td>
              <td>${fmt(s.sample_seconds, 0)} s</td>
            </tr>`).join('');
        return `<h2>Sessions</h2>
            <div class="report-table-wrap"><table class="data">
              <tr><th>Session</th><th>Span</th><th>Snap-ons</th><th>Dwells</th><th>Beam-on min</th>
                  <th>Max Hz</th><th>Icath sags in run</th><th>Log interval</th></tr>
              ${rows}
            </table></div>`;
    }

    function envelopeCell(m, p) {
        if (p.value === null) return '<td>–</td>';
        let main;
        if (m.col === 'duty') main = `${fmt(p.value, 3)}%`;
        else if (m.col === 'avg_ma') main = `${fmt(p.value, 2)} mA`;
        else if (m.col === 'KLY FWD') main = fmt(p.value, 2);
        else main = fmt(p.value, 0);
        const ctx = [];
        if (p.Hz !== null) ctx.push(`${fmt(p.Hz, 0)} Hz`);
        if (p.icath !== null) ctx.push(`${fmt(p.icath, 2)} A`);
        if (p['GunHV (kV)'] !== null) ctx.push(`${fmt(p['GunHV (kV)'], 1)} kV`);
        if (m.col !== 'power' && p.power !== null) ctx.push(`pwr ${fmt(p.power, 0)}`);
        if (p.duration !== null) ctx.push(`${fmt(p.duration / 60, 1)} min`);
        return `<td title="${esc(p.start_str || '')}">${main}<span class="sub">${esc(ctx.join(' · '))}</span></td>`;
    }

    function renderEnvelope(d) {
        let html = `<h2>How far at the same gas</h2>
            <p class="hint">Best reached in each session on dwells whose gas stayed at or below
            each level (90th percentile over the dwell, at least ${fmt(d.options.transient_seconds, 0)} s long,
            and either one dwell of 2+ min or two dwells). Higher is further. These only show what was
            attempted: a session that didn't push hard will look lower.</p>`;
        d.gas_columns.forEach(g => {
            const gname = g.replace(' (uA)', '');
            (d.envelope[g] || []).forEach(level => {
                const head = d.sessions.map(s => `<th>${sessionCell(s)}</th>`).join('');
                const rows = level.measures.map(m => `
                    <tr><th>${esc(m.label)}</th>
                        ${d.sessions.map(s => envelopeCell(m, m.per_session[s.index])).join('')}
                        <td>${badge(m.verdict)}</td></tr>`).join('');
                html += `<h3 style="margin-top:14px;font-size:1em">${esc(gname)} ≤ ${fmtGas(level.gas)} µA</h3>
                    <div class="report-table-wrap"><table class="data">
                      <tr><th></th>${head}<th>First → last</th></tr>${rows}
                    </table></div>`;
            });
        });
        return html;
    }

    function renderConditions(d) {
        if (!d.conditions.length) {
            return `<h2>Gas at matching settings</h2>
                <p class="hint">No group of settings was used in more than one session
                (${d.condition_count} different setting combinations found). Try loosening the
                tolerances or turning off settings that don't matter.</p>`;
        }
        let html = `<h2>Gas at matching settings</h2>
            <p class="hint">Dwells grouped by matching settings (${d.condition_count} combinations
            found; ${d.conditions.length} appear in more than one session). Gas is the steady-state
            value when available in at least two sessions, otherwise the reading
            ${fmt(d.options.transient_seconds, 0)} s after snap-on / step. Values are per-session medians (n = dwells).</p>`;
        const g0 = d.gas_columns;
        const rows = d.conditions.map(c => {
            const gasCells = g0.map(g => {
                const info = c.gas[g];
                if (!info) {
                    return `<td>–<span class="sub">no dwell long enough for a gas reading
                            in two sessions</span></td><td></td>`;
                }
                const seq = info.per_session.map(p =>
                    `<span style="color:${esc(d.sessions[p.session].color)}">${fmtGas(p.median)}</span> <small>(n=${p.n})</small>`
                ).join(' → ');
                const ps = info.per_session;
                const weak = ps[0].n < 2 || ps[ps.length - 1].n < 2;
                return `<td>${seq}<span class="sub">${info.metric === 'steady' ? 'steady state' : 'transient'}
                        · ${fmt(info.change_pct, 0)}%${weak ? ' · weak: only 1 dwell in a session' : ''}</span></td>
                        <td>${badge(info.verdict)}</td>`;
            }).join('');
            const ic = c.icath;
            const icSeq = ic.per_session.map(p =>
                `<span style="color:${esc(d.sessions[p.session].color)}">${fmt(p.median, 3)}</span>`).join(' → ');
            return `<tr><td>${esc(c.label)}<span class="sub">${c.sessions} sessions · ${c.dwells} dwells</span></td>
                    ${gasCells}
                    <td>${icSeq} A<span class="sub">${fmt(ic.change_pct, 1)}%${ic.filament_note ? ' · ' + esc(ic.filament_note) : ''}</span></td>
                    <td>${badge(ic.status)}</td></tr>`;
        }).join('');
        const gasHead = g0.map(g => `<th>${esc(g.replace(' (uA)', ''))} gas (µA)</th><th></th>`).join('');
        html += `<div class="report-table-wrap"><table class="data">
            <tr><th>Settings</th>${gasHead}<th>Cathode current</th><th></th></tr>${rows}</table></div>`;
        return html;
    }

    function renderNotes(d) {
        if (!d.notes.length) return '';
        return `<h2>Notes</h2><ul style="margin-left:20px">` +
            d.notes.map(n => `<li>${esc(n)}</li>`).join('') + `</ul>`;
    }

    function renderReport(d) {
        const rep = $('analysisReport');
        let html = `<div class="report">` +
            renderSummary(d) + renderSessions(d) + renderEnvelope(d) + renderConditions(d) +
            `<h2>Charts</h2>`;
        d.charts.forEach((c, i) => {
            html += `<div class="chart-block"><h3>${esc(c.title)}</h3>
                     <div class="hint">${esc(c.note)}</div><div id="anChart${i}"></div></div>`;
        });
        html += renderNotes(d) + `</div>`;
        rep.innerHTML = html;
        rep.style.display = 'block';

        loadPlotly(d.plotlyjs_version).then(() => {
            d.charts.forEach((c, i) => {
                const fig = typeof c.figure === 'string' ? JSON.parse(c.figure) : c.figure;
                Plotly.newPlot($('anChart' + i), fig.data, fig.layout, {responsive: true});
            });
        }).catch(err => showError('Could not draw charts: ' + err.message));
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('runAnalysis').addEventListener('click', run);
    });

    window.BunkerAnalysis = { chooseFiles: chooseFiles, hide: hide };
})();
