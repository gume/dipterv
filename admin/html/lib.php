<?php

const DB_PATH = '/db/descriptions.sqlite';

// Write handlers must use open_db(true); SQLite serializes writers, busy_timeout makes them wait for each other.
function open_db(bool $write = false): SQLite3
{
    $db = new SQLite3(DB_PATH, $write ? SQLITE3_OPEN_READWRITE : SQLITE3_OPEN_READONLY);
    $db->enableExceptions(true);
    $db->busyTimeout(10000);
    return $db;
}

function fetch_all(SQLite3 $db, string $sql, array $params = []): array
{
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

function table_exists(SQLite3 $db, string $name): bool
{
    return (bool)fetch_all($db, "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", [$name]);
}

function h($value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

// HTTP basic auth, enabled when ADMIN_PASSWORD is set in the container environment.
function require_admin(): void
{
    header("Content-Security-Policy: default-src 'self'; style-src 'self'; frame-ancestors 'none'");
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: no-store');

    $password = getenv('ADMIN_PASSWORD');
    if ($password === false || $password === '') {
        return;
    }
    $user = getenv('ADMIN_USER') ?: 'admin';
    $given = $_SERVER['PHP_AUTH_USER'] ?? '';
    $givenPass = $_SERVER['PHP_AUTH_PW'] ?? '';
    if (!hash_equals($user, $given) | !hash_equals($password, $givenPass)) {
        header('WWW-Authenticate: Basic realm="Admin"');
        http_response_code(401);
        echo 'Authentication required.';
        exit;
    }
}

function render_head(string $title, string $active): void
{
    $nav = ['index.php' => 'Tasks', 'descriptions.php' => 'Decisions', 'supervisors.php' => 'Supervisors'];
    echo '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        . '<meta name="viewport" content="width=device-width, initial-scale=1">'
        . '<title>' . h($title) . ' - Admin</title><link rel="stylesheet" href="assets/style.css"></head><body>'
        . '<header class="topbar"><div class="topbar-title"><span class="brand-mark small">AD</span> Admin</div><nav>';
    foreach ($nav as $href => $label) {
        echo '<a href="' . $href . '"' . ($href === $active ? ' class="active"' : '') . '>' . h($label) . '</a>';
    }
    echo '</nav></header>';
}
