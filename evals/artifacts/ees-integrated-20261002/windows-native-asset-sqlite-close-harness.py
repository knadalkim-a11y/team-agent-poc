from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import platform
import sqlite3
import sys
import unittest
from unittest.mock import patch
import test_ees_asset_native as module

names = [
 'NativeAuthoringAssetReadTests.test_sa12_actual_native_public_asset_references_do_not_grant_workspace_or_write_assets',
 'NativeAuthoringAssetReadTests.test_sa12_18_actual_native_acl_revocation_keeps_opaque_draft_but_blocks_publication',
]
source = Path(module.__file__).resolve()
original = sqlite3.connect
connections = []
def tracked_connect(*args, **kwargs):
    caller = inspect.currentframe().f_back
    connection = original(*args, **kwargs)
    if Path(caller.f_code.co_filename).resolve() == source and caller.f_code.co_name == 'native_digest':
        connections.append(connection)
    return connection

output = Path('dist/integrated/windows-native-asset-sqlite-close-local.log')
with output.open('w', encoding='utf-8') as stream:
    with patch.object(sqlite3, 'connect', tracked_connect):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.TestLoader().loadTestsFromNames(names, module=module))
    open_connections = 0
    for connection in connections:
        try:
            connection.execute('SELECT 1')
        except sqlite3.ProgrammingError as error:
            assert 'closed database' in str(error), str(error)
        else:
            open_connections += 1
        finally:
            connection.close()
    report = {'date_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'python': sys.version, 'tests': names, 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
              'strict_default_encoding': True, 'native_digest_connections_kept_alive_until_after_cleanup': len(connections),
              'open_native_digest_connections': open_connections,
              'test_scope': 'Pinned upstream real Native tables/ACL fixture and explicit historical authoring; not full product browser or company environment',
              'windows_execution': 'not run locally; next Windows CI required'}
    stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
Path('dist/integrated/windows-native-asset-sqlite-close-local.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
assert result.wasSuccessful() and result.testsRun == 2 and not result.skipped
assert connections and not open_connections
