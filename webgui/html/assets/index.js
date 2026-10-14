pdfjsDistBuildPdf.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.0.428/pdf.worker.min.js';

function setCookie(name, value) {
    document.cookie = name + '=' + encodeURIComponent(value) + '; path=/; SameSite=Lax';
}
function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

var params = new URLSearchParams(window.location.search);
var aiParameter = params.has('ai') ? '?ai=' + encodeURIComponent(params.get('ai') || '1') : '';
var currentMode = getCookie('dipterv_mode') === 'review' ? 'review' : 'browse';
var viewMode = getCookie('dipterv_view') === 'text' ? 'text' : 'pdf';
var currentFilename = null;
var currentPdf = null;
var currentPageNumber = 1;
var currentZoom = parseFloat(getCookie('dipterv_zoom')) || 1.2;
var currentRenderTask = null;
var loadToken = 0;
var splitter = document.getElementById('splitter');
var splitRatio = 0.5;
try {
    var savedRatio = Number(localStorage.getItem('dipterv_split_ratio'));
    if (savedRatio >= 0.2 && savedRatio <= 0.8) splitRatio = savedRatio;
} catch (error) {
    // Storage can be disabled by browser privacy settings.
}

document.getElementById('mode-frame').src = currentMode + '.html' + aiParameter;

function isStackedLayout() {
    return window.matchMedia('(max-width: 960px)').matches;
}

function applySplitRatio(ratio) {
    splitRatio = Math.max(0.2, Math.min(0.8, ratio));
    var content = document.getElementById('content');
    var contentRect = content.getBoundingClientRect();
    var isStacked = isStackedLayout();
    var total = isStacked ? contentRect.height : contentRect.width;
    var divider = isStacked ? splitter.offsetHeight : splitter.offsetWidth;
    document.getElementById('left').style.flexBasis = (splitRatio * (total - divider)) + 'px';
    splitter.setAttribute('aria-orientation', isStacked ? 'horizontal' : 'vertical');
    splitter.setAttribute('aria-valuenow', Math.round(splitRatio * 100));
}

function updateSplitFromPointer(event) {
    var contentRect = document.getElementById('content').getBoundingClientRect();
    var isStacked = isStackedLayout();
    var total = isStacked ? contentRect.height : contentRect.width;
    var divider = isStacked ? splitter.offsetHeight : splitter.offsetWidth;
    var position = isStacked ? event.clientY - contentRect.top : event.clientX - contentRect.left;
    applySplitRatio((position - divider / 2) / (total - divider));
}

