<?php
require __DIR__ . '/lib.php';
start_session();
security_headers();
$user = require_login();

$verdictLabels = [
    'go' => ['Accepted', 'The description is accepted.'],
    'nogo' => ['Rejected', 'The description is rejected and needs to be reworked.'],
    'undecided' => ['Undecided', 'No decision has been made yet.'],
];
$formalLabels = [
    0 => ['ok', 'Formally correct'],
    1 => ['minor', 'Minor formal problems'],
    2 => ['critical', 'Critical formal problems'],
];

$error = '';
$docs = [];
try {
    $db = open_db();
    $docs = load_descriptions($db, $user['neptun_code']);
} catch (Throwable $e) {
    $error = 'The database is not available.';
}

$selected = null;
foreach ($docs as $doc) {
    if (($doc['key'] ?? '') === ($_GET['d'] ?? '')) {
        $selected = $doc;
    }
}
$selected = $selected ?? ($docs[0] ?? null);

$human = [];
$ai = null;
$aiModel = null;
if ($selected) {
    $human = load_human_reviews($db, $selected['neptun_code'], (int)$selected['version']);
    $aiModel = configured_ai_model($db);
    $ai = load_ai_review($db, $selected['neptun_code'], (int)$selected['version'], $aiModel);
}

function pips(?int $score): string
{
    $html = '<span class="pips" title="' . ($score === null ? 'Not rated' : $score . ' / 5') . '">';
    for ($i = 1; $i <= 5; $i++) {
        $html .= '<i class="' . ($score !== null && $i <= $score ? 'on s' . $score : '') . '"></i>';
    }
    return $html . '</span>';
}

