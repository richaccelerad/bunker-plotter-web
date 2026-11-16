"""
Processing-progress analysis across several bunker log files.

Each uploaded file is one *session*. Within each session the beam-on time
(cathode current above a threshold) is split into *dwells*: stretches where
the operating settings stay constant. A dwell starts at a snap-on or at a
setting change (a "step") while the beam stays on.

For every dwell we measure the gas level (ion pump current) two ways:
  * transient: X seconds after the dwell started
  * steady state: median of the last third of a long dwell, if gas has
    levelled off

Progress is then judged two ways:
  1. Lower gas at the same settings (dwells grouped into matching conditions)
  2. Further at the same gas: higher beam duty or klystron power reached
     while gas stays at or below a given level (the operating envelope)

Cathode current is checked for drops at matching settings, and within runs.
All statistics are medians or similar, because ion pump readings contain
large glitches.
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

GAS_COLUMNS = ['Guide Iip (uA)', 'Gun Iip (uA)', 'Scan Iip (uA)']

DEFAULT_OPTIONS = {
    'gas_columns': ['Guide Iip (uA)'],
    'on_threshold': 0.1,          # Icath (A) above which the beam counts as on
    'transient_seconds': 30,      # gas is read this long after snap-on / step
    'gas_limit': None,            # optional user gas level (uA) for the envelope
    'match': [
        # col, enabled, tolerance, relative (tolerance in % of value)
        {'col': 'Hz', 'enabled': True, 'tol': 5, 'relative': True},
        {'col': 'GunHV (kV)', 'enabled': True, 'tol': 0.5, 'relative': False},
        {'col': 'Gun PW (us)', 'enabled': True, 'tol': 0.5, 'relative': False},
        {'col': 'Dac2', 'enabled': True, 'tol': 0.05, 'relative': False},
        {'col': 'CCPS', 'enabled': True, 'tol': 10, 'relative': False},
        {'col': 'RFDriver (W)', 'enabled': True, 'tol': 2, 'relative': False},
        {'col': 'GunVfil (v)', 'enabled': False, 'tol': 0.2, 'relative': False},
    ],
}

STEADY_MIN_SECONDS = 120     # dwell must be this long to judge steady state
STEADY_MAX_CHANGE = 0.10     # gas may change at most this much over the last third
BASELINE_SECONDS = 60        # beam-off window before snap-on for baseline gas
IMPROVE_RATIO = 0.10         # >10% change counts as a real change
ICATH_WARN = 0.05            # >5% Icath drop -> warning
ICATH_TROUBLE = 0.10         # >10% Icath drop -> trouble
ICATH_RUN_MIN_SECONDS = 60   # dwell length needed to judge an in-run Icath drop
MAX_CONDITION_CHARTS = 8

SESSION_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

LABELS = {
    'Hz': ('Hz', '{:.0f}'),
    'GunHV (kV)': ('kV', '{:.1f}'),
    'Gun PW (us)': ('µs', '{:.1f}'),
    'Dac2': ('DAC', '{:.2f}'),
    'CCPS': ('CCPS', '{:.0f}'),
    'RFDriver (W)': ('W drv', '{:.1f}'),
    'GunVfil (v)': ('V fil', '{:.2f}'),
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _clean(v):
    """Make a value JSON-safe (NaN/inf -> None, numpy -> python)."""
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        v = float(v)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _fmt_gas(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '–'
    if v >= 100:
        return f'{v:.0f}'
    if v >= 10:
        return f'{v:.1f}'
    return f'{v:.2f}'


def _within(a, b, spec):
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) \
            or (isinstance(b, float) and math.isnan(b)):
        return True  # missing data never splits / separates
    tol = spec['tol']
    if spec.get('relative'):
        tol = abs(b) * tol / 100.0
    return abs(a - b) <= tol


def _pct(a, b):
    """Percent change from a to b."""
    if a is None or b is None or a == 0:
        return None
    return (b - a) / abs(a) * 100.0


# ----------------------------------------------------------------------------
# Step 1: load
# ----------------------------------------------------------------------------

def build_sessions(frames):
    """frames: list of (name, DataFrame from load_and_parse_csv).

    Returns (combined DataFrame with a 'session' column, list of session info),
    sessions ordered by start time.
    """
    frames = [(n, d) for n, d in frames if len(d)]
    frames.sort(key=lambda nd: nd[1].index[0])
    infos = []
    parts = []
    for i, (name, df) in enumerate(frames):
        df = df.sort_index().copy()
        df['session'] = i
        dt = df.index.to_series().diff().dt.total_seconds()
        infos.append({
            'index': i,
            'name': name,
            'start': df.index[0].strftime('%Y-%m-%d %H:%M'),
            'end': df.index[-1].strftime('%Y-%m-%d %H:%M'),
            'rows': int(len(df)),
            'sample_seconds': _clean(dt.median()),
            'color': SESSION_COLORS[i % len(SESSION_COLORS)],
        })
        parts.append(df)
    return pd.concat(parts), infos


def choose_power(df, on):
    """Klystron power measure: KlyI x KlyV when logged, else CCPS."""
    if 'Ikly (A)' in df and 'Ekly (kV)' in df:
        kw = df['Ikly (A)'] * df['Ekly (kV)']
        # Every session must have real klystron readings while beam is on.
        per_session = kw[on].groupby(df.loc[on, 'session']).median()
        if len(per_session) == df['session'].nunique() and (per_session > 1).all():
            return kw, 'Klystron power (kV·A)'
    if 'CCPS' in df:
        return df['CCPS'], 'CCPS'
    return None, None


# ----------------------------------------------------------------------------
# Step 2: dwells
# ----------------------------------------------------------------------------

def find_dwells(df, opts, match_specs):
    """Split beam-on time into constant-settings dwells.

    Returns a list of dicts with start/end row positions (in df) and kind.
    """
    thr = opts['on_threshold']
    dwells = []
    for sess, sdf in df.groupby('session', sort=True):
        times = sdf.index.to_numpy()
        icath = sdf['Icath (A)'].to_numpy()
        on = icath > thr
        dt = np.diff(times).astype('timedelta64[ms]').astype(float) / 1000.0
        med_dt = float(np.median(dt)) if len(dt) else 6.0
        gap_limit = max(3 * med_dt, 30.0)
        settings = {s['col']: sdf[s['col']].to_numpy() for s in match_specs}

        start = None
        kind = None
        ref = None
        pending = 0
        n = len(sdf)
        for i in range(n + 1):
            ends_here = (
                i == n or not on[i] or
                (start is not None and i > 0 and dt[i - 1] > gap_limit)
            )
            if start is not None and ends_here:
                dwells.append({'session': sess, 'i0': start, 'i1': i - 1 - pending,
                               'kind': kind})
                # samples held as "pending change" belong to no dwell if the
                # beam turned off; that's at most one sample.
                start = None
            if i == n:
                break
            if not on[i]:
                pending = 0
                continue
            if start is None:
                start, kind, pending = i, 'snap-on', 0
                ref = {c: settings[c][i] for c in settings}
                continue
            # Beam still on: has a setting changed (for 2 samples in a row)?
            changed = any(not _within(settings[s['col']][i], ref[s['col']], s)
                          for s in match_specs)
            if changed:
                pending += 1
                if pending >= 2:
                    new_start = i - 1
                    dwells.append({'session': sess, 'i0': start, 'i1': new_start - 1,
                                   'kind': kind})
                    start, kind, pending = new_start, 'step', 0
                    ref = {c: settings[c][i] for c in settings}
            else:
                pending = 0
        for d in dwells:
            if d['session'] == sess and 'sdf' not in d:
                d['sdf'] = sdf
                d['med_dt'] = med_dt
    return [d for d in dwells if d['i1'] - d['i0'] + 1 >= 2]


def measure_dwell(d, opts, gas_cols, match_specs, power_col):
    sdf = d['sdf']
    seg = sdf.iloc[d['i0']:d['i1'] + 1]
    t0 = seg.index[0]
    t1 = seg.index[-1]
    duration = (t1 - t0).total_seconds() + d['med_dt']
    elapsed = (seg.index - t0).total_seconds().to_numpy()

    row = {
        'session': d['session'],
        'kind': d['kind'],
        'start': t0,
        'start_str': t0.strftime('%Y-%m-%d %H:%M:%S'),
        'duration': duration,
        'samples': len(seg),
    }
    for s in match_specs:
        row[s['col']] = seg[s['col']].median()
    for col in ('Hz', 'GunHV (kV)', 'Dac2', 'CCPS', 'GunVfil (v)', 'KLY FWD'):
        if col in seg and col not in row:
            row[col] = seg[col].median()
    row['duty'] = seg['duty_gun'].median() * 100 if 'duty_gun' in seg else None
    row['power'] = seg[power_col].median() if power_col else None

    # Cathode current at start and end of the dwell (first / last 20%).
    ic = seg['Icath (A)'].to_numpy()
    k = max(2, len(ic) // 5)
    row['icath'] = float(np.median(ic))
    # Average beam (cathode) current in mA = duty x peak current.
    row['avg_ma'] = (row['duty'] / 100.0 * row['icath'] * 1000.0
                     if row['duty'] is not None else None)
    row['icath_start'] = float(np.median(ic[:k]))
    row['icath_end'] = float(np.median(ic[-k:]))
    row['icath_run_drop'] = (
        duration >= ICATH_RUN_MIN_SECONDS and
        row['icath_end'] < row['icath_start'] * (1 - ICATH_WARN)
    )

    X = opts['transient_seconds']
    x_tol = max(6.0, X / 2.0)
    for g in gas_cols:
        vals = seg[g].to_numpy()
        # Transient: sample nearest X s after the dwell started.
        at_x = None
        if len(vals):
            j = int(np.argmin(np.abs(elapsed - X)))
            if abs(elapsed[j] - X) <= x_tol:
                at_x = float(vals[j])
        # Steady state: last third, if long enough and levelled off.
        steady = None
        if duration >= STEADY_MIN_SECONDS and len(vals) >= 6:
            last = vals[len(vals) * 2 // 3:]
            h = len(last) // 2
            m1, m2 = np.median(last[:h]), np.median(last[h:])
            if m1 > 0 and abs(m2 - m1) / m1 < STEADY_MAX_CHANGE:
                steady = float(np.median(last))
        # Baseline: beam-off gas in the minute before a snap-on.
        baseline = None
        if d['kind'] == 'snap-on':
            before = sdf.loc[(sdf.index < t0) &
                             (sdf.index >= t0 - pd.Timedelta(seconds=BASELINE_SECONDS))]
            before = before[before['Icath (A)'] <= opts['on_threshold']]
            if len(before):
                baseline = float(before[g].median())
        # Peak: the gas level the dwell stayed under (90th percentile, so a
        # single glitch doesn't count). Only for dwells lasting at least X s,
        # so a brief excursion isn't mistaken for sustained operation.
        peak = None
        if duration >= X and len(vals) >= 2:
            peak = float(np.quantile(vals, 0.9))
        row[f'{g}|at_x'] = at_x
        row[f'{g}|steady'] = steady
        row[f'{g}|baseline'] = baseline
        row[f'{g}|peak'] = peak
        if steady is not None:
            row[f'{g}|rep'], row[f'{g}|rep_kind'] = steady, 'steady'
        else:
            row[f'{g}|rep'], row[f'{g}|rep_kind'] = at_x, ('transient' if at_x is not None else None)
    return row


# ----------------------------------------------------------------------------
# Step 3: conditions (matching settings)
# ----------------------------------------------------------------------------

def assign_conditions(dw, match_specs):
    refs = []
    cond = []
    for _, r in dw.iterrows():
        found = None
        for ci, ref in enumerate(refs):
            if all(_within(r[s['col']], ref[s['col']], s) for s in match_specs):
                found = ci
                break
        if found is None:
            refs.append({s['col']: r[s['col']] for s in match_specs})
            found = len(refs) - 1
        cond.append(found)
    dw['condition'] = cond
    labels = []
    for ref in refs:
        parts = []
        for s in match_specs:
            v = ref[s['col']]
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            unit, fmt = LABELS.get(s['col'], (s['col'], '{:.2f}'))
            parts.append(f"{fmt.format(v)} {unit}")
        labels.append(' · '.join(parts))
    return labels


def compare_conditions(dw, labels, gas_cols, sessions):
    out = []
    for ci, label in enumerate(labels):
        sub = dw[dw['condition'] == ci]
        if sub['session'].nunique() < 2:
            continue
        entry = {'condition': ci, 'label': label, 'dwells': int(len(sub)),
                 'sessions': int(sub['session'].nunique()), 'gas': {}}
        for g in gas_cols:
            # Prefer steady-state if at least two sessions have it, else
            # transient (X s after start), so like is compared with like.
            metric = None
            for m in ('steady', 'at_x'):
                col = f'{g}|{m}'
                if sub.dropna(subset=[col])['session'].nunique() >= 2:
                    metric = m
                    break
            if metric is None:
                entry['gas'][g] = None
                continue
            col = f'{g}|{metric}'
            ok = sub.dropna(subset=[col])
            per = ok.groupby('session')[col].agg(['median', 'size'])
            first, last = per.iloc[0], per.iloc[-1]
            change = _pct(first['median'], last['median'])
            verdict = 'flat'
            if change is not None:
                if change <= -IMPROVE_RATIO * 100:
                    verdict = 'better'
                elif change >= IMPROVE_RATIO * 100:
                    verdict = 'worse'
            entry['gas'][g] = {
                'metric': metric,
                'per_session': [
                    {'session': int(s), 'median': _clean(r['median']), 'n': int(r['size'])}
                    for s, r in per.iterrows()
                ],
                'first': _clean(first['median']),
                'last': _clean(last['median']),
                'change_pct': _clean(change),
                'verdict': verdict,
            }
        # Cathode current at these settings, per session.
        agg = dict(icath=('icath', 'median'), n=('icath', 'size'))
        if 'GunVfil (v)' in sub:
            agg['fil'] = ('GunVfil (v)', 'median')
        per_ic = sub.groupby('session').agg(**agg)
        ic_first, ic_last = per_ic['icath'].iloc[0], per_ic['icath'].iloc[-1]
        ic_change = _pct(ic_first, ic_last)
        ic_status = 'ok'
        if ic_change is not None and ic_change <= -ICATH_TROUBLE * 100:
            ic_status = 'trouble'
        elif ic_change is not None and ic_change <= -ICATH_WARN * 100:
            ic_status = 'warning'
        fil_note = None
        if 'GunVfil (v)' in sub:
            fils = per_ic['fil']
            if fils.max() - fils.min() > 0.1:
                fil_note = f'filament {fils.iloc[0]:.2f} → {fils.iloc[-1]:.2f} V'
        entry['icath'] = {
            'per_session': [{'session': int(s), 'median': _clean(r['icath']), 'n': int(r['n'])}
                            for s, r in per_ic.iterrows()],
            'first': _clean(ic_first), 'last': _clean(ic_last),
            'change_pct': _clean(ic_change), 'status': ic_status, 'filament_note': fil_note,
        }
        out.append(entry)
    out.sort(key=lambda e: (-e['sessions'], -e['dwells']))
    return out


# ----------------------------------------------------------------------------
# Step 4: envelope (how far at a given gas level)
# ----------------------------------------------------------------------------

def _envelope_value(q, col):
    """Highest value of `col` that is trustworthy: reached on one long dwell
    (at least STEADY_MIN_SECONDS) or on at least two dwells."""
    q = q.dropna(subset=[col])
    if not len(q):
        return None, None
    q = q.sort_values(col, ascending=False)
    best = None
    long_ = q[q['duration'] >= STEADY_MIN_SECONDS]
    if len(long_):
        best = long_.iloc[0]
    if len(q) >= 2:
        second = q.iloc[1]
        if best is None or second[col] > best[col]:
            best = second
    if best is None:
        return None, None
    return best[col], best


def gas_levels(values, user_limit):
    v = np.array([x for x in values if x is not None and x > 0])
    levels = []
    if len(v):
        lo, hi = np.quantile(v, 0.1), np.quantile(v, 0.9)
        for base in (0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000, 3000):
            if lo <= base <= hi:
                levels.append(base)
        if len(levels) > 4:
            # keep a spread of up to four levels
            idx = np.linspace(0, len(levels) - 1, 4).round().astype(int)
            levels = [levels[i] for i in sorted(set(idx))]
        if not levels:
            levels = [float(f'{np.median(v):.2g}')]
    if user_limit:
        levels = sorted(set(levels) | {float(user_limit)})
    return levels


ENVELOPE_CONTEXT = ('Hz', 'icath', 'GunHV (kV)', 'power', 'duration', 'start_str')


def envelope(dw, g, levels, sessions, power_label):
    """For each gas level G and session: the highest duty / beam current /
    power reached on dwells whose gas stayed at or below G throughout."""
    peak = f'{g}|peak'
    data = dw.dropna(subset=[peak])
    measures = [('duty', 'Beam duty (%)'), ('avg_ma', 'Avg beam current (mA)')]
    if power_label:
        measures.append(('power', power_label))
    if 'KLY FWD' in data and data['KLY FWD'].notna().any():
        measures.append(('KLY FWD', 'KLY FWD (backup)'))
    result = []
    for G in levels:
        q = data[data[peak] <= G]
        level = {'gas': G, 'measures': []}
        for col, label in measures:
            per = []
            for s in sessions:
                val, row = _envelope_value(q[q['session'] == s['index']], col)
                entry = {'session': s['index'], 'value': _clean(val)}
                for c in ENVELOPE_CONTEXT:
                    entry[c] = _clean(row[c]) if row is not None and c in row else None
                per.append(entry)
            vals = [p for p in per if p['value'] is not None]
            verdict = None
            change = None
            if len(vals) >= 2:
                change = _pct(vals[0]['value'], vals[-1]['value'])
                if change is not None:
                    verdict = 'further' if change > 2 else ('less' if change < -2 else 'same')
            level['measures'].append({'col': col, 'label': label, 'per_session': per,
                                      'change_pct': _clean(change), 'verdict': verdict})
        result.append(level)
    return result


# ----------------------------------------------------------------------------
# Charts (plotly figures as JSON-able dicts)
# ----------------------------------------------------------------------------

def _scatter_by_session(dw, sessions, x, y, x_title, y_title, log_y=True, hover_cols=()):
    fig = go.Figure()
    for s in sessions:
        sub = dw[(dw['session'] == s['index'])].dropna(subset=[x, y])
        if not len(sub):
            continue
        custom = np.column_stack([sub['start_str']] + [sub[c].round(3).astype(str) for c in hover_cols]) \
            if len(sub) else None
        hover = '%{customdata[0]}<br>' + x_title + ': %{x}<br>' + y_title + ': %{y}'
        for k, c in enumerate(hover_cols, start=1):
            hover += f'<br>{c}: %{{customdata[{k}]}}'
        steady = (sub['_kind'] == 'steady').to_numpy() if '_kind' in sub else None
        fig.add_trace(go.Scatter(
            x=sub[x].to_numpy(), y=sub[y].to_numpy(), mode='markers',
            name=s['name'],
            marker=dict(color=s['color'], size=7, opacity=0.75,
                        symbol=np.where(steady, 'circle', 'circle-open').tolist()
                        if steady is not None else 'circle'),
            customdata=custom, hovertemplate=hover + '<extra>' + s['name'] + '</extra>',
        ))
    fig.update_layout(
        template='plotly_white', height=380, margin=dict(l=60, r=20, t=30, b=50),
        xaxis_title=x_title, yaxis_title=y_title,
        legend=dict(orientation='h', y=1.12),
    )
    if log_y:
        fig.update_yaxes(type='log')
    return fig


def build_charts(dw, sessions, gas_cols, power_label, conditions):
    charts = []
    for g in gas_cols:
        d = dw.copy()
        d['_kind'] = np.where(d['duration'] >= STEADY_MIN_SECONDS, 'steady', 'short')
        gname = g.replace(' (uA)', '')
        note = ('One point per dwell: the gas level it stayed under (90th percentile). '
                'Filled = dwell of 2 min or more, open = shorter. '
                'Progress moves points down or to the right.')
        for x, title in (('duty', 'Beam duty (%)'), ('avg_ma', 'Avg beam current (mA)'),
                         ('power', power_label)):
            if not title:
                continue
            charts.append({
                'title': f'{gname} gas vs {title}',
                'note': note,
                'figure': _scatter_by_session(d, sessions, x, f'{g}|peak', title,
                                              f'{gname} (µA)',
                                              hover_cols=('Hz', 'icath', 'CCPS', 'duration'))
                          .to_json(),
            })
    # Gas over time for each compared condition (first gas column).
    if gas_cols:
        g = gas_cols[0]
        gname = g.replace(' (uA)', '')
        for c in conditions[:MAX_CONDITION_CHARTS]:
            info = c['gas'].get(g)
            if not info:
                continue
            col = f"{g}|{info['metric']}"
            sub = dw[dw['condition'] == c['condition']].copy()
            sub['_kind'] = 'steady' if info['metric'] == 'steady' else 'transient'
            fig = _scatter_by_session(sub, sessions, 'start_str', col, 'Time', f'{gname} (µA)',
                                      hover_cols=('icath',))
            charts.append({
                'title': f"{gname} at {c['label']}",
                'note': ('Steady-state gas' if info['metric'] == 'steady'
                         else 'Gas X s after start') + ' for each dwell at these settings.',
                'figure': fig.to_json(),
            })
    # Cathode current over time.
    d = dw.copy()
    fig = _scatter_by_session(d, sessions, 'start_str', 'icath', 'Time', 'Icath (A)',
                              log_y=False, hover_cols=('GunHV (kV)', 'Dac2'))
    charts.append({'title': 'Cathode current per dwell',
                   'note': 'Compare at the same gun HV and DAC setting (in hover).',
                   'figure': fig.to_json()})
    return charts


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------

def merge_options(user):
    opts = {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULT_OPTIONS.items()}
    user = user or {}
    for k in ('gas_columns', 'on_threshold', 'transient_seconds', 'gas_limit', 'match'):
        if user.get(k) not in (None, ''):
            opts[k] = user[k]
    opts['on_threshold'] = float(opts['on_threshold'])
    opts['transient_seconds'] = float(opts['transient_seconds'])
    opts['gas_limit'] = float(opts['gas_limit']) if opts['gas_limit'] not in (None, '') else None
    return opts


def analyze(frames, user_options=None):
    """frames: list of (session name, DataFrame from load_and_parse_csv)."""
    opts = merge_options(user_options)
    notes = []
    if len(frames) < 2:
        notes.append('Only one file: trends need at least two sessions, so only '
                     'within-session results are shown.')

    df, sessions = build_sessions(frames)
    if 'Icath (A)' not in df:
        return {'error': 'No cathode current (Icath) column found.'}

    gas_cols = [g for g in opts['gas_columns'] if g in df]
    missing_gas = [g for g in opts['gas_columns'] if g not in df]
    if missing_gas:
        notes.append('Gas column(s) not found: ' + ', '.join(missing_gas))
    if not gas_cols:
        return {'error': 'None of the selected gas readings are in these files.'}

    match_specs = [s for s in opts['match'] if s.get('enabled') and s['col'] in df]
    for s in opts['match']:
        if s.get('enabled') and s['col'] not in df:
            notes.append(f"Matching setting {s['col']} not in files; ignored.")

    on = df['Icath (A)'] > opts['on_threshold']
    power, power_label = choose_power(df, on)
    power_col = None
    if power is not None:
        df['_power'] = power
        power_col = '_power'

    for s in sessions:
        if s['sample_seconds'] and s['sample_seconds'] > max(6.0, opts['transient_seconds'] / 2):
            notes.append(f"{s['name']}: logged every {s['sample_seconds']:.0f} s, too coarse "
                         f"for the {opts['transient_seconds']:.0f} s transient reading; "
                         'only steady-state values are used from it.')

    dwell_defs = find_dwells(df, opts, match_specs)
    if not dwell_defs:
        return {'error': f"No beam-on time found (Icath > {opts['on_threshold']} A)."}
    rows = [measure_dwell(d, opts, gas_cols, match_specs, power_col) for d in dwell_defs]
    dw = pd.DataFrame(rows)

    labels = assign_conditions(dw, match_specs)
    conditions = compare_conditions(dw, labels, gas_cols, sessions)

    env = {}
    for g in gas_cols:
        levels = gas_levels(dw[f'{g}|peak'].tolist(), opts['gas_limit'])
        env[g] = envelope(dw, g, levels, sessions, power_label)

    # Session summaries
    for s in sessions:
        sub = dw[dw['session'] == s['index']]
        s['snap_ons'] = int((sub['kind'] == 'snap-on').sum())
        s['dwells'] = int(len(sub))
        s['beam_on_minutes'] = _clean(sub['duration'].sum() / 60.0)
        s['icath_run_drops'] = int(sub['icath_run_drop'].sum())
        s['max_duty'] = _clean(sub['duty'].max())
        s['max_hz'] = _clean(sub['Hz'].max()) if 'Hz' in sub else None
        s['max_power'] = _clean(sub['power'].max()) if power_col else None

    summary = build_summary(conditions, env, sessions, gas_cols, power_label)
    charts = build_charts(dw, sessions, gas_cols, power_label, conditions)

    return {
        'options': opts,
        'sessions': sessions,
        'gas_columns': gas_cols,
        'power_label': power_label,
        'summary': summary,
        'conditions': conditions,
        'condition_count': len(labels),
        'envelope': env,
        'charts': charts,
        'notes': notes,
        'dwell_count': int(len(dw)),
    }


def build_summary(conditions, env, sessions, gas_cols, power_label):
    """Headline findings as (tone, text) items. tone: good / bad / warn / neutral."""
    items = []
    if len(sessions) < 2:
        return items
    first, last = sessions[0]['name'], sessions[-1]['name']
    for g in gas_cols:
        gname = g.replace(' (uA)', '')
        # 1. Same settings, lower gas?
        verdicts = [c['gas'][g] for c in conditions if c['gas'].get(g)]
        better = sum(v['verdict'] == 'better' for v in verdicts)
        worse = sum(v['verdict'] == 'worse' for v in verdicts)
        if verdicts:
            tone = 'good' if better > worse else ('bad' if worse > better else 'neutral')
            items.append({'tone': tone, 'text':
                f'{gname}: at matching settings, gas is lower in {better} and higher in '
                f'{worse} of {len(verdicts)} condition(s) seen in more than one session.'})
        else:
            items.append({'tone': 'neutral', 'text':
                f'{gname}: no settings were repeated across sessions, so gas at '
                'matching settings could not be compared.'})
        # 2. Further at the same gas?
        # One line per gas level: duty, average beam current and power,
        # each as a sequence across sessions (only sessions that qualified).
        for level in env.get(g, []):
            parts = []
            verdicts = []
            for m in level['measures']:
                if m['col'] == 'KLY FWD' or m['verdict'] is None:
                    continue
                ps = m['per_session']   # one entry per session, value may be None

                def seq(f):
                    return ' → '.join('–' if p['value'] is None else f(p) for p in ps)

                if m['col'] == 'duty':
                    if all(p['Hz'] for p in ps if p['value'] is not None):
                        parts.append('duty ' + seq(lambda p: f"{p['Hz']:.0f}") + ' Hz')
                    else:
                        parts.append('duty ' + seq(lambda p: f"{p['value']:.3f}%"))
                elif m['col'] == 'avg_ma':
                    parts.append('avg beam ' + seq(lambda p: f"{p['value']:.2f}") + ' mA')
                else:
                    parts.append(f'{power_label} ' + seq(lambda p: f"{p['value']:.0f}"))
                verdicts.append(m['verdict'])
            if not parts:
                continue
            if 'further' in verdicts and 'less' not in verdicts:
                tone = 'good'
            elif 'less' in verdicts and 'further' not in verdicts:
                tone = 'bad'
            else:
                tone = 'neutral'
            items.append({'tone': tone, 'text':
                f"{gname} ≤ {_fmt_gas(level['gas'])} µA, best reached by session: "
                + ' · '.join(parts) + '.'})
    # 3. Cathode
    bad = [c for c in conditions if c['icath']['status'] != 'ok']
    for c in bad:
        items.append({'tone': 'bad' if c['icath']['status'] == 'trouble' else 'warn', 'text':
            f"Cathode current fell {abs(c['icath']['change_pct']):.0f}% at {c['label']} "
            f"({c['icath']['first']:.3f} → {c['icath']['last']:.3f} A)"
            + (f"; note {c['icath']['filament_note']}" if c['icath']['filament_note'] else '') + '.'})
    drops = [(s['name'], s['icath_run_drops']) for s in sessions if s['icath_run_drops']]
    if drops:
        items.append({'tone': 'warn', 'text': 'Cathode current sagged during runs: ' +
                      ', '.join(f'{n}: {k}×' for n, k in drops) + '.'})
    if not bad and conditions:
        items.append({'tone': 'good', 'text':
            'Cathode current is holding steady at matching settings.'})
    return items
