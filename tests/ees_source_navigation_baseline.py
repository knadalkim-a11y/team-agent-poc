"""Require the real 42cc756 browser regression to fail on EES loading frames.

This is a negative-control gate, never a passing result for the old product.
Unexpected assertions, skipped tests, browser/bootstrap errors and absent frame
evidence all reject the gate. Candidate tests run separately, unchanged.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


BASELINE = '42cc7568eb8477013abcf0a042617dd9e3279db2'
TEST = ('test_ees_source_shell_native.SourceShellNativeTests.'
        'test_delayed_navigation_never_replaces_loaded_menu_or_panel_with_loading')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--branding-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline, branding, output = (path.resolve() for path in
                                  (args.baseline_dir, args.branding_dir, args.output))
    output.mkdir(parents=True, exist_ok=True)
    report = {'baseline_commit': BASELINE, 'test': TEST, 'status': 'rejected'}
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=baseline,
                                         text=True, encoding='utf-8').strip()
        if commit != BASELINE:
            raise AssertionError('Negative control checkout is not the fixed baseline')
        status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=baseline,
                                         text=True, encoding='utf-8').strip()
        if status:
            raise AssertionError('Negative control checkout has pre-existing changes')
        manifest = json.loads((branding / 'manifest.json').read_text(encoding='utf-8'))
        provenance = branding / 'baseline-provenance.json'
        if provenance.exists():
            report['provenance'] = json.loads(provenance.read_text(encoding='utf-8'))
            if report['provenance'].get('commit') != BASELINE:
                raise AssertionError('Negative control program provenance differs')
        wheel = branding / manifest['wheel']['filename']
        report['wheel_sha256'] = digest(wheel)
        if (report['wheel_sha256'] != manifest['wheel']['sha256']
                or wheel.stat().st_size != manifest['wheel']['size']):
            raise AssertionError('Negative control wheel differs from its manifest')
        # Only the new observer and exact same regression are copied. All
        # product bytes and fixtures remain owned by the fixed old checkout.
        report['test_sources'] = {}
        for name in ('test_ees_source_shell_native.py', 'ees_source_frame_monitor.py'):
            source = Path(__file__).resolve().parent / name
            destination = baseline / 'tests' / name
            shutil.copyfile(source, destination)
            report['test_sources'][name] = digest(destination)
        os.environ['EES_TEST_BRANDING_DIR'] = str(branding)
        os.environ['EES_TEST_SCREENSHOT_DIR'] = str(output)
        sys.path[:0] = [str(baseline / 'tests'), str(baseline)]
        os.chdir(baseline)
        importlib.invalidate_caches()
        suite = unittest.TestLoader().loadTestsFromName(TEST)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report['tests_run'] = result.testsRun
        report['failures'] = [detail for _, detail in result.failures]
        report['errors'] = [detail for _, detail in result.errors]
        report['skipped'] = [(str(case), reason) for case, reason in result.skipped]
        if (result.testsRun != 1 or len(result.failures) != 1 or result.errors
                or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
            raise AssertionError('Baseline did not produce exactly one ordinary assertion failure')
        if 'Observed EES loading placeholders after initial data:' not in result.failures[0][1]:
            raise AssertionError('Baseline failed for a reason other than EES loading placeholders')
        evidence = json.loads((output / 'source-shell-delayed-navigation-frames.json').read_text(encoding='utf-8'))
        samples = evidence['samples']
        guarded = [row for row in samples if row.get('loadingGuard')]
        bad = [row for row in guarded if row.get('menuLoading') or row.get('panelLoading')]
        if not bad or not evidence['counts'] or any(value['frames'] < 3 for value in evidence['counts'].values()):
            raise AssertionError('Baseline has no complete positive loading-frame evidence')
        if any(row['legacy'] or row['missingSource'] or row['bodyHidden'] or row['startupGate'] for row in samples):
            raise AssertionError('Baseline had a separate source-shell visibility failure')
        reads = evidence['reads']
        if (not reads or any(not row['completed'] or row['released'] - row['started'] < .99 for row in reads)
                or not all(any(row['path'].endswith('/' + endpoint) for row in reads)
                           for endpoint in ('workspace', 'operations'))):
            raise AssertionError('Baseline did not exercise both one-second HTTP delays')
        report.update(status='negative_control_verified', baseline_status='failed_as_required',
                      loading_frames=len(bad), counts=evidence['counts'])
        print('Baseline 42cc756 failed as required: EES loading_frames=' + str(len(bad)))
        return 0
    except Exception as error:
        report['rejection'] = type(error).__name__ + ': ' + str(error)
        print(report['rejection'], file=sys.stderr)
        return 1
    finally:
        (output / 'baseline-verification.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
