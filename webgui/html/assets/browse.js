var table = null;
var docs = [];
var filters = { go: true, nogo: true, undecided: true, last: false };
var aiMode = false;

function textOf(value) {
    return value == null ? '' : String(value);
}

function remarkColumn(reviewer) {
    return {
        title: Dipterv.esc(reviewer.name),
        orderable: false,
        data: null,
        render: function (doc, type) {
            var text = textOf(doc.remarks[reviewer.id]);
            if (type !== 'display') return text;
            var editable = Dipterv.state.reviewer === reviewer.id;
            return '<textarea class="remark" data-reviewer="' + Dipterv.esc(reviewer.id) + '"' +
                (editable ? '' : ' readonly') + '>' + Dipterv.esc(text) + '</textarea>';
        }
    };
}

function averageColumn() {
    return {
        title: 'AI avg',
        data: null,
        className: 'ai-average',
        render: function (doc, type) {
            var score = Dipterv.aiAverage(doc);
            if (type === 'sort' || type === 'type') return score;
            return score ? score.toFixed(2) : '';
        }
    };
}

function buildTable() {
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

    if (aiMode) {
        columns.push(averageColumn());
        columns.push({
            title: 'AI reviews', data: null,
            render: function (doc, type) {
                return type === 'display' ? Dipterv.aiScores(doc) : Dipterv.aiAverage(doc);
            }
        });
    }

    columns = columns.concat(Dipterv.state.reviewers.map(remarkColumn), [{
        title: 'Verdict', data: null,
        render: function (doc, type) {
            return type === 'display' ? Dipterv.verdictButtons(doc) : doc.verdict;
        }
    }]);

    table = $('#docs').DataTable({
        data: docs,
        columns: columns,
        createdRow: function (row, doc) { $(row).data('doc', doc); },
        paging: false,
        autoWidth: false,
        ordering: true,
        order: [],
        deferRender: true
    });

    $.fn.dataTable.ext.search.push(function (settings, data, index) {
        if (settings.nTable.id !== 'docs') return true;
        var doc = table.row(index).data();
        if (!doc) return true;
        if (filters.last && !doc.is_last) return false;
        return filters[doc.verdict] !== false;
    });
}

function redrawRow(tr) {
    table.row(tr).invalidate().draw(false);
}

function docOf(element) {
    return table.row($(element).closest('tr')).data();
}

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
        parent.displayFK(docOf(this).filename);
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
        if (table) table.rows().invalidate().draw(false);
    });
    $.when(reviewersReady, $.getJSON('data.php')).done(function (reviewers, response) {
        docs = response[0];
        Dipterv.markLast(docs);
        buildTable();
    }).fail(function () {
        Dipterv.notify('Could not load the data.', true);
    });
});
