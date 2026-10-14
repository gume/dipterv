(function () {
    var table = document.getElementById('decisions');
    var body = table.tBodies[0];
    var tabs = document.querySelectorAll('.tab');
    var empty = document.getElementById('empty');
    var collator = new Intl.Collator('hu', { numeric: true, sensitivity: 'base' });
    var sortState = { col: -1, dir: 1 };

    function applyFilter(filter) {
        var visible = 0;
        Array.prototype.forEach.call(body.rows, function (row) {
            var show = filter === 'all' || row.dataset.status === filter;
            row.hidden = !show;
            if (show) visible++;
        });
        tabs.forEach(function (tab) { tab.classList.toggle('active', tab.dataset.filter === filter); });
        empty.hidden = visible > 0;
        history.replaceState(null, '', '#' + filter);
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
        tab.addEventListener('click', function () { applyFilter(tab.dataset.filter); });
    });
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
        th.addEventListener('click', function () { sortBy(i); });
        th.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(i); }
        });
    });

    var initial = location.hash.slice(1);
    applyFilter(['all', 'go', 'nogo', 'undecided'].indexOf(initial) >= 0 ? initial : 'all');
})();
