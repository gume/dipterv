<?php
require __DIR__ . '/lib.php';
require_admin();

$labels = ['go' => 'Accepted', 'nogo' => 'Rejected', 'undecided' => 'Undecided'];
$counts = ['go' => 0, 'nogo' => 0, 'undecided' => 0];
$rows = [];
$error = '';
try {
    $rows = fetch_all(open_db(), '
        SELECT i.supervisor_name, i.student_name, i.neptun_code, i.version,
               COALESCE(NULLIF(i.title_hu, \'\'), i.title_en, e.thesis_title) AS title,
               COALESCE(v.status, \'undecided\') AS status
        FROM "import" AS i
        LEFT JOIN "extract" AS e ON e.filename = i.filename
        LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
        ORDER BY i.supervisor_name, i.student_name, i.version');
    foreach ($rows as &$row) {
        $row['status'] = in_array($row['status'], ['go', 'nogo'], true) ? $row['status'] : 'undecided';
        $counts[$row['status']]++;
    }
    unset($row);
} catch (Throwable $e) {
    $error = 'The database is not available.';
}

render_head('Decisions', 'descriptions.php');
?>
<main class="page">
    <h1>Description decisions</h1>
    <?php if ($error): ?><div class="alert"><?= h($error) ?></div><?php endif; ?>
    <div class="tabs" role="tablist">
        <button type="button" class="tab active" data-filter="all">All <span class="count"><?= count($rows) ?></span></button>
        <?php foreach ($labels as $status => $label): ?>
            <button type="button" class="tab" data-filter="<?= $status ?>"><?= h($label) ?> <span class="count"><?= $counts[$status] ?></span></button>
        <?php endforeach; ?>
    </div>
    <section class="panel">
        <table id="decisions">
            <thead>
                <tr>
                    <th data-sort="text" tabindex="0">Supervisor</th>
                    <th data-sort="text" tabindex="0">Student</th>
                    <th data-sort="text" tabindex="0">Thesis title</th>
                    <th data-sort="num" tabindex="0">Ver.</th>
                    <th data-sort="text" tabindex="0">Status</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($rows as $r): ?>
                <tr data-status="<?= h($r['status']) ?>">
                    <td><?= h($r['supervisor_name']) ?></td>
                    <td><?= h($r['student_name']) ?> <small class="muted"><?= h($r['neptun_code']) ?></small></td>
                    <td><?= h($r['title']) ?></td>
                    <td><?= (int)$r['version'] ?></td>
                    <td><span class="badge <?= h($r['status']) ?>"><?= h($labels[$r['status']]) ?></span></td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
        <p class="muted" id="empty" hidden>No descriptions in this list.</p>
    </section>
</main>
<script src="assets/decisions.js"></script>
</body></html>
