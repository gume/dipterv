<?php

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

$db = new SQLite3('/db/descriptions.sqlite', SQLITE3_OPEN_CREATE | SQLITE3_OPEN_READWRITE);

foreach ($_POST as $key => $value) {
	if ($value == "") continue;
	if (substr($key, 0, 9) == 'ekovacsG_') {
		$id = substr($key, 9);

		$sql = "UPDATE dipterv SET ekovacsG = '$value' WHERE id = '$id'";
		echo($sql . "\r\n");
		$result = $db->query($sql);
	}
	else if (substr($key, 0, 8) == 'eGuszti_') {
		$id = substr($key, 8);

		$sql = "UPDATE dipterv SET eGuszti = '$value' WHERE id = '$id'";
		echo($sql . "\r\n");
		$result = $db->query($sql);
	}
	else if (substr($key, 0, 6) == 'eGume_') {
		$id = substr($key, 6);

		$sql = "UPDATE dipterv SET eGume = '$value' WHERE id = '$id'";
		echo($sql . "\r\n");
		$result = $db->query($sql);

	}	
	else if (substr($key, 0, 6) == 'ePali_') {
		$id = substr($key, 6);

		$sql = "UPDATE dipterv SET ePali = '$value' WHERE id = '$id'";
		echo($sql . "\r\n");
		$result = $db->query($sql);

	}	
}

//header("Location: index.html"); /* Redirect browser */
//header("Location: ."); /* Refresh in browser */
exit();

?>