function stars(?int $score): string
{
    if ($score === null) {
        return '';
    }
    return '<span class="stars" title="' . $score . ' / 5">' . str_repeat('★', $score) . str_repeat('☆', 5 - $score) . '</span>';
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My students' task descriptions</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="topbar">
    <div class="topbar-title"><span class="brand-mark small">TD</span> Task description reviews</div>
    <form method="post" action="logout.php" class="topbar-user">
        <span><?= h($user['display_name']) ?> <small>(<?= h($user['neptun_code']) ?>)</small></span>
        <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
        <button type="submit" class="link">Sign out</button>
    </form>
</header>

<?php if ($error): ?>
    <main class="empty"><div class="alert"><?= h($error) ?></div></main>
<?php elseif (!$docs): ?>
    <main class="empty"><h2>No task descriptions found</h2><p>There are no task descriptions assigned to you yet.</p></main>
<?php else: ?>
<div class="layout">
    <aside class="list">
        <h2>Descriptions <span class="count"><?= count($docs) ?></span></h2>
        <?php foreach ($docs as $doc): $v = $doc['verdict']; ?>
            <a class="card <?= $doc['key'] === $selected['key'] ? 'active' : '' ?>" href="?d=<?= h(urlencode($doc['key'])) ?>">
                <span class="card-name"><?= h($doc['student_name']) ?></span>
                <span class="card-title"><?= h($doc['title_hu'] ?: $doc['title_en'] ?: $doc['thesis_title'] ?: '') ?></span>
                <span class="card-meta">
                    <span class="badge <?= h($v) ?>"><?= h($verdictLabels[$v][0]) ?></span>
                    <?php if ($doc['template_status'] === 2): ?><span class="badge critical">Formal errors</span><?php endif; ?>
                    <span class="ver">v<?= (int)$doc['version'] ?></span>
                </span>
            </a>
        <?php endforeach; ?>
    </aside>

    <main class="detail">
        <?php $v = $selected['verdict']; $fs = $selected['template_status']; ?>
        <div class="doc-head">
            <h1><?= h($selected['student_name']) ?> <small><?= h($selected['neptun_code']) ?> &middot; version <?= (int)$selected['version'] ?></small></h1>
            <p class="doc-title"><?= h($selected['title_hu'] ?: $selected['title_en'] ?: $selected['thesis_title'] ?: '') ?></p>
            <p class="doc-sub"><?= h(implode(' · ', array_filter([$selected['degree'], $selected['faculty'], $selected['subject']]))) ?></p>
        </div>

        <section class="verdict <?= h($v) ?>">
            <div class="verdict-icon"><?= $v === 'go' ? '✔' : ($v === 'nogo' ? '✖' : '…') ?></div>
            <div>
                <div class="verdict-label"><?= h($verdictLabels[$v][0]) ?></div>
                <div class="verdict-text"><?= h($verdictLabels[$v][1]) ?></div>
                <?php if (trim((string)$selected['verdict_summary']) !== ''): ?>
                    <div class="verdict-note"><?= nl2br(h($selected['verdict_summary'])) ?></div>
                <?php endif; ?>
                <?php if ($selected['verdict_updated'] && $v !== 'undecided'): ?>
                    <div class="muted">Decided: <?= h($selected['verdict_updated']) ?> UTC</div>
                <?php endif; ?>
            </div>
        </section>

        <section class="panel">
            <h2>Formal check
                <?php if ($fs === null): ?><span class="badge undecided">Not checked yet</span>
                <?php else: ?><span class="badge <?= h($formalLabels[$fs][0]) ?>"><?= h($formalLabels[$fs][1]) ?></span><?php endif; ?>
            </h2>
            <?php if ($selected['page_count'] !== null): ?>
                <p class="muted">Pages: <?= (int)$selected['page_count'] ?> (exactly one page is required)</p>
            <?php endif; ?>
            <?php if ($selected['formal']): ?>
                <ul class="issues">
                    <?php foreach ($selected['formal'] as $issue): ?>
                        <li><span class="kind"><?= h($issue['kind']) ?></span> <?= h($issue['text']) ?></li>
                    <?php endforeach; ?>
                </ul>
            <?php elseif ($fs !== null): ?>
                <p class="muted">No formal errors were found.</p>
            <?php endif; ?>
        </section>

        <section class="panel">
            <h2>Reviewer remarks</h2>
            <?php if (!$human): ?>
                <p class="muted">No reviewer remarks yet.</p>
            <?php endif; ?>
            <?php foreach ($human as $r): ?>
                <article class="remark">
                    <header>
                        <strong><?= h($r['reviewer']) ?></strong>
                        <?= stars($r['score'] === null ? null : (int)$r['score']) ?>
                        <time><?= h($r['updated_at']) ?> UTC</time>
                    </header>
                    <?php if (trim((string)$r['result']) !== ''): ?><p><?= nl2br(h($r['result'])) ?></p><?php endif; ?>
                </article>
            <?php endforeach; ?>
        </section>

        <section class="panel">
            <h2>AI review <?php if ($ai): ?><span class="model"><?= h($ai['model']) ?></span><?php endif; ?></h2>
            <?php if (!$ai): ?>
                <p class="muted">No AI review is available for this description.</p>
            <?php else: ?>
                <?php if ($ai['average'] !== null): ?>
                    <div class="avg"><span class="avg-value"><?= h(number_format($ai['average'], 2)) ?></span><span class="avg-of">/ 5 average</span></div>
                <?php endif; ?>
                <?php if (trim($ai['summary']) !== ''): ?><p class="ai-summary"><?= nl2br(h($ai['summary'])) ?></p><?php endif; ?>
                <?php foreach ($ai['aspects'] as $a): ?>
                    <details class="aspect">
                        <summary><span><?= h(aspect_label($a['aspect'])) ?></span><?= pips($a['score'] === null ? null : (int)$a['score']) ?></summary>
                        <p><?= nl2br(h($a['result'])) ?></p>
                    </details>
                <?php endforeach; ?>
                <p class="muted">AI reviews are automatic and informational; the verdict above is decided by the reviewers.</p>
            <?php endif; ?>
        </section>
    </main>
</div>
<?php endif; ?>
</body>
</html>
