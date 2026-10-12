<?php
require __DIR__ . '/db.php';

$db = open_db();

$docs = [];
$index = [];
$rows = fetch_all($db, '
    SELECT i.filename, i.neptun_code, i.version, i.student_name, i.supervisor_name, i.degree, i.faculty,
           e.template_status, e.missing_boilerplate_rules_json, e.layout_discrepancies_json,
           COALESCE(v.status, \'undecided\') AS verdict
    FROM "import" AS i
    LEFT JOIN "extract" AS e ON e.filename = i.filename
    LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
    ORDER BY i.row_id, i.filename
');
foreach ($rows as $row) {
    $issues = [];
    foreach (json_decode($row['missing_boilerplate_rules_json'] ?? '[]', true) ?: [] as $rule) {
        $issues[] = 'Missing: ' . $rule;
    }
    foreach (json_decode($row['layout_discrepancies_json'] ?? '[]', true) ?: [] as $text) {
        $issues[] = 'Layout: ' . $text;
    }
    unset($row['missing_boilerplate_rules_json'], $row['layout_discrepancies_json']);
    $row['template_status'] = $row['template_status'] === null ? null : (int)$row['template_status'];
    $row['format_issues'] = $issues;
    $row['remarks'] = [];
    $row['ai'] = [];
    $index[$row['neptun_code'] . '|' . $row['version']] = count($docs);
    $docs[] = $row;
}

// A "remark" aspect is a human remark; all other aspects are scored (AI) reviews.
foreach (fetch_all($db, 'SELECT neptun_code, version, reviewer, aspect, result, score FROM reviews ORDER BY reviewer, aspect') as $r) {
    $key = $r['neptun_code'] . '|' . $r['version'];
    if (!isset($index[$key])) {
        continue;
    }
    $i = $index[$key];
    if ($r['aspect'] === 'remark') {
        $docs[$i]['remarks'][$r['reviewer']] = $r['result'];
    } else {
        $docs[$i]['ai'][$r['reviewer']][] = [
            'aspect' => $r['aspect'],
            'score' => $r['score'] === null ? null : (int)$r['score'],
            'result' => $r['result'],
        ];
    }
}

foreach ($docs as &$doc) {
    $doc['remarks'] = (object)$doc['remarks'];
    $doc['ai'] = (object)$doc['ai'];
}
unset($doc);

json_out($docs);