splitter.addEventListener('pointerdown', function(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    splitter.setPointerCapture(event.pointerId);
    splitter.classList.add('dragging');
    updateSplitFromPointer(event);
});
splitter.addEventListener('pointermove', function(event) {
    if (splitter.hasPointerCapture(event.pointerId)) updateSplitFromPointer(event);
});
splitter.addEventListener('pointerup', function(event) {
    if (splitter.hasPointerCapture(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
    splitter.classList.remove('dragging');
    try {
        localStorage.setItem('dipterv_split_ratio', String(splitRatio));
    } catch (error) {
        // Storage can be disabled by browser privacy settings.
    }
});
splitter.addEventListener('pointercancel', function() {
    splitter.classList.remove('dragging');
});
splitter.addEventListener('keydown', function(event) {
    var delta = isStackedLayout() ? 0.02 : 0.02;
    var increase = isStackedLayout() ? event.key === 'ArrowDown' : event.key === 'ArrowRight';
    var decrease = isStackedLayout() ? event.key === 'ArrowUp' : event.key === 'ArrowLeft';
    if (event.key === 'Home') splitRatio = 0.2;
    else if (event.key === 'End') splitRatio = 0.8;
    else if (increase) splitRatio += delta;
    else if (decrease) splitRatio -= delta;
    else return;
    event.preventDefault();
    applySplitRatio(splitRatio);
    try {
        localStorage.setItem('dipterv_split_ratio', String(splitRatio));
    } catch (error) {
        // Storage can be disabled by browser privacy settings.
    }
});
window.addEventListener('resize', function() {
    applySplitRatio(splitRatio);
    applyPaneRatio(paneRatio);
});

// Vertical separator between the viewer and the review pane; the ratio is the pane's share of the right column.
var paneSplitter = document.getElementById('pane-splitter');
var PANE_MIN = 0.15;
var PANE_MAX = 0.6;
var paneRatio = 0.25;
try {
    var savedPaneRatio = Number(localStorage.getItem('dipterv_pane_ratio'));
    if (savedPaneRatio >= PANE_MIN && savedPaneRatio <= PANE_MAX) paneRatio = savedPaneRatio;
} catch (error) {
    // Storage can be disabled by browser privacy settings.
}

function applyPaneRatio(ratio) {
    paneRatio = Math.max(PANE_MIN, Math.min(PANE_MAX, ratio));
    var total = document.getElementById('right').clientHeight - paneSplitter.offsetHeight;
    if (total > 0) document.getElementById('review-pane').style.flexBasis = (paneRatio * total) + 'px';
    paneSplitter.setAttribute('aria-valuenow', Math.round(paneRatio * 100));
}

function savePaneRatio() {
    try {
        localStorage.setItem('dipterv_pane_ratio', String(paneRatio));
    } catch (error) {
        // Storage can be disabled by browser privacy settings.
    }
}

function updatePaneFromPointer(event) {
    var rect = document.getElementById('right').getBoundingClientRect();
    var divider = paneSplitter.offsetHeight;
    applyPaneRatio((rect.bottom - event.clientY - divider / 2) / (rect.height - divider));
}

paneSplitter.addEventListener('pointerdown', function(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    paneSplitter.setPointerCapture(event.pointerId);
    paneSplitter.classList.add('dragging');
    updatePaneFromPointer(event);
});
paneSplitter.addEventListener('pointermove', function(event) {
    if (paneSplitter.hasPointerCapture(event.pointerId)) updatePaneFromPointer(event);
});
paneSplitter.addEventListener('pointerup', function(event) {
    if (paneSplitter.hasPointerCapture(event.pointerId)) paneSplitter.releasePointerCapture(event.pointerId);
    paneSplitter.classList.remove('dragging');
    savePaneRatio();
});
paneSplitter.addEventListener('pointercancel', function() {
    paneSplitter.classList.remove('dragging');
});
paneSplitter.addEventListener('keydown', function(event) {
    if (event.key === 'Home') paneRatio = PANE_MAX;
    else if (event.key === 'End') paneRatio = PANE_MIN;
    else if (event.key === 'ArrowUp') paneRatio += 0.02;
    else if (event.key === 'ArrowDown') paneRatio -= 0.02;
    else return;
    event.preventDefault();
    applyPaneRatio(paneRatio);
    savePaneRatio();
});

function updateZoomUi() {
    var hasPdf = !!currentPdf;
    document.getElementById('zoom-level').textContent = Math.round(currentZoom * 100) + '%';
    document.getElementById('zoom-out').disabled = !hasPdf || currentZoom <= 0.4;
    document.getElementById('zoom-in').disabled = !hasPdf || currentZoom >= 3;
    document.getElementById('zoom-reset').disabled = !hasPdf;
}

function renderCurrentPdfPage() {
    if (!currentPdf) return;

    currentPdf.getPage(currentPageNumber).then(function(page) {
        var viewport = page.getViewport(currentZoom);
        var canvas = document.getElementById('the-canvas');
        var context = canvas.getContext('2d');

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        if (currentRenderTask && currentRenderTask.cancel) currentRenderTask.cancel();
        currentRenderTask = page.render({ canvasContext: context, viewport: viewport });
        currentRenderTask.promise.then(function() {
            currentRenderTask = null;
        }).catch(function(error) {
            currentRenderTask = null;
            if (error && error.name !== 'RenderingCancelledException') console.log(error);
        });
    });

    updateZoomUi();
}

function refreshView() {
    var pdfMode = viewMode === 'pdf';
    document.getElementById('pdf-scroll').style.display = pdfMode ? 'block' : 'none';
    document.getElementById('text-view').style.display = pdfMode ? 'none' : 'block';
    document.getElementById('zoom-controls').style.display = pdfMode ? 'flex' : 'none';
    document.getElementById('view-pdf').classList.toggle('active', pdfMode);
    document.getElementById('view-text').classList.toggle('active', !pdfMode);
    if (!currentFilename) return;

    var token = ++loadToken;
    if (pdfMode) {
        pdfjsDistBuildPdf.getDocument('descriptions/' + currentFilename).promise.then(function(pdf) {
            if (token !== loadToken) return;
            currentPdf = pdf;
            currentPageNumber = 1;
            renderCurrentPdfPage();
        });
    } else {
        var view = document.getElementById('text-view');
        view.textContent = 'Loading...';
        fetch('body.php?filename=' + encodeURIComponent(currentFilename))
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (token === loadToken) view.textContent = data.text || data.error || '';
            })
            .catch(function() {
                if (token === loadToken) view.textContent = 'Could not load the text.';
            });
    }
}

function setViewMode(mode) {
    viewMode = mode === 'text' ? 'text' : 'pdf';
    setCookie('dipterv_view', viewMode);
    refreshView();
}

function switchMode(mode) {
    var nextMode = mode === 'review' ? 'review' : 'browse';
    if (currentMode === nextMode) return;
    currentMode = nextMode;
    setCookie('dipterv_mode', nextMode);
    pane.set(null);
    document.getElementById('mode-frame').src = nextMode + '.html' + aiParameter;
}

