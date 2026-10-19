<?php
require __DIR__ . '/lib.php';
require_admin();

function format_portal_status(?string $status): ?array
{
    if ($status === null || $status === '') {
        return null;
    }
    $norm = strtolower(trim($status));
    if (in_array($norm, ['accepted', 'go', 'tanszékvezető jóváhagyta'], true)) {
        return ['label' => 'Accepted', 'badge' => 'go'];
    }
    if (in_array($norm, ['rejected', 'nogo', 'konzulensi feltöltésre vár, mert a tanszékvezető elutasította', 'nincs beadva, mert a tanszékvezető nem hagyta jóvá'], true)) {
        return ['label' => 'Rejected', 'badge' => 'nogo'];
    }
    if (in_array($norm, ['undecided', 'feltöltve, tanszékvezetői jóváhagyásra vár'], true)) {
        return ['label' => 'Undecided', 'badge' => 'undecided'];
    }
    return null;
}

$labels = ['go' => 'Accepted', 'nogo' => 'Rejected', 'undecided' => 'Undecided'];
$counts = ['go' => 0, 'nogo' => 0, 'undecided' => 0];
$mismatchCount = 0;
$rows = [];
$error = '';
try {
    $db = open_db();
    $importCols = array_column(fetch_all($db, 'PRAGMA table_info("import")'), 'name');
    $portalCol = in_array('portal_status', $importCols, true) ? 'i.portal_status' : 'NULL AS portal_status';

    $rows = fetch_all($db, "
        SELECT i.supervisor_name, i.student_name, i.neptun_code, i.version,
               COALESCE(NULLIF(i.title_hu, ''), i.title_en, e.thesis_title) AS title,
               COALESCE(v.status, 'undecided') AS status,
               {$portalCol}
        FROM \"import\" AS i
        LEFT JOIN \"extract\" AS e ON e.filename = i.filename
        LEFT JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
        WHERE (i.subject IS NULL OR TRIM(i.subject) != ?)
        ORDER BY i.supervisor_name, i.student_name, i.version", [EXCLUDED_SUBJECT]);

    $maxVersions = [];
    foreach ($rows as $r) {
        $code = $r['neptun_code'];
        $ver = (int)$r['version'];
        if (!isset($maxVersions[$code]) || $ver > $maxVersions[$code]) {
            $maxVersions[$code] = $ver;
        }
    }

    foreach ($rows as &$row) {
        $row['status'] = in_array($row['status'], ['go', 'nogo'], true) ? $row['status'] : 'undecided';
        $row['is_latest'] = ((int)$row['version'] === ($maxVersions[$row['neptun_code']] ?? null)) ? 1 : 0;
        $ps = format_portal_status($row['portal_status'] ?? null);
        $row['portal_info'] = $ps;
        $row['is_mismatch'] = ($ps === null || $row['status'] !== $ps['badge']) ? 1 : 0;

        $counts[$row['status']]++;
        if ($row['is_mismatch']) {
            $mismatchCount++;
        }
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
    <div class="toolbar">
        <div class="tabs" role="tablist">
            <button type="button" class="tab active" data-filter="all">All <span class="count"><?= count($rows) ?></span></button>
            <?php foreach ($labels as $status => $label): ?>
                <button type="button" class="tab" data-filter="<?= $status ?>"><?= h($label) ?> <span class="count"><?= $counts[$status] ?></span></button>
            <?php endforeach; ?>
            <button type="button" class="tab" data-filter="mismatch">Mismatch <span class="count"><?= $mismatchCount ?></span></button>
        </div>
        <div class="toolbar-filter">
            <label class="filter-toggle" for="filter-latest">
                <input type="checkbox" id="filter-latest">
                <span class="switch-track"></span>
                <span>Latest version only</span>
            </label>
        </div>
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
                    <th data-sort="text" tabindex="0">Uni status</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($rows as $r): ?>
                <?php $ps = $r['portal_info']; ?>
                <tr data-status="<?= h($r['status']) ?>" data-mismatch="<?= $r['is_mismatch'] ? '1' : '0' ?>" data-latest="<?= $r['is_latest'] ? '1' : '0' ?>">
                    <td><?= h($r['supervisor_name']) ?></td>
                    <td><?= h($r['student_name']) ?> <small class="muted"><?= h($r['neptun_code']) ?></small></td>
                    <td><?= h($r['title']) ?></td>
                    <td><?= (int)$r['version'] ?></td>
                    <td><span class="badge <?= h($r['status']) ?>"><?= h($labels[$r['status']]) ?></span></td>
                    <td><?php if ($ps): ?><span class="badge <?= h($ps['badge']) ?>"><?= h($ps['label']) ?></span><?php endif; ?></td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
        <p class="muted" id="empty" hidden>No descriptions in this list.</p>
    </section>
</main>
<script src="assets/decisions.js"></script>
</body></html>
