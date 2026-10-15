var table = null;
var docs = [];
var filters = { go: true, nogo: true, undecided: true, last: false };
var aiMode = false;
var aiModels = [];
var filterRegistered = false;
var hiddenAiModels = {};
var selectedDoc = null;
var aiColumnStart = 0;
var hiddenReviewers = {};
var reviewerColumnStart = 0;

function renderReviewerToggles(reviewers) {
    var box = $('#reviewer-toggles');
    box.find('.column-toggle').remove();
    box.prop('hidden', !reviewers.length);
    reviewers.forEach(function (reviewer, index) {
        $('<button type="button" class="column-toggle"></button>')
            .text(reviewer.name)
            .toggleClass('active', !hiddenReviewers[reviewer.id])
            .on('click', function () {
                hiddenReviewers[reviewer.id] = !hiddenReviewers[reviewer.id];
                this.classList.toggle('active', !hiddenReviewers[reviewer.id]);
                if (table) table.column(reviewerColumnStart + index).visible(!hiddenReviewers[reviewer.id]);
            })
            .appendTo(box);
    });
}

function renderAiToggles() {
    var box = $('#ai-toggles');
    box.find('.column-toggle').remove();
    box.prop('hidden', !aiMode || !aiModels.length);
    if (!aiMode) return;
    aiModels.forEach(function (model, index) {
        $('<button type="button" class="column-toggle"></button>')
            .text(aiModels.length === 1 ? 'AI' : 'AI#' + (index + 1))
            .attr('title', model)
            .toggleClass('active', !hiddenAiModels[model])
            .on('click', function () {
                hiddenAiModels[model] = !hiddenAiModels[model];
                this.classList.toggle('active', !hiddenAiModels[model]);
                if (table) table.column(aiColumnStart + index).visible(!hiddenAiModels[model]);
            })
            .appendTo(box);
    });
}

function textOf(value) {
    return value == null ? '' : String(value);
}

function remarkColumn(reviewer) {
    return {
        title: Dipterv.esc(reviewer.name),
        data: null,
        type: 'num',
        render: function (doc, type) {
            var text = textOf(doc.remarks[reviewer.id]);
            var score = Number((doc.remark_scores || {})[reviewer.id]) || 0;
            if (type === 'sort' || type === 'type') return score;
            if (type !== 'display') return text;
            var editable = Dipterv.state.reviewer === reviewer.id;
            return Dipterv.starsReadonly(score) + '<textarea class="remark" data-reviewer="' + Dipterv.esc(reviewer.id) + '"' +
                (editable ? '' : ' readonly') + '>' + Dipterv.esc(text) + '</textarea>';
        }
    };
}

function aiModelColumn(model, index) {
    return {
        title: aiModels.length === 1 ? 'AI' : 'AI#' + (index + 1),
        data: null,
        className: 'ai-average',
        type: 'num',
        render: function (doc, type) {
            if (type !== 'display') return Dipterv.aiAverage(doc, model);
            return Dipterv.aiModelCell(doc, model);
        }
    };
}

