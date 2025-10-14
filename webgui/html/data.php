<?php

function utf8ize($d) {
    if (is_array($d)) {
        foreach ($d as $k => $v) {
            $d[$k] = utf8ize($v);
        }
    } else if (is_string ($d)) {
        return utf8_encode($d);
    }
    return $d;
}

$db = new SQLite3('/db/descriptions.sqlite', SQLITE3_OPEN_CREATE | SQLITE3_OPEN_READWRITE);

$result = $db->query("SELECT * FROM dipterv");

$rows = Array();
while($r = $result->fetchArray(SQLITE3_ASSOC)){
  array_push($rows, $r);
}

header('Content-type:application/json;charset=utf-8');
print json_encode($rows);

?>
