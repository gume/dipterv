<?php

const DB_PATH = '/db/descriptions.sqlite';

function open_db($readOnly = true) {
    $db = new SQLite3(DB_PATH, $readOnly ? SQLITE3_OPEN_READONLY : SQLITE3_OPEN_READWRITE);
    $db->busyTimeout(5000);
    return $db;
}

function json_out($data, $status = 200) {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function fetch_all($db, $sql, $params = []) {
    $stmt = $db->prepare($sql);
    foreach ($params as $i => $value) {
        $stmt->bindValue($i + 1, $value);
    }
    $result = $stmt->execute();
    $rows = [];
    while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
        $rows[] = $row;
    }
    return $rows;
}
