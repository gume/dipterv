var allDocs = [];
var filteredDocs = [];
var currentIdx = -1;
var filters = { go: true, nogo: true, undecided: true, last: false };
var loadedDoc = null;
var loadedReviewer = '';

function currentDoc() {
    return filteredDocs[currentIdx] || null;
}

function passesFilter(doc) {
    return (!filters.last || doc.is_last) && filters[doc.verdict] !== false;
}

function commitNotes() {
    var notes = document.getElementById('notes');
    if (!loadedDoc || !loadedReviewer) return;
    var stored = loadedDoc.remarks[loadedReviewer] || '';
    if (notes.value.trim() !== stored) {
        Dipterv.saveRemark(loadedDoc, loadedReviewer, notes.value).done(updateHistory);
    }
}

function updateHistory() {
    var doc = currentDoc();
    var lines = [];
    if (doc) {
        allDocs.filter(function (d) {
            return d.neptun_code === doc.neptun_code && d.version <= doc.version;
        }).sort(function (a, b) { return a.version - b.version; }).forEach(function (d) {
            var block = Dipterv.state.reviewers.filter(function (r) { return d.remarks[r.id]; }).map(function (r) {
                return r.name + ': ' + d.remarks[r.id];
            });
            if (block.length) {
                if (lines.length) lines.push('');
                lines.push('--- v' + d.version + ' ---');
                Array.prototype.push.apply(lines, block);
            }
        });
    }
    document.getElementById('reviews-summary').value = lines.join('\n');
}

function renderVerdict() {
    var doc = currentDoc();
    document.getElementById('verdict').innerHTML = doc ? Dipterv.verdictButtons(doc) : '';
}

function loadNotes() {
    var doc = currentDoc();
    var notes = document.getElementById('notes');
    loadedDoc = doc;
    loadedReviewer = Dipterv.state.reviewer;
    notes.value = doc && loadedReviewer ? (doc.remarks[loadedReviewer] || '') : '';
    notes.disabled = !loadedReviewer;
    notes.placeholder = loadedReviewer ? 'Write your review notes here.' : 'Select a reviewer first.';
    document.getElementById('notes-label').textContent = 'Review Notes' +
        (loadedReviewer ? ' (' + Dipterv.reviewerName(loadedReviewer) + ')' : '');
}

function goTo(idx) {
    commitNotes();
    var none = filteredDocs.length === 0;
    currentIdx = none ? -1 : Math.max(0, Math.min(filteredDocs.length - 1, idx));
    var doc = currentDoc();

    document.getElementById('nav-counter').textContent = none ? '0/0' : (currentIdx + 1) + '/' + filteredDocs.length;
    document.getElementById('nav-name').textContent = doc ? doc.student_name + (doc.degree ? ' (' + doc.degree + ')' : '') : '';
    document.getElementById('nav-supervisor').textContent = doc ? doc.supervisor_name || '' : '';
    document.getElementById('nav-version').textContent = doc ? 'v' + doc.version : '';
    document.getElementById('format-check').innerHTML = doc ? Dipterv.formatBadge(doc) : '';
    document.getElementById('ai-check').innerHTML = doc ? Dipterv.aiScores(doc) : '';
    document.getElementById('nav-first').disabled = none || currentIdx <= 0;
    document.getElementById('nav-prev').disabled = none || currentIdx <= 0;
    document.getElementById('nav-next').disabled = none || currentIdx >= filteredDocs.length - 1;
    document.getElementById('nav-last').disabled = none || currentIdx >= filteredDocs.length - 1;

    if (doc && parent.displayFK) parent.displayFK(doc.filename);
    renderVerdict();
    loadNotes();
    updateHistory();
}

function applyFilter() {
    commitNotes();
    filteredDocs = allDocs.filter(passesFilter);
    goTo(0);
}

function saveReview() {
    if (!Dipterv.state.reviewer) {
        Dipterv.notify('Select a reviewer first.', true);
        return;
    }
    commitNotes();
}

$(function () {
    var params = new URLSearchParams(window.parent.location.search);
    document.getElementById('ai-review-section').classList.toggle('enabled', params.has('ai'));
    $('[data-switch-mode]').on('click', function () {
        parent.switchMode(this.getAttribute('data-switch-mode'));
    });
    $('#save-review').on('click', saveReview);

    $('.filter-toggle').on('click', function () {
        var name = this.getAttribute('data-filter');
        filters[name] = !filters[name];
        this.classList.toggle('active', filters[name]);
        applyFilter();
    });
    $('#nav-first').on('click', function () { goTo(0); });
    $('#nav-prev').on('click', function () { goTo(currentIdx - 1); });
    $('#nav-next').on('click', function () { goTo(currentIdx + 1); });
    $('#nav-last').on('click', function () { goTo(filteredDocs.length - 1); });

    $('#verdict').on('click', '.verdict-btn', function () {
        var doc = currentDoc();
        var status = this.getAttribute('data-verdict');
        if (doc && doc.verdict !== status) Dipterv.setVerdict(doc, status).done(renderVerdict);
    });

    var reviewersReady = Dipterv.loadReviewers(document.getElementById('reviewer-select'), function () {
        commitNotes();
        loadNotes();
    });
    $.when(reviewersReady, $.getJSON('data.php')).done(function (reviewers, data) {
        allDocs = data[0].sort(function (a, b) {
            return (a.student_name || '').localeCompare(b.student_name || '', undefined, { sensitivity: 'base' }) ||
                a.version - b.version;
        });
        Dipterv.markLast(allDocs);
        applyFilter();
    }).fail(function () {
        document.getElementById('nav-counter').textContent = 'error';
    });
});
