<?php
require __DIR__ . '/db.php';

json_out(fetch_all(open_db(), 'SELECT id, name FROM reviewers ORDER BY rowid'));
