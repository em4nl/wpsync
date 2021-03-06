from datetime import datetime
from pathlib import Path
from .host_info import HostInfo
from . import put
from .connection import RemoteExecutionError


this_dir = Path(__file__).resolve().parent
mysqldump_php_template = """<?php

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include_once(__DIR__ . '/Mysqldump.php');

try {{

    $dump = new Ifsnop\Mysqldump\Mysqldump(
        'mysql:host={mysql_host};dbname={mysql_name};port={mysql_port}',
        '{mysql_user}',
        '{mysql_pass}',
        array(
            'extended-insert' => false,
            'add-drop-table' => true,
        )
    );

    $dump->start(__DIR__ . '/dump.sql');

}} catch (Exception $e) {{

    http_response_code(500); # internal server error
    echo $e->getMessage();
}}
"""


def backup(
    wpsyncdir, site, connection, quiet, database, uploads, plugins, themes, full
):
    host = HostInfo(wpsyncdir, site, connection)
    dt = datetime.now()
    iso_ts = dt.isoformat()[:19]
    fs_ts = f"{iso_ts[:13]}_{iso_ts[14:16]}_{iso_ts[17:]}"
    backup_dir = wpsyncdir / "backups" / site["fs_safe_name"] / fs_ts

    if not quiet:
        put.title(f'Creating new backup of {site["name"]}')

    if database or full:
        if not quiet:
            put.step("Backing up database")
        database_backup_dir = backup_dir / "database"
        local_dump_file = database_backup_dir / "dump.sql"
        remote_dump_file = connection.normalise("dump.sql")
        database_backup_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

        php_code = mysqldump_php_template.format(**site)
        mysqldump_library_local = this_dir / "Mysqldump.php"
        mysqldump_library_remote = connection.normalise("Mysqldump.php")
        connection.put(mysqldump_library_local, mysqldump_library_remote)
        # TODO Connection#run_php returns the response text, do
        # something with it?
        try:
            connection.run_php(php_code)
            connection.get(remote_dump_file, str(local_dump_file.resolve()))
        except RemoteExecutionError as error:
            put.error(error)
        finally:
            connection.rm(mysqldump_library_remote)
            # TODO easier to ask forgiveness
            if connection.file_exists(remote_dump_file):
                connection.rm(remote_dump_file)

    if uploads:
        backup_a_dir(backup_dir, site, connection, "uploads", quiet)

    if plugins:
        backup_a_dir(backup_dir, site, connection, "plugins", quiet)

    if themes:
        backup_a_dir(backup_dir, site, connection, "themes", quiet)

    if full:
        if not quiet:
            put.step("Backing up full site")
        local_dir = backup_dir / "full"
        remote_dir = site["base_dir"][:-1]
        local_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        connection.mirror(remote_dir, local_dir)

    return fs_ts


def backup_a_dir(backup_dir, site, connection, name, quiet):
    if not quiet:
        put.step(f"Backing up {name}")
    local_dir = backup_dir / name
    remote_dir = f'{site["base_dir"]}wp-content/{name}'
    if not connection.dir_exists(remote_dir):
        if not quiet:
            put.info(
                f'\bwp-content/{name} doesn\'t exist on {site["name"]},'
                + " creating it"
            )
        connection.mkdir(remote_dir)
    local_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    connection.mirror(remote_dir, local_dir)
