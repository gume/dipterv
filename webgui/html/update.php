<?php

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

$db = new SQLite3('/db/descriptions.sqlite', SQLITE3_OPEN_CREATE | SQLITE3_OPEN_READWRITE);

foreach ($_POST as $key => $value) {
	if ($value == "") continue;
	$key = preg_replace('/_pdf$/', '.pdf', $key);
	echo("Key: $key, Value: $value\r\n");
	if (substr($key, 0, 9) == 'ekovacsG_') {
		$filename = substr($key, 9);

		$sql = "UPDATE dipterv SET ekovacsG = '$value' WHERE filename = '$filename'";
		echo($sql . "\r\n");
		$result = $db->query($sql);
	}
	else if (substr($key, 0, 8) == 'eGuszti_') {
		$filename = substr($key, 8);

		$sql = "UPDATE dipterv SET eGuszti = '$value' WHERE filename = '$filename'";
		echo($sql . "\r\n");
		$result = $db->query($sql);
	}
	else if (substr($key, 0, 6) == 'eGume_') {
		$filename = substr($key, 6);

		$sql = "UPDATE dipterv SET eGume = '$value' WHERE filename = '$filename'";
		echo($sql . "\r\n");
		$result = $db->query($sql);

	}	
	else if (substr($key, 0, 6) == 'ePali_') {
		$filename = substr($key, 6);

		$sql = "UPDATE dipterv SET ePali = '$value' WHERE filename = '$filename'";
		echo($sql . "\r\n");
		$result = $db->query($sql);

	}
	else if (substr($key, 0, 7) == 'status_') {
		$filename = substr($key, 7);

		$sql = "UPDATE dipterv SET status = '$value' WHERE filename = '$filename'";
		echo($sql . "\r\n");
		$result = $db->query($sql);
	}
}

//header("Location: index.html"); /* Redirect browser */
//header("Location: ."); /* Refresh in browser */
exit();

?>