// doc is the table frame's own row object, so edits made here show up there and vice versa.
function displayFK(filename, doc) {
    currentFilename = filename;
    if (doc !== undefined) pane.set(doc);
    refreshView();
    return false;
}

function changePdfZoom(delta) {
    if (!currentPdf) return;
    currentZoom = Math.max(0.4, Math.min(3, Math.round((currentZoom + delta) * 10) / 10));
    setCookie('dipterv_zoom', currentZoom);
    renderCurrentPdfPage();
}

function resetPdfZoom() {
    if (!currentPdf) return;
    currentZoom = 1;
    setCookie('dipterv_zoom', currentZoom);
    renderCurrentPdfPage();
}

var pane = (function() {
    var textArea = document.getElementById('pane-text');
    var title = document.getElementById('pane-title');
    var status = document.getElementById('pane-status');
    var stars = Array.prototype.slice.call(document.querySelectorAll('#stars .star'));
    var reviewers = [];
    var doc = null;
    var statusTimer = null;

    fetch('reviewers.php').then(function(r) { return r.json(); }).then(function(list) {
        reviewers = list;
        render();
    });

    function reviewerId() {
        var id = getCookie('dipterv_reviewer');
        return reviewers.some(function(r) { return r.id === id; }) ? id : '';
    }

    function reviewerName(id) {
        var found = reviewers.filter(function(r) { return r.id === id; })[0];
        return found ? found.name : id;
    }

    function scoreOf(id) {
        return doc && doc.remark_scores ? Number(doc.remark_scores[id]) || 0 : 0;
    }

    function drawStars(score, enabled) {
        stars.forEach(function(button, index) {
            button.textContent = index < score ? '\u2605' : '\u2606';
            button.disabled = !enabled;
            button.setAttribute('aria-checked', index + 1 === score ? 'true' : 'false');
        });
    }

    function render() {
        var id = reviewerId();
        var enabled = !!(doc && id);
        textArea.disabled = !enabled;
        textArea.value = enabled ? ((doc.remarks || {})[id] || '') : '';
        textArea.placeholder = !doc ? 'Select a document.' : (id ? 'Write your review here.' : 'Select a reviewer in the table toolbar first.');
        title.textContent = id && doc ? 'Review (' + reviewerName(id) + ')' : 'Review';
        drawStars(enabled ? scoreOf(id) : 0, enabled);
    }

    function say(message, isError) {
        status.textContent = message;
        status.className = isError ? 'error' : '';
        clearTimeout(statusTimer);
        statusTimer = setTimeout(function() { status.textContent = ''; }, isError ? 5000 : 2000);
    }

    function save(score) {
        var id = reviewerId();
        if (!doc || !id) return;
        var target = doc;
        var text = textArea.value.trim();
        var body = new URLSearchParams({ action: 'remark', filename: target.filename, reviewer: id, text: text });
        if (score !== undefined) body.set('score', score === 0 ? '' : String(score));
        fetch('update.php', { method: 'POST', body: body }).then(function(response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            target.remarks = target.remarks || {};
            target.remark_scores = target.remark_scores || {};
            if (text) target.remarks[id] = text; else delete target.remarks[id];
            if (score !== undefined) {
                if (score) target.remark_scores[id] = score; else delete target.remark_scores[id];
            }
            say('Saved.');
            var frame = document.getElementById('mode-frame').contentWindow;
            if (frame && frame.onPaneSaved) frame.onPaneSaved(target);
            render();
        }).catch(function() { say('Save failed.', true); });
    }

    textArea.addEventListener('change', function() { save(); });
    stars.forEach(function(button, index) {
        button.addEventListener('click', function() {
            // Clicking the current rating again clears it.
            var id = reviewerId();
            var next = scoreOf(id) === index + 1 ? 0 : index + 1;
            save(next);
        });
    });

    return {
        set: function(next) { doc = next; render(); },
        refresh: render,
        // Called by the table frame after it saved the same document.
        sync: function(changed) { if (changed === doc) render(); }
    };
})();
window.pane = pane;

document.getElementById('view-pdf').addEventListener('click', function() { setViewMode('pdf'); });
document.getElementById('view-text').addEventListener('click', function() { setViewMode('text'); });
document.getElementById('zoom-out').addEventListener('click', function() { changePdfZoom(-0.1); });
document.getElementById('zoom-reset').addEventListener('click', resetPdfZoom);
document.getElementById('zoom-in').addEventListener('click', function() { changePdfZoom(0.1); });

refreshView();
updateZoomUi();
applySplitRatio(splitRatio);
applyPaneRatio(paneRatio);
