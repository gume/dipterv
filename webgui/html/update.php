<?php
require __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_out(['error' => 'POST required.'], 405);
}

$db = open_db(false);
$filename = $_POST['filename'] ?? '';
$doc = fetch_all($db, 'SELECT neptun_code, version FROM "import" WHERE filename = ?', [$filename]);
if (!$doc) {
    json_out(['error' => 'Unknown file.'], 404);
}
$neptun = $doc[0]['neptun_code'];
$version = (int)$doc[0]['version'];

$action = $_POST['action'] ?? '';
if ($action === 'remark') {
    $reviewer = $_POST['reviewer'] ?? '';
    if (!fetch_all($db, 'SELECT 1 FROM reviewers WHERE id = ?', [$reviewer])) {
        json_out(['error' => 'Unknown reviewer.'], 400);
    }
    $text = trim($_POST['text'] ?? '');
    if ($text === '') {
        $stmt = $db->prepare('DELETE FROM reviews WHERE neptun_code = ? AND version = ? AND reviewer = ? AND aspect = \'remark\'');
        $stmt->bindValue(1, $neptun);
        $stmt->bindValue(2, $version);
        $stmt->bindValue(3, $reviewer);
    } else {
        $stmt = $db->prepare('INSERT OR REPLACE INTO reviews (neptun_code, version, reviewer, aspect, result, updated_at) VALUES (?, ?, ?, \'remark\', ?, datetime(\'now\'))');
        $stmt->bindValue(1, $neptun);
        $stmt->bindValue(2, $version);
        $stmt->bindValue(3, $reviewer);
        $stmt->bindValue(4, $text);
    }
    $stmt->execute();
} elseif ($action === 'verdict') {
    $status = $_POST['status'] ?? '';
    if (!in_array($status, ['go', 'nogo', 'undecided'], true)) {
        json_out(['error' => 'Invalid verdict.'], 400);
    }
    $insert = $db->prepare('INSERT OR IGNORE INTO review_verdict (neptun_code, version) VALUES (?, ?)');
    $insert->bindValue(1, $neptun);
    $insert->bindValue(2, $version);
    $insert->execute();
    $update = $db->prepare('UPDATE review_verdict SET status = ?, updated_at = datetime(\'now\') WHERE neptun_code = ? AND version = ?');
    $update->bindValue(1, $status);
    $update->bindValue(2, $neptun);
    $update->bindValue(3, $version);
    $update->execute();
} else {
    json_out(['error' => 'Unknown action.'], 400);
}

json_out(['ok' => true]);
