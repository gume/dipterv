<?php

const DB_PATH = '/db/descriptions.sqlite';
const AI_MODEL_KEY = 'supervisor_ai_model';

function start_session(): void
{
    session_name('supervisor_sid');
    session_set_cookie_params(['httponly' => true, 'samesite' => 'Strict', 'path' => '/']);
    session_start();
}

// The database is only ever opened read-only; this app has no write path.
function open_db(): SQLite3
{
    $db = new SQLite3(DB_PATH, SQLITE3_OPEN_READONLY);
    $db->enableExceptions(true);
    $db->busyTimeout(5000);
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

function csrf_token(): string
{
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
}

function normalize_neptun(string $value): string
{
    return strtoupper(trim($value));
}

// Temporary scheme: the password equals the Neptun code. Replace with OAuth later.
function authenticate(SQLite3 $db, string $neptun, string $password): ?array
{
    $neptun = normalize_neptun($neptun);
    if ($neptun === '' || !table_exists($db, 'supervisors')) {
        return null;
    }
    $rows = fetch_all($db, 'SELECT * FROM supervisors WHERE neptun_code = ?', [$neptun]);
    $user = $rows[0] ?? null;
    // Compare even for unknown users so the timing does not reveal valid codes.
    $expected = $user['neptun_code'] ?? str_repeat('x', 6);
    $ok = hash_equals($expected, normalize_neptun($password));
    if (!$user || !$ok) {
        return null;
    }
    // display_name prefers the manually set alternative name.
    $alt = trim((string)($user['alt_name'] ?? ''));
    return ['neptun_code' => $user['neptun_code'], 'name' => $user['name'], 'display_name' => $alt !== '' ? $alt : $user['name']];
}

function current_user(): ?array
{
    return $_SESSION['user'] ?? null;
}

function require_login(): array
{
    $user = current_user();
    if (!$user) {
        header('Location: index.php');
        exit;
    }
    return $user;
}

function security_headers(): void
{
    header("Content-Security-Policy: default-src 'self'; style-src 'self'; frame-ancestors 'none'");
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: same-origin');
    header('Cache-Control: no-store');
}

// Descriptions of the supervisor, grouped by student and newest version first.
function load_descriptions(SQLite3 $db, string $supervisorCode): array
{
    $rows = fetch_all($db, '
        SELECT i.neptun_code, i.version, i.filename, i.student_name, i.degree, i.faculty, i.subject,
               i.title_hu, i.title_en,
               e.template_status, e.page_count, e.thesis_title,
               e.missing_boilerplate_rules_json, e.layout_discrepancies_json,
               COALESCE(v.status, \'undecided\') AS verdict, v.summary AS verdict_summary,
               v.updated_at AS verdict_updated
        FROM "import" AS i
        LEFT JOIN "extract" AS e ON e.filename = i.filename
        LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
        WHERE i.supervisor_code = ?
        ORDER BY i.student_name, i.version DESC
    ', [$supervisorCode]);
    foreach ($rows as &$row) {
        $row['key'] = $row['neptun_code'] . '-' . $row['version'];
        $row['verdict'] = in_array($row['verdict'], ['go', 'nogo'], true) ? $row['verdict'] : 'undecided';
        $row['formal'] = formal_issues($row);
        $row['template_status'] = $row['template_status'] === null ? null : (int)$row['template_status'];
    }
    return $rows;
}

function formal_issues(array $row): array
{
    $issues = [];
    foreach (json_decode($row['missing_boilerplate_rules_json'] ?? '[]', true) ?: [] as $rule) {
        $issues[] = ['kind' => 'Missing text', 'text' => (string)$rule];
    }
    foreach (json_decode($row['layout_discrepancies_json'] ?? '[]', true) ?: [] as $text) {
        $kind = str_starts_with((string)$text, 'Page count:') ? 'Page count' : 'Layout';
        $issues[] = ['kind' => $kind, 'text' => (string)preg_replace('/^Page count:\s*/', '', (string)$text)];
    }
    return $issues;
}

// Human remarks in chronological order.
function load_human_reviews(SQLite3 $db, string $neptun, int $version): array
{
    $hasReviewers = table_exists($db, 'reviewers');
    $name = $hasReviewers ? 'COALESCE(p.name, r.reviewer)' : 'r.reviewer';
    $join = $hasReviewers ? 'LEFT JOIN reviewers AS p ON p.id = r.reviewer' : '';
    return fetch_all($db, "
        SELECT $name AS reviewer, r.result, r.score, r.updated_at
        FROM reviews AS r $join
        WHERE r.neptun_code = ? AND r.version = ? AND r.aspect = 'remark'
          AND (TRIM(COALESCE(r.result, '')) <> '' OR r.score IS NOT NULL)
        ORDER BY r.updated_at ASC, r.reviewer
    ", [$neptun, $version]);
}

function configured_ai_model(SQLite3 $db): ?string
{
    if (!table_exists($db, 'settings')) {
        return null;
    }
    $rows = fetch_all($db, 'SELECT value FROM settings WHERE key = ?', [AI_MODEL_KEY]);
    $value = trim((string)($rows[0]['value'] ?? ''));
    return $value === '' ? null : $value;
}

// One AI review: the configured model, or the most recently updated one when none is configured.
function load_ai_review(SQLite3 $db, string $neptun, int $version, ?string $model): ?array
{
    $summaries = table_exists($db, 'review_summaries')
        ? fetch_all($db, '
            SELECT reviewer, average_score, summary, updated_at FROM review_summaries
            WHERE neptun_code = ? AND version = ?
            ORDER BY updated_at DESC', [$neptun, $version])
        : [];
    if ($model === null) {
        $model = $summaries[0]['reviewer'] ?? null;
        if ($model === null) {
            $rows = fetch_all($db, "
                SELECT reviewer FROM reviews
                WHERE neptun_code = ? AND version = ? AND aspect <> 'remark'
                ORDER BY updated_at DESC LIMIT 1", [$neptun, $version]);
            $model = $rows[0]['reviewer'] ?? null;
        }
    }
    if ($model === null) {
        return null;
    }
    $summary = null;
    foreach ($summaries as $s) {
        if ($s['reviewer'] === $model) {
            $summary = $s;
            break;
        }
    }
    $aspects = fetch_all($db, "
        SELECT aspect, result, score FROM reviews
        WHERE neptun_code = ? AND version = ? AND reviewer = ? AND aspect <> 'remark'
        ORDER BY rowid", [$neptun, $version, $model]);
    if (!$aspects && !$summary) {
        return null;
    }
    return [
        'model' => $model,
        'average' => $summary ? (float)$summary['average_score'] : null,
        'summary' => $summary['summary'] ?? '',
        'updated_at' => $summary['updated_at'] ?? null,
        'aspects' => $aspects,
    ];
}

function aspect_label(string $key): string
{
    return ucfirst(str_replace('_', ' ', $key));
}
