<?php
require __DIR__ . '/lib.php';
require_admin();

$rows = [];
$error = '';
try {
    $db = open_db();
    if (!table_exists($db, 'supervisors')) {
        $error = 'The supervisors table does not exist yet; run create_db.py.';
    } else {
        $rows = fetch_all($db, '
            SELECT s.neptun_code, s.name, s.alt_name,
                   COUNT(i.filename) AS total,
                   SUM(CASE WHEN v.status = \'go\' THEN 1 ELSE 0 END) AS go,
                   SUM(CASE WHEN v.status = \'nogo\' THEN 1 ELSE 0 END) AS nogo
            FROM supervisors AS s
            LEFT JOIN "import" AS i ON i.supervisor_code = s.neptun_code
            LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
            GROUP BY s.neptun_code
            ORDER BY COALESCE(NULLIF(s.alt_name, \'\'), s.name)');
    }
} catch (Throwable $e) {
    $error = 'The database is not available.';
}

render_head('Supervisors', 'supervisors.php');
?>
<main class="page">
    <h1>Supervisors <span class="count"><?= count($rows) ?></span></h1>
    <?php if ($error): ?><div class="alert"><?= h($error) ?></div><?php endif; ?>
    <section class="panel">
        <table>
            <thead><tr><th>Name</th><th>Neptun code</th><th>Descriptions</th><th>Accepted</th><th>Rejected</th><th>Undecided</th></tr></thead>
            <tbody>
            <?php foreach ($rows as $r):
                $alt = trim((string)$r['alt_name']);
                $total = (int)$r['total']; $go = (int)$r['go']; $nogo = (int)$r['nogo']; ?>
                <tr>
                    <td><?= h($alt !== '' ? $alt : $r['name']) ?>
                        <?php if ($alt !== ''): ?><small class="muted">(portal: <?= h($r['name']) ?>)</small><?php endif; ?></td>
                    <td><?= h($r['neptun_code']) ?></td>
                    <td><?= $total ?></td>
                    <td><span class="badge go"><?= $go ?></span></td>
                    <td><span class="badge nogo"><?= $nogo ?></span></td>
                    <td><span class="badge undecided"><?= $total - $go - $nogo ?></span></td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</main>
</body></html>
