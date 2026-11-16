"""Install the reviewed EES release from its verified GitHub Actions artifact."""
import argparse
import hashlib
import http.client
import json
import locale
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time

SHA = 'd1ba8555991f5d730dbdd60552d697ae416861bd'
DIGEST = 'ffba55bcda20c3f5f092457b4d694e6e99bddecf9c461029a9cb0d75f4f355a4'
ARTIFACT_ID = 14199642442
SIZE = 155790205
REGISTRY = 'EES_WORK_API_SERVICES'
SERVICE = 'confluence-readonly-pilot'
AUTH = 'EES_CONFLUENCE_PILOT_AUTHORIZATION'
SOURCE = 'https://github.com/knadalkim-a11y/team-agent-poc'
FILENAME = 'ees-program-' + SHA + '.zip'


class DeploymentError(Exception):
    pass


def parse_output(data):
    for encoding in ('utf-8-sig', 'utf-16', locale.getpreferredencoding(False), 'oem'):
        try:
            return json.loads(data.decode(encoding))
        except (ValueError, UnicodeError, LookupError):
            continue
    raise DeploymentError('EES 관리자의 상태 결과를 확인할 수 없습니다.')


def manager(repo, config, action, *extra, env=None, read=False):
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = repo / 'scripts/manage-ees.ps1'
    if not script.is_file():
        raise DeploymentError('기존 EES 설치 경로에서 manage-ees.ps1을 찾을 수 없습니다.')
    args = [str(powershell), '-NoProfile', '-NonInteractive', '-File', str(script),
            '-Action', action, '-Config', str(config), *map(str, extra)]
    if not read and action != 'Update':
        args.append('-Summary')
    result = subprocess.run(args, env=env, stdout=subprocess.PIPE if read else None)
    if result.returncode:
        raise DeploymentError(f'EES 관리자의 {action} 단계가 완료되지 않았습니다. 위 출력에서 실패 단계를 확인하세요.')
    if read:
        answer = parse_output(result.stdout)
        if not isinstance(answer, dict):
            raise DeploymentError('EES 관리자 응답 형식을 확인하세요.')
        return answer


def git(repo, *args):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
    result = subprocess.run(['git', '-C', str(repo), *args], env=env, capture_output=True, timeout=90)
    if result.returncode:
        raise DeploymentError('설치 저장소의 Git 연결과 자격을 확인하세요.')
    return result.stdout.decode('utf-8').strip()


