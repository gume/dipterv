<?php
require __DIR__ . '/lib.php';
require_admin();

function render_histogram_svg(array $histogram): string
{
    if (empty($histogram)) {
        return '<div class="muted" style="text-align:center;padding:20px;">No distribution data available</div>';
    }

    $n = count($histogram);
    $width = 300;
    $height = 130;
    $chartTop = 22;
    $chartBottom = 105;
    $chartHeight = $chartBottom - $chartTop;

    $maxCount = 0;
    foreach ($histogram as $item) {
        $c = (int)($item['count'] ?? 0);
        if ($c > $maxCount) {
            $maxCount = $c;
        }
    }

    $slotWidth = $width / max(1, $n);
    $barWidth = max(8, min(36, $slotWidth * 0.7));

    $svg = '<svg viewBox="0 0 ' . $width . ' ' . $height . '" class="histogram-svg" role="img" aria-label="Distribution chart">';
    $svg .= '<line x1="8" y1="' . $chartBottom . '" x2="' . ($width - 8) . '" y2="' . $chartBottom . '" class="hist-axis" />';

    foreach ($histogram as $i => $item) {
        $count = (int)($item['count'] ?? 0);
        $pct = (float)($item['percentage'] ?? 0);
        $bucket = (string)($item['bucket'] ?? ($i + 1));

        $xCenter = 10 + ($i + 0.5) * (($width - 20) / $n);
        $barX = round($xCenter - ($barWidth / 2));

        $barH = ($maxCount > 0 && $count > 0) ? max(4, round(($count / $maxCount) * $chartHeight)) : 0;
        $barY = $chartBottom - $barH;

        if ($barH > 0) {
            $svg .= '<rect x="' . $barX . '" y="' . $barY . '" width="' . $barWidth . '" height="' . $barH . '" rx="4" class="hist-bar">';
            $svg .= '<title>' . h($bucket) . ': ' . $count . ' (' . number_format($pct, 1) . '%)</title>';
            $svg .= '</rect>';

            $svg .= '<text x="' . round($xCenter) . '" y="' . ($barY - 5) . '" class="hist-count-text">' . $count . '</text>';
        }

        $svg .= '<text x="' . round($xCenter) . '" y="' . ($chartBottom + 16) . '" class="hist-label-text">' . h($bucket) . '</text>';
    }

    $svg .= '</svg>';
    return $svg;
}

function render_progress_svg(float $percentage): string
{
    $p = max(0.0, min(100.0, $percentage));
    $svg = '<svg viewBox="0 0 100 8" class="progress-svg" preserveAspectRatio="none">';
    $svg .= '<rect x="0" y="0" width="100" height="8" rx="4" class="progress-bg" />';
    $svg .= '<rect x="0" y="0" width="' . number_format($p, 1, '.', '') . '" height="8" rx="4" class="progress-fill" />';
    $svg .= '</svg>';
    return $svg;
}

$topics = [];
$metrics = [];
$facts = [];
$lastUpdated = null;
$error = '';

try {
    $db = open_db();

    if (table_exists($db, 'description_topics')) {
        $topics = fetch_all($db, 'SELECT * FROM description_topics ORDER BY rank ASC LIMIT 5');
    }
    if (table_exists($db, 'description_metric_distributions')) {
        $metrics = fetch_all($db, 'SELECT * FROM description_metric_distributions ORDER BY rowid ASC');
    }
    if (table_exists($db, 'description_fun_facts')) {
        $facts = fetch_all($db, 'SELECT * FROM description_fun_facts ORDER BY id ASC');
    }

    foreach ([$topics, $metrics, $facts] as $dataset) {
        foreach ($dataset as $row) {
            if (!empty($row['updated_at']) && ($lastUpdated === null || $row['updated_at'] > $lastUpdated)) {
                $lastUpdated = $row['updated_at'];
            }
        }
    }
} catch (Throwable $e) {
    $error = 'The database is not available: ' . $e->getMessage();
}