function buildTable() {
    if (table) {
        table.destroy();
        $('#docs').empty();
    }

    var columns = [
        {
            title: 'Student', data: null,
            render: function (doc, type) {
                if (type !== 'display') return textOf(doc.student_name);
                return '<div class="student-cell"><button type="button" class="open-pdf" title="Open"></button>' +
                    '<span>' + Dipterv.esc(doc.student_name) + ' (' + Dipterv.esc(doc.degree) + ')</span>' +
                    '<span class="student-version">v' + Dipterv.esc(doc.version) + '</span></div>';
            }
        },
        { title: 'Supervisor', data: null, render: function (doc) { return Dipterv.esc(doc.supervisor_name); } },
        {
            title: 'Format', data: null,
            render: function (doc, type) {
                return type === 'display' ? Dipterv.formatBadge(doc) : (doc.template_status == null ? -1 : doc.template_status);
            }
        }
    ];

    aiColumnStart = columns.length;
    if (aiMode) aiModels.forEach(function (model, index) {
        columns.push(aiModelColumn(model, index));
        columns[columns.length - 1].visible = !hiddenAiModels[model];
    });

    var reviewers = Dipterv.state.reviewers.slice();
    reviewers.sort(function (a, b) {
        return Number(b.id === Dipterv.state.reviewer) - Number(a.id === Dipterv.state.reviewer);
    });
    reviewerColumnStart = columns.length;
    renderReviewerToggles(reviewers);
    columns = columns.concat(reviewers.map(function (reviewer) {
        var column = remarkColumn(reviewer);
        column.visible = !hiddenReviewers[reviewer.id];
        return column;
    }), [{
        title: 'Verdict', data: null,
        render: function (doc, type) {
            return type === 'display' ? Dipterv.verdictButtons(doc) : doc.verdict;
        }
    }]);

    table = $('#docs').DataTable({
        data: docs,
        columns: columns,
        createdRow: function (row, doc) {
            $(row).data('doc', doc).toggleClass('selected-row', doc === selectedDoc);
        },
        paging: false,
        autoWidth: false,
        ordering: true,
        order: [],
        deferRender: true,
        initComplete: function () {
            if (!aiMode) return;
            var api = this.api();
            aiModels.forEach(function (model, index) {
                var header = api.column(aiColumnStart + index).header();
                header.setAttribute('data-tip', model);
                header.setAttribute('title', model);
            });
        }
    });

    if (!filterRegistered) {
        $.fn.dataTable.ext.search.push(function (settings, data, index) {
            if (settings.nTable.id !== 'docs') return true;
            var doc = table.row(index).data();
            if (!doc) return true;
            if (filters.last && !doc.is_last) return false;
            return filters[doc.verdict] !== false;
        });
        filterRegistered = true;
    }
}

function redrawRow(tr) {
    table.row(tr).invalidate().draw(false);
}

function docOf(element) {
    return table.row($(element).closest('tr')).data();
}

// The review pane saved this document; show its text and rating in the table.
window.onPaneSaved = function (doc) {
    if (!table) return;
    table.rows().every(function () {
        if (this.data() === doc) this.invalidate();
    });
    table.draw(false);
};

$(function () {
    var params = new URLSearchParams(window.parent.location.search);
    aiMode = params.has('ai');
    $('[data-switch-mode]').on('click', function () {
        parent.switchMode(this.getAttribute('data-switch-mode'));
    });

    $('.filter-toggle').on('click', function () {
        var name = this.getAttribute('data-filter');
        filters[name] = !filters[name];
        this.classList.toggle('active', filters[name]);
        if (table) table.draw();
    });

    $('#docs').on('click', '.open-pdf', function () {
        var doc = docOf(this);
        selectedDoc = doc;
        $('#docs tbody tr.selected-row').removeClass('selected-row');
        $(this).closest('tr').addClass('selected-row');
        parent.displayFK(doc.filename, doc);
    });

    $('#docs').on('click', '.verdict-btn', function () {
        var tr = $(this).closest('tr');
        var doc = docOf(this);
        var status = this.getAttribute('data-verdict');
        if (doc.verdict !== status) Dipterv.setVerdict(doc, status).done(function () { redrawRow(tr); });
    });

    $('#docs').on('change', 'textarea.remark', function () {
        var reviewer = this.getAttribute('data-reviewer');
        if (this.readOnly || reviewer !== Dipterv.state.reviewer) return;
        Dipterv.saveRemark(docOf(this), reviewer, this.value);
    });

    var reviewersReady = Dipterv.loadReviewers(document.getElementById('reviewer-select'), function () {
        if (table) buildTable();
    });
    $.when(reviewersReady, $.getJSON('data.php')).done(function (reviewers, response) {
        docs = response[0];
        Dipterv.markLast(docs);
        var modelSet = {};
        docs.forEach(function (doc) {
            Object.keys(doc.ai).forEach(function (model) { modelSet[model] = true; });
        });
        aiModels = Object.keys(modelSet).sort();
        renderAiToggles();
        buildTable();
    }).fail(function () {
        Dipterv.notify('Could not load the data.', true);
    });
});