def check_source(repo, config):
    if git(repo, 'remote', 'get-url', 'origin') not in (SOURCE, SOURCE + '.git'):
        raise DeploymentError('기존 EES 설치 저장소의 origin을 확인하세요.')
    if git(repo, 'branch', '--show-current') != 'main' or git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise DeploymentError('설치 저장소의 main 브랜치와 로컬 수정 사항을 확인하세요.')
    # Do not advance the user's checkout if main has since moved to a different release.
    remote = git(repo, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').split()
    if remote != [SHA, 'refs/heads/main']:
        raise DeploymentError('main에 다른 버전이 있습니다. 현재 main에 맞는 배포 명령을 확인하세요.')
    manager(repo, config, 'Update')
    if any(git(repo, 'rev-parse', ref) != SHA for ref in ('HEAD', 'origin/main')):
        raise DeploymentError('업데이트 후 설치 소스가 지정된 배포 커밋과 일치하지 않습니다.')


def verified(path):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != SIZE or getattr(info, 'st_file_attributes', 0) & 0x400:
            return False
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest() == DIGEST
    except FileNotFoundError:
        return False


def download(repo, config, cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / FILENAME
    for existing in (target, Path.home() / 'Downloads' / FILENAME):
        if verified(existing):
            print('검증된 기존 프로그램 ZIP을 사용합니다.', flush=True)
            return existing
    # Loaded only after verifying HEAD. The existing client confines the saved token
    # to GitHub's API and uses the installation's configured Git proxy and TLS trust.
    sys.path.insert(0, str(repo / 'scripts'))
    import ees_upgrade as upgrade
    settings = upgrade.manager.states.load_config(config)
    client = upgrade.github_client(settings)
    downloads = upgrade.downloads
    old_limit = downloads.MAX_DOWNLOAD_SECONDS
    print('GitHub Actions에서 프로그램을 다운로드합니다 (약 149 MiB).', flush=True)
    downloads.MAX_DOWNLOAD_SECONDS = 3600
    try:
        with tempfile.TemporaryDirectory(prefix='ees-artifact-', dir=cache) as temp:
            part = Path(temp) / 'program.zip.part'
            for attempt in range(2):
                try:
                    client._download(ARTIFACT_ID, part, DIGEST, SIZE)
                    break
                except (downloads.DownloadError, OSError, http.client.HTTPException) as error:
                    code = getattr(error, 'code', None)
                    transient = code in (None, 'download_timeout', 'github_connection_failed', 'artifact_download_failed')
                    if getattr(error, 'code', None) == 'credentials_rejected' and attempt == 0 and sys.stdin.isatty():
                        if input('기존 GitHub 자격이 거절되었습니다. 새 GitHub Actions 읽기 토큰으로 바꿀까요? [y/N] ').strip().lower() != 'y':
                            raise DeploymentError('GitHub 저장소와 Actions 읽기 권한을 확인하세요.') from None
                        client = upgrade.github_client(settings, reset=True)
                    elif attempt > 0 or not transient:
                        raise DeploymentError('GitHub 프로그램 다운로드 실패 (' + (code or 'connection_error') + ').') from None
                    else:
                        print('다운로드 연결이 중단되어 한 번 다시 시도합니다.', flush=True)
                        time.sleep(2)
                    part.unlink(missing_ok=True)
            if not verified(part):
                raise DeploymentError('다운로드한 프로그램의 SHA256 또는 크기가 일치하지 않습니다.')
            os.replace(part, target)
            return target
    finally:
        downloads.MAX_DOWNLOAD_SECONDS = old_limit


def connection_choice(base, choice, settings, current):
    if choice is False or not base:
        if choice:
            raise DeploymentError('--connect에는 --confluence-base 주소가 필요합니다.')
        return False
    if choice is True:
        return True
    registered = {key.upper() for key in settings.get('env_names', [])}
    try:
        service_in_env = SERVICE in json.loads(os.environ.get(REGISTRY, '{}'))
    except (TypeError, ValueError):
        service_in_env = True
    if not sys.stdin.isatty():
        return False
    # Process-only settings from a previous guide run cannot be inferred from the
    # invoking shell. A healthy running release therefore defaults to no restart.
    default = not (current or service_in_env or {AUTH, REGISTRY} & registered)
    label = 'Y/n' if default else 'y/N'
    while True:
        response = input(f'이번 기동에 Confluence 읽기 연결을 설정할까요? [{label}] ').strip().lower()
        if not response:
            return default
        if response in ('y', 'yes', '예'):
            return True
        if response in ('n', 'no', '아니오'):
            return False


def get_connection(base, settings):
    # An isolated Python launch (-I) does not add the launcher's own directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guide_connection import connect, GuideConnectionError
    try:
        return connect(base, settings)
    except GuideConnectionError as error:
        raise DeploymentError(str(error)) from None


def selected(status):
    return (status.get('current_commit') == SHA and status.get('program_valid') is True
            and not status.get('program_incomplete'))


def start(repo, config, env):
    result = manager(repo, config, 'Start', '-HealthTimeout', '120', env=env, read=True)
    if result.get('already_running') or result.get('started') is not True:
        raise DeploymentError('새 서버 프로세스의 기동을 확인하지 못했습니다. 관리자 상태를 확인하세요.')


def install(repo, config, cache, base, choice):
    settings = json.loads(config.read_text(encoding='utf-8-sig'))
    initial = manager(repo, config, 'Status', read=True)
    current = selected(initial)
    connect_now = connection_choice(base, choice, settings, current)
    if (initial.get('current_commit') == SHA and not current) or initial.get('program_incomplete'):
        raise DeploymentError('이전 변경이 미완료이거나 현재 프로그램 검증에 실패했습니다. EES 관리자 상태를 확인하세요.')
    artifact = None
    if not current:
        check_source(repo, config)
        artifact = download(repo, config, cache)
    # Do not put Confluence credentials in the downloader's environment. Validate
    # both read APIs before any running service can be stopped.
    env = get_connection(base, settings) if connect_now else None
    now = manager(repo, config, 'Status', read=True)
    if selected(now):
        if now.get('managed_process_running') is True and connect_now:
            manager(repo, config, 'Stop')
            try:
                start(repo, config, env)
            except (DeploymentError, OSError, subprocess.SubprocessError, KeyboardInterrupt):
                # Retry only a stopped instance which is still on this release.
                # The manager remains responsible for process identity and locks.
                recovery = manager(repo, config, 'Status', read=True)
                if selected(recovery) and recovery.get('managed_process_running') is False:
                    start(repo, config, None)
                    raise DeploymentError('새 연결로 시작하지 못해 기존 관리 설정으로 서버를 다시 시작했습니다.') from None
                raise
        elif now.get('managed_process_running') is not True:
            start(repo, config, env)
    else:
        if (now.get('program_incomplete') or now.get('current_commit') != initial.get('current_commit')
                or now.get('current_commit') == SHA or artifact is None):
            raise DeploymentError('다른 작업이 설치 상태를 변경했습니다. EES 관리자 상태를 확인한 뒤 다시 실행하세요.')
        manager(repo, config, 'Upgrade', '-Bundle', artifact, '-Commit', SHA,
                '-ArtifactSha256', DIGEST, '-HealthTimeout', '120', env=env)
    final = manager(repo, config, 'Status', read=True)
    if not selected(final) or final.get('managed_process_running') is not True:
        raise DeploymentError('최종 설치 커밋 또는 EES 서버 기동 여부를 확인하지 못했습니다.')
    print('EES 배포 확인: ' + SHA[:12] + ' / 실행 중')
    if connect_now:
        print('이번 기동에 Confluence 읽기 연결을 적용했습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confluence-base')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--connect', action='store_true', dest='choice')
    group.add_argument('--skip-connect', action='store_false', dest='choice')
    parser.set_defaults(choice=None)
    args = parser.parse_args()
    if os.name != 'nt':
        raise DeploymentError('기존 EES 설치 계정의 Windows PowerShell에서 실행하세요.')
    local = Path(os.environ['LOCALAPPDATA']) / 'EES-Agent-POC'
    install(Path.home() / 'team-agent-poc', local / 'deployment/config.json',
            local / 'downloads', args.confluence_base, args.choice)


if __name__ == '__main__':
    try:
        main()
    except DeploymentError as error:
        sys.exit(str(error))
    except (EOFError, KeyboardInterrupt):
        sys.exit('운영자 입력으로 배포를 중단했습니다.')
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        sys.exit('설치 환경, 등록 파일 및 GitHub 연결을 확인하세요.')
