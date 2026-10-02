from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import platform
import sqlite3
import sys
import unittest
from unittest.mock import patch
import test_ees_work_authoring as module

names = [
    'SystemAuthoringTests.test_sa19_publish_and_audit_failure_roll_back_one_transaction',
    'AuthoringRestoreTests.test_sa23_exact_legacy_archive_and_explicit_partial_import',
    'AuthoringRestoreTests.test_sa25_explicit_admin_reconciliation_resumes_changed_or_removed_publication',
    'AuthoringRestoreTests.test_sa25_reconciliation_rejects_stale_publication_and_rolls_back_failed_audit',
    'AuthoringRestoreTests.test_sa25_real_previous_program_restore_and_reupgrade_preserve_new_and_old_state',
    'AuthoringRestoreTests.test_sa25_old_publication_shared_reference_cannot_be_changed_through_one_process',
]
source = Path(module.__file__).resolve()
expected_lines = {number for number, line in enumerate(source.read_text(encoding='utf-8').splitlines(), 1)
                  if 'with closing(sqlite3.connect(self.database)) as db, db:' in line}
assert len(expected_lines) == 14
original = sqlite3.connect
connections = []
def tracked_connect(*args, **kwargs):
    caller = inspect.currentframe().f_back
    origin = (str(Path(caller.f_code.co_filename).resolve()), caller.f_lineno)
    connection = original(*args, **kwargs)
    connections.append((connection, origin))
    return connection

output = Path('dist/integrated/windows-authoring-sqlite-close-local.log')
with output.open('w', encoding='utf-8') as stream:
    with patch.object(sqlite3, 'connect', tracked_connect):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.TestLoader().loadTestsFromNames(names, module=module))
    open_connections = []
    for connection, origin in connections:
        try:
            connection.execute('SELECT 1')
        except sqlite3.ProgrammingError:
            continue
        else:
            open_connections.append(origin)
        finally:
            connection.close()
    covered_lines = {line for _, (path, line) in connections if path == str(source)} & expected_lines
    report = {'date_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'python': sys.version, 'tests': names, 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
              'strict_default_encoding': True, 'connections_kept_alive_until_after_cleanup': len(connections),
              'open_connections': open_connections, 'changed_connection_sites': sorted(expected_lines),
              'executed_changed_connection_sites': sorted(covered_lines),
              'historical_fixture_bytes': 'unchanged; pinned ees.10 and b41e239 checks executed by test helpers',
              'initial_harness_selection': 'No tests ran: sa23/sa25 belong to AuthoringRestoreTests, corrected selectors.',
              'windows_execution': 'not run locally; next Windows CI required'}
    stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
Path('dist/integrated/windows-authoring-sqlite-close-local.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
assert result.wasSuccessful() and result.testsRun == 6 and not result.skipped
assert not open_connections, open_connections
assert covered_lines == expected_lines, (expected_lines, covered_lines)