render_head('Statistics', 'statistics.php');
?>
<main class="page">
    <div class="stats-header">
        <div>
            <h1>Statistics & Insights</h1>
            <p class="section-desc">Analysis of thesis topic clusters, evaluation distributions, and portfolio facts.</p>
        </div>
        <?php if ($lastUpdated): ?>
            <div class="stats-meta">Last analyzed: <?= h($lastUpdated) ?></div>
        <?php endif; ?>
    </div>

    <?php if ($error): ?>
        <div class="alert"><?= h($error) ?></div>
    <?php endif; ?>

    <?php if (empty($topics) && empty($metrics) && empty($facts)): ?>
        <div class="panel">
            <h2>No Statistics Available Yet</h2>
            <p class="muted">
                Statistics have not been computed. Run the statistics computation script to analyze thesis descriptions:
            </p>
            <pre><code>python3 /app/compute_statistics.py</code></pre>
        </div>
    <?php endif; ?>

    <?php if (!empty($topics)): ?>
        <section class="stats-section">
            <div class="section-header">
                <h2>Top 5 Department Topics <span class="count"><?= count($topics) ?></span></h2>
                <p class="section-desc">Identified from technical keywords and thesis frequencies, ranked by department share.</p>
            </div>
            <div class="topics-list">
                <?php foreach ($topics as $t):
                    $rank = (int)$t['rank'];
                    $rankClass = in_array($rank, [1, 2, 3], true) ? ' rank-' . $rank : '';
                    $pct = (float)$t['percentage'];
                    $keywords = json_decode($t['top_keywords_json'] ?? '[]', true) ?: [];
                ?>
                    <article class="topic-card">
                        <div class="topic-card-top">
                            <div class="topic-title-wrap">
                                <span class="topic-rank<?= $rankClass ?>">#<?= $rank ?></span>
                                <h3 class="topic-title"><?= h($t['topic_name']) ?></h3>
                            </div>
                            <div class="topic-stat-badge">
                                <span><?= (int)$t['thesis_count'] ?> theses</span>
                                <span class="muted">&bull;</span>
                                <strong><?= number_format($pct, 1) ?>%</strong>
                            </div>
                        </div>

                        <div class="topic-progress-wrap">
                            <?= render_progress_svg($pct) ?>
                        </div>

                        <?php if (!empty($t['topic_description'])): ?>
                            <p class="topic-desc"><?= h($t['topic_description']) ?></p>
                        <?php endif; ?>

                        <?php if (!empty($keywords)): ?>
                            <div class="topic-keywords">
                                <span class="keywords-label">Keywords:</span>
                                <?php foreach ($keywords as $kw): ?>
                                    <span class="keyword-badge"><?= h($kw) ?></span>
                                <?php endforeach; ?>
                            </div>
                        <?php endif; ?>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
    <?php endif; ?>

    <?php if (!empty($metrics)): ?>
        <section class="stats-section">
            <div class="section-header">
                <h2>Metric Distributions & Histograms <span class="count"><?= count($metrics) ?></span></h2>
                <p class="section-desc">Latest versions only. AI aspect scores are calculated separately for each model.</p>
            </div>
            <div class="metrics-grid">
                <?php foreach ($metrics as $m):
                    $avg = (float)$m['average_value'];
                    $samples = (int)$m['total_samples'];
                    $isScore100 = str_contains($m['metric_key'], 'fit_score_') || str_ends_with($m['metric_key'], '_fit');
                    $isVersionCount = $m['metric_key'] === 'version_count';
                    $scale = $isVersionCount ? 'versions / thesis' : ($isScore100 ? '/ 100%' : '/ 5.0');
                    $histogram = json_decode($m['histogram_json'] ?? '[]', true) ?: [];
                    $sourceLabel = $isScore100 ? 'Blind Fit Test' : (($m['source_type'] === 'extract') ? 'Extract Assessment' : (($m['source_type'] === 'import') ? 'Versioning' : 'AI Review'));
                ?>
                    <article class="metric-card">
                        <div>
                            <div class="metric-header">
                                <h3 class="metric-title"><?= h($m['metric_label']) ?></h3>
                                <span class="metric-badges">
                                    <?php if (!empty($m['model'])): ?>
                                        <span class="metric-badge model"><?= h($m['model']) ?></span>
                                    <?php endif; ?>
                                    <span class="metric-badge"><?= h($sourceLabel) ?></span>
                                </span>
                            </div>
                            <div class="metric-score-row">
                                <span class="metric-avg-val"><?= number_format($avg, $isScore100 ? 1 : 2) ?></span>
                                <span class="metric-scale"><?= $scale ?></span>
                                <span class="metric-samples">N = <?= $samples ?></span>
                            </div>
                        </div>
                        <div class="histogram-wrap">
                            <?= render_histogram_svg($histogram) ?>
                        </div>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
    <?php endif; ?>

    <?php if (!empty($facts)): ?>
        <section class="stats-section">
            <div class="section-header">
                <h2>Curiosities & Fun Facts <span class="count"><?= count($facts) ?></span></h2>
                <p class="section-desc">Notable statistics, interesting patterns, and highlights discovered across the thesis descriptions.</p>
            </div>
            <div class="facts-grid">
                <?php foreach ($facts as $f): ?>
                    <article class="fact-card">
                        <span class="fact-cat"><?= h(strtoupper($f['category'])) ?></span>
                        <?php if (!empty($f['highlight_stat'])): ?>
                            <div class="fact-stat"><?= h($f['highlight_stat']) ?></div>
                        <?php endif; ?>
                        <h3 class="fact-title"><?= h($f['title']) ?></h3>
                        <p class="fact-desc"><?= h($f['fact_text']) ?></p>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
    <?php endif; ?>
</main>
</body></html>

