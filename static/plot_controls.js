// Interactive behaviour shared by the main page and the standalone /plot page.
// - Clicking a legend entry hides/shows just that trace; the subplot's y-axes
//   are then re-autoscaled so the remaining traces fill the plot.
// - Hidden traces are remembered (by trace name) in localStorage, so channels
//   that are turned off stay off for the next uploaded file.
(function() {
    var KEY = 'bunkerPlotter.hiddenTraces';

    function loadHidden() {
        try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
    }

    window.setupPlotControls = function(gd) {
        function saveHidden() {
            var hidden = gd.data.filter(function(t) { return t.visible === 'legendonly'; })
                                .map(function(t) { return t.name; });
            try { localStorage.setItem(KEY, JSON.stringify(hidden)); } catch (e) {}
        }

        function autorangeY(traceIdxs) {
            var upd = {};
            traceIdxs.forEach(function(i) {
                var ya = (gd.data[i].yaxis || 'y').replace('y', 'yaxis');
                upd[ya + '.autorange'] = true;
            });
            if (Object.keys(upd).length) Plotly.relayout(gd, upd);
        }

        gd.on('plotly_restyle', function(ev) {
            if (!ev || !ev[0] || !('visible' in ev[0])) return;
            saveHidden();
            // Re-fit every y-axis in the subplots that were touched.
            var touched = ev[1] || gd.data.map(function(_, i) { return i; });
            var groups = {};
            touched.forEach(function(i) { groups[gd.data[i].legendgroup] = true; });
            var related = [];
            gd.data.forEach(function(t, i) {
                // Only data traces have a legendgroup; skip the fixed comment row.
                if (t.legendgroup && groups[t.legendgroup]) related.push(i);
            });
            autorangeY(related);
        });

        // Restore previously hidden traces (the handler above re-fits the axes).
        var hidden = loadHidden();
        var idxs = [];
        gd.data.forEach(function(t, i) { if (hidden.indexOf(t.name) !== -1) idxs.push(i); });
        if (idxs.length) Plotly.restyle(gd, {visible: 'legendonly'}, idxs);
    };
})();
