<?php
require __DIR__ . '/lib.php';
start_session();
if ($_SERVER['REQUEST_METHOD'] === 'POST' && hash_equals(csrf_token(), (string)($_POST['csrf'] ?? ''))) {
    $_SESSION = [];
    session_destroy();
}
header('Location: index.php');
