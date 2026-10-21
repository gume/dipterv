<?php
require __DIR__ . '/db.php';

// Same body as scraper/app/review_docs.py document_body(), with the extracted
// keywords appended so reviewers can see them next to the description.
$rows = fetch_all(open_db(),
    'SELECT thesis_title, problem_background, project_goal, task_intro, tasks_json,
            keyword1, keyword2, keyword3, keyword4, keyword5
     FROM "extract" WHERE filename = ?',
    [$_GET['filename'] ?? '']);
if (!$rows) {
    json_out(['error' => 'No extracted text for this file.'], 404);
}

$e = $rows[0];
$tasks = json_decode($e['tasks_json'] ?? '[]', true) ?: [];
$numbered = [];
foreach (array_values($tasks) as $n => $task) {
    $numbered[] = ($n + 1) . '. ' . $task;
}
$parts = array_filter([
    $e['thesis_title'], $e['problem_background'], $e['project_goal'], $e['task_intro'], implode("\n", $numbered),
], function ($part) {
    return $part !== null && $part !== '';
});

$keywords = array_filter(
    [$e['keyword1'], $e['keyword2'], $e['keyword3'], $e['keyword4'], $e['keyword5']],
    function ($keyword) {
        return $keyword !== null && trim($keyword) !== '';
    });
$text = implode("\n\n", $parts);
if ($keywords) {
    $text .= "\n\nKeywords: " . implode(', ', $keywords);
}

json_out(['text' => $text]);
