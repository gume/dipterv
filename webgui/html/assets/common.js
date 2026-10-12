// Helpers shared by browse.html and review.html (requires jQuery).
var Dipterv = (function () {
    var VERDICTS = [
        { id: 'go', label: 'Go', symbol: '\u2713' },
        { id: 'nogo', label: 'No-go', symbol: '\u2717' },
        { id: 'undecided', label: 'Undecided', symbol: '?' }
    ];
    var FORMAT = {
        0: { cls: 'fmt-ok', label: 'ok' },
        1: { cls: 'fmt-minor', label: 'minor' },
        2: { cls: 'fmt-severe', label: 'severe' }
    };
    var state = { reviewers: [], reviewer: '' };

    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[1]) : null;
    }

    function setCookie(name, value) {
        document.cookie = name + '=' + encodeURIComponent(value) + '; path=/; SameSite=Lax';
    }

    // ---- tooltip ----
    var tip = null;
    function initTooltip() {
        tip = document.createElement('div');
        tip.id = 'tip';
        document.body.appendChild(tip);
        $(document).on('mouseover', '[data-tip]', function (e) {
            tip.textContent = this.getAttribute('data-tip');
            tip.style.display = 'block';
            moveTooltip(e);
        }).on('mousemove', '[data-tip]', moveTooltip).on('mouseout', '[data-tip]', function () {
            tip.style.display = 'none';
        });
    }

    function moveTooltip(e) {
        var x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
        var y = e.clientY + 18;
        if (y + tip.offsetHeight > window.innerHeight - 8) y = e.clientY - tip.offsetHeight - 10;
        tip.style.left = Math.max(4, x) + 'px';
        tip.style.top = Math.max(4, y) + 'px';
    }

    // ---- toast ----
    var toastTimer = null;
    function notify(message, isError) {
        var toast = document.getElementById('toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'toast';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.className = isError ? 'error' : '';
        toast.style.display = 'block';
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.style.display = 'none'; }, isError ? 5000 : 2000);
    }

    // ---- server calls ----
    function post(data, okMessage) {
        return $.post('update.php', data).done(function () {
            if (okMessage) notify(okMessage);
        }).fail(function (xhr) {
            var message = xhr.responseJSON && xhr.responseJSON.error;
            notify('Save failed' + (message ? ': ' + message : '.'), true);
        });
    }

    function setVerdict(doc, status) {
        return post({ action: 'verdict', filename: doc.filename, status: status }, 'Verdict saved.')
            .done(function () { doc.verdict = status; });
    }

    function saveRemark(doc, reviewer, text) {
        return post({ action: 'remark', filename: doc.filename, reviewer: reviewer, text: text }, 'Review saved.')
            .done(function () {
                if (text.trim()) doc.remarks[reviewer] = text.trim();
                else delete doc.remarks[reviewer];
            });
    }

    // ---- reviewer identity (selection only, no authentication) ----
    function loadReviewers(select, onChange) {
        return $.getJSON('reviewers.php').done(function (list) {
            state.reviewers = list;
            var saved = getCookie('dipterv_reviewer');
            state.reviewer = list.some(function (r) { return r.id === saved; }) ? saved : '';
            select.innerHTML = '<option value="">-- select reviewer --</option>' + list.map(function (r) {
                return '<option value="' + esc(r.id) + '">' + esc(r.name) + '</option>';
            }).join('');
            select.value = state.reviewer;
            select.classList.toggle('unset', !state.reviewer);
            select.addEventListener('change', function () {
                state.reviewer = select.value;
                select.classList.toggle('unset', !state.reviewer);
                setCookie('dipterv_reviewer', state.reviewer);
                if (onChange) onChange(state.reviewer);
            });
        }).fail(function () {
            notify('Could not load the reviewer list.', true);
        });
    }

    function reviewerName(id) {
        var found = state.reviewers.filter(function (r) { return r.id === id; })[0];
        return found ? found.name : id;
    }

    // ---- rendering ----
    function formatBadge(doc) {
        var fmt = FORMAT[doc.template_status];
        if (!fmt) return '<span class="badge" data-tip="Not extracted yet">n/a</span>';
        var tipText = doc.format_issues.length ? doc.format_issues.join('\n') : 'No problems found.';
        return '<span class="badge ' + fmt.cls + '" data-tip="' + esc(tipText) + '">' + fmt.label + '</span>';
    }

    function aspectLabel(key) {
        return key.split('_').map(function (part) { return part.charAt(0).toUpperCase(); }).join('');
    }

    function aiScores(doc) {
        var models = Object.keys(doc.ai);
        if (!models.length) return '<span class="muted">-</span>';
        return models.map(function (model) {
            var chips = doc.ai[model].map(function (item) {
                var score = item.score == null ? '?' : item.score;
                var text = item.aspect + ': ' + score + '/5\n' + (item.result || '');
                return '<span class="chip score-' + esc(score) + '" data-tip="' + esc(text) + '">' +
                    esc(aspectLabel(item.aspect)) + ' ' + esc(score) + '</span>';
            }).join('');
            return '<div class="ai-row"><span class="ai-model" data-tip="' + esc(model) + '">' + esc(model) +
                '</span>' + chips + '</div>';
        }).join('');
    }

    function aiAverage(doc) {
        var scores = [];
        Object.keys(doc.ai).forEach(function (model) {
            doc.ai[model].forEach(function (item) { if (item.score != null) scores.push(item.score); });
        });
        if (!scores.length) return 0;
        return scores.reduce(function (a, b) { return a + b; }, 0) / scores.length;
    }

    function verdictButtons(doc) {
        return '<span class="verdict" data-filename="' + esc(doc.filename) + '">' + VERDICTS.map(function (v) {
            return '<button type="button" class="verdict-btn v-' + v.id + (doc.verdict === v.id ? ' active' : '') +
                '" data-verdict="' + v.id + '" data-tip="' + v.label + '">' + v.symbol + '</button>';
        }).join('') + '</span>';
    }

    function markLast(docs) {
        var max = {};
        docs.forEach(function (d) {
            if (max[d.neptun_code] === undefined || d.version > max[d.neptun_code]) max[d.neptun_code] = d.version;
        });
        docs.forEach(function (d) { d.is_last = d.version === max[d.neptun_code]; });
    }

    $(initTooltip);

    return {
        state: state, esc: esc, notify: notify, loadReviewers: loadReviewers, reviewerName: reviewerName,
        setVerdict: setVerdict, saveRemark: saveRemark, formatBadge: formatBadge, aiScores: aiScores,
        aiAverage: aiAverage, verdictButtons: verdictButtons, markLast: markLast
    };
})();
