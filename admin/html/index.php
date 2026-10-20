<?php
require __DIR__ . '/lib.php';
require_admin();

$counts = ['go' => 0, 'nogo' => 0, 'undecided' => 0];
$supervisors = 0;
$error = '';
try {
    $db = open_db();
    foreach (fetch_all($db, '
        SELECT COALESCE(v.status, \'undecided\') AS status, COUNT(*) AS n
        FROM "import" AS i
        LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
        WHERE (i.subject IS NULL OR TRIM(i.subject) != ?)
        GROUP BY 1', [EXCLUDED_SUBJECT]) as $r) {
        $counts[in_array($r['status'], ['go', 'nogo'], true) ? $r['status'] : 'undecided'] += (int)$r['n'];
    }
    if (table_exists($db, 'supervisors')) {
        $supervisors = (int)fetch_all($db, 'SELECT COUNT(*) AS n FROM supervisors')[0]['n'];
    }
} catch (Throwable $e) {
    $error = 'The database is not available.';
}

render_head('Tasks', 'index.php');
?>
<main class="page">
    <h1>Tasks</h1>
    <?php if ($error): ?><div class="alert"><?= h($error) ?></div><?php endif; ?>
    <div class="tiles">
        <a class="tile" href="descriptions.php">
            <h2>Description decisions</h2>
            <p>Which task descriptions are accepted, rejected or still undecided.</p>
            <div class="tile-stats">
                <span class="badge go"><?= $counts['go'] ?> accepted</span>
                <span class="badge nogo"><?= $counts['nogo'] ?> rejected</span>
                <span class="badge undecided"><?= $counts['undecided'] ?> undecided</span>
            </div>
        </a>
        <a class="tile" href="supervisors.php">
            <h2>Supervisors</h2>
            <p>The supervisors known to the system and their descriptions.</p>
            <div class="tile-stats"><span class="badge neutral"><?= $supervisors ?> supervisors</span></div>
        </a>
        <a class="tile" href="statistics.php">
            <h2>Statistics & Insights</h2>
            <p>Top 5 department topics, metric distribution histograms, and fun facts.</p>
            <div class="tile-stats"><span class="badge neutral">View analytics</span></div>
        </a>
    </div>
</main>
</body></html>
