(function () {
    var table = document.getElementById('decisions');
    if (!table) return;
    var body = table.tBodies[0];
    var tabs = document.querySelectorAll('.tab');
    var empty = document.getElementById('empty');
    var latestToggle = document.getElementById('filter-latest');
    var collator = new Intl.Collator('hu', { numeric: true, sensitivity: 'base' });
    var sortState = { col: -1, dir: 1 };
    var currentFilter = 'all';

    function updateView() {
        var onlyLatest = latestToggle ? latestToggle.checked : false;
        var visible = 0;
        var counts = { all: 0, go: 0, nogo: 0, undecided: 0, mismatch: 0 };

        Array.prototype.forEach.call(body.rows, function (row) {
            var isLatest = row.dataset.latest === '1';
            var status = row.dataset.status;
            var isMismatch = row.dataset.mismatch === '1';

            if (!onlyLatest || isLatest) {
                counts.all++;
                if (counts[status] !== undefined) {
                    counts[status]++;
                }
                if (isMismatch) {
                    counts.mismatch++;
                }
            }

            var matchFilter = currentFilter === 'all'
                || (currentFilter === 'mismatch' ? isMismatch : status === currentFilter);
            var matchLatest = !onlyLatest || isLatest;
            var show = matchFilter && matchLatest;

            row.hidden = !show;
            if (show) visible++;
        });

        tabs.forEach(function (tab) {
            var f = tab.dataset.filter;
            tab.classList.toggle('active', f === currentFilter);
            var badge = tab.querySelector('.count');
            if (badge && counts[f] !== undefined) {
                badge.textContent = counts[f];
            }
        });

        empty.hidden = visible > 0;

        var hash = '#' + currentFilter;
        var search = onlyLatest ? '?latest=1' : '';
        if (location.pathname) {
            history.replaceState(null, '', location.pathname + search + hash);
        }
    }

    function setFilter(filter) {
        var validFilters = ['all', 'go', 'nogo', 'undecided', 'mismatch'];
        currentFilter = validFilters.indexOf(filter) >= 0 ? filter : 'all';
        updateView();
    }

    function sortBy(col) {
        var th = table.tHead.rows[0].cells[col];
        sortState.dir = sortState.col === col ? -sortState.dir : 1;
        sortState.col = col;
        var numeric = th.dataset.sort === 'num';
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
            var x = a.cells[col].textContent.trim();
            var y = b.cells[col].textContent.trim();
            if (x === y) return 0;
            if (x === '') return 1;
            if (y === '') return -1;
            var result = numeric ? parseFloat(x) - parseFloat(y) : collator.compare(x, y);
            return result * sortState.dir;
        });
        rows.forEach(function (row) { body.appendChild(row); });
        Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell, i) {
            cell.classList.toggle('asc', i === col && sortState.dir === 1);
            cell.classList.toggle('desc', i === col && sortState.dir === -1);
        });
    }

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () { setFilter(tab.dataset.filter); });
    });

    if (latestToggle) {
        latestToggle.addEventListener('change', function () { updateView(); });
    }

    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
        th.addEventListener('click', function () { sortBy(i); });
        th.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(i); }
        });
    });

    window.addEventListener('hashchange', function () {
        var h = location.hash.slice(1);
        if (['all', 'go', 'nogo', 'undecided', 'mismatch'].indexOf(h) >= 0 && h !== currentFilter) {
            setFilter(h);
        }
    });

    var searchParams = new URLSearchParams(location.search);
    if (latestToggle && searchParams.get('latest') === '1') {
        latestToggle.checked = true;
    }
    var initial = location.hash.slice(1);
    setFilter(initial);
})();
