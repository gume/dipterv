<?php
require __DIR__ . '/lib.php';
start_session();
security_headers();

if (current_user()) {
    header('Location: dashboard.php');
    exit;
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $token = (string)($_POST['csrf'] ?? '');
    $locked = ($_SESSION['fail_count'] ?? 0) >= 5 && time() < ($_SESSION['locked_until'] ?? 0);
    if (!hash_equals(csrf_token(), $token)) {
        $error = 'The form has expired, please try again.';
    } elseif ($locked) {
        $error = 'Too many failed attempts. Please wait a minute.';
    } else {
        try {
            $user = authenticate(open_db(), (string)($_POST['neptun'] ?? ''), (string)($_POST['password'] ?? ''));
        } catch (Throwable $e) {
            $user = null;
            $error = 'The database is not available.';
        }
        if ($user) {
            session_regenerate_id(true);
            $_SESSION = ['user' => $user];
            header('Location: dashboard.php');
            exit;
        }
        if ($error === '') {
            $_SESSION['fail_count'] = ($_SESSION['fail_count'] ?? 0) + 1;
            if ($_SESSION['fail_count'] >= 5) {
                $_SESSION['locked_until'] = time() + 60;
                $_SESSION['fail_count'] = 0;
            }
            usleep(500000);
            $error = 'Invalid Neptun code or password.';
        }
    }
}
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in - Task description reviews</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body class="login-page">
<main class="login-card">
    <div class="brand">
        <span class="brand-mark">TD</span>
        <h1>Task description reviews</h1>
        <p>Sign in to see the review results of your students' task descriptions.</p>
    </div>
    <?php if ($error): ?><div class="alert" role="alert"><?= h($error) ?></div><?php endif; ?>
    <form method="post" autocomplete="off">
        <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
        <label for="neptun">Neptun code</label>
        <input id="neptun" name="neptun" type="text" maxlength="12" required autofocus value="<?= h($_POST['neptun'] ?? '') ?>">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" maxlength="64" required>
        <button type="submit">Sign in</button>
    </form>
</main>
</body>
</html>
